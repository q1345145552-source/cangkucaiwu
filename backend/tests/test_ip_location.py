"""Bundled offline database, fail-open geolocation and real audit HTTP requests."""
import asyncio
import hashlib
import json
import statistics
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.core import ip_location as geo
from app.core.security import hash_password
from app.main import app
from app.models import User
from app.models.audit_log import AuditLog
from tests.test_round2_permissions import auth
from tests.test_round3_permissions import hr_environment, snapshot

PUBLIC = '58.8.177.1'  # Public range test fixture, not a stored visitor address.
EMPTY = {'ip_country': '', 'ip_region': '', 'ip_city': ''}


@pytest.mark.parametrize('value', [None, '', 'not-ip', '0.0.0.0', '::', '192.0.2.1', '203.0.113.4', '224.0.0.1'])
def test_unknown_invalid_and_special_addresses_never_open_database(monkeypatch, value):
    monkeypatch.setattr(geo, '_database', lambda: pytest.fail('Must not open database'))
    assert geo.get_ip_location(value) == EMPTY


@pytest.mark.parametrize('value', ['10.2.3.4', '172.16.0.1', '172.31.255.255', '192.168.1.1', '127.0.0.1', '::1', 'fd00::1', 'fe80::1', '::ffff:192.168.1.1'])
def test_private_returns_internal_without_database(monkeypatch, value):
    monkeypatch.setattr(geo, '_database', lambda: pytest.fail('Private must not query database'))
    assert geo.get_ip_location(value) == {**EMPTY, 'ip_country': '内网'}


def test_real_file_checksum_china_thailand_ipv6_and_single_memory_load(monkeypatch):
    metadata = json.loads(geo.DATABASE.with_name('metadata.json').read_text())
    assert hashlib.sha256(geo.DATABASE.read_bytes()).hexdigest() == metadata['sha256']
    calls = []
    original = geo.maxminddb.open_database
    def opened(stream, *, mode):
        calls.append(mode)
        return original(stream, mode=mode)
    monkeypatch.setattr(geo, '_loaded', False)
    monkeypatch.setattr(geo, '_reader', None)
    monkeypatch.setattr(geo.maxminddb, 'open_database', opened)
    for _ in range(10):
        assert geo.get_ip_location(PUBLIC) == {'ip_country': '泰国', 'ip_region': '曼谷', 'ip_city': '旺通朗'}
    assert geo.get_ip_location('119.147.115.112') == {'ip_country': '中国', 'ip_region': '广东', 'ip_city': '广州'}
    assert geo.get_ip_location('240e:47c:40:10::1')['ip_country'] == '中国'
    assert calls == [geo.maxminddb.MODE_FD]
    assert geo._reader._buffer_size == metadata['database_bytes']
    geo._reader.close()


def test_missing_database_failure_cached_and_bad_record_fail_open(monkeypatch, tmp_path):
    monkeypatch.setattr(geo, '_loaded', False)
    monkeypatch.setattr(geo, '_reader', None)
    monkeypatch.setattr(geo, 'DATABASE', tmp_path / 'missing.gz')
    assert geo.get_ip_location(PUBLIC) == EMPTY
    assert geo._loaded is True
    # A failed initial load must not reopen the file on each request.
    monkeypatch.setattr(geo.gzip, 'open', lambda *a, **k: pytest.fail('Must not retry every request'))
    assert geo.get_ip_location(PUBLIC) == EMPTY
    class Broken:
        def get(self, ip): raise RuntimeError('malformed isolated record')
    monkeypatch.setattr(geo, '_database', lambda: Broken())
    assert geo.get_ip_location(PUBLIC) == EMPTY


def test_public_172_is_not_mislabelled_as_internal(monkeypatch):
    seen = []
    class Reader:
        def get(self, ip):
            seen.append(ip)
            return {'country': {'names': {'en': 'United States'}}}
    monkeypatch.setattr(geo, '_database', lambda: Reader())
    assert geo.get_ip_location('172.217.14.206')['ip_country'] == 'United States'
    assert seen == ['172.217.14.206']


def test_missing_database_does_not_break_login_or_drop_audit(tmp_path, monkeypatch):
    async def run():
        monkeypatch.setattr(geo, '_loaded', False)
        monkeypatch.setattr(geo, '_reader', None)
        monkeypatch.setattr(geo, 'DATABASE', tmp_path / 'missing.gz')
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, _):
            async with factory() as db:
                (await db.get(User, 1)).password_hash = hash_password('missing-db-test')
                await db.commit()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(PUBLIC, 12)), base_url='http://test') as client:
                r = await client.post('/api/v1/auth/login', json={'username': 'warehouse_admin', 'password': 'missing-db-test'})
                assert r.status_code == 200
            async with factory() as db:
                record = (await db.execute(select(AuditLog))).scalar_one()
                assert record.action_type == 'login' and record.ip_address == PUBLIC
                assert {k: getattr(record, k) for k in EMPTY} == EMPTY
    asyncio.run(run())


def test_login_writes_country_region_city_old_nulls_no_secrets_and_ten_operations(tmp_path, monkeypatch):
    async def run():
        import app.core.audit as audit
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, _):
            password = 'isolated-location-test'
            async with factory() as db:
                (await db.get(User, 1)).password_hash = hash_password(password)
                db.add(AuditLog(id=1, user_id=1, warehouse_id=1, action_type='edit', module='old', ip_address='172.18.0.5'))
                await db.commit()
            old = await snapshot(factory)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(PUBLIC, 12345)), base_url='http://test') as client:
                r = await client.post('/api/v1/auth/login', json={'username': 'warehouse_admin', 'password': password})
                assert r.status_code == 200, r.text
                token = r.json()['access_token']
                headers = {**auth(1), 'X-Warehouse-ID': '1'}
                # Compare ten otherwise-identical real writes, with a warm offline reader.
                original = audit.get_ip_location
                timings = {}
                for label, lookup in [('baseline', lambda _: EMPTY), ('offline', original)]:
                    monkeypatch.setattr(audit, 'get_ip_location', lookup)
                    samples = []
                    for _ in range(10):
                        start = time.perf_counter()
                        response = await client.put('/api/v1/customers/1', headers=headers, json={'company_name': '隔离地区验收客户'})
                        samples.append((time.perf_counter() - start) * 1000)
                        assert response.status_code == 200, response.text
                    timings[label] = {'average_ms': round(statistics.mean(samples), 3), 'samples_ms': [round(v, 3) for v in samples]}
                result = await client.get('/api/v1/settings/logs', headers=headers, params={'page_size': 100})
                assert result.status_code == 200
                logs = result.json()['data']
                legacy = next(row for row in logs if row['id'] == 1)
                assert all(legacy[k] is None for k in EMPTY)
                login = next(row for row in logs if row['action_type'] == 'login')
                assert login['ip_address'] == PUBLIC
                assert {k: login[k] for k in EMPTY} == original(PUBLIC)
                assert len(logs) == 22
                assert sum(row['ip_country'] == '泰国' for row in logs) == 11
                assert await snapshot(factory) == old
                async with factory() as db:
                    details = json.dumps([row.detail for row in (await db.execute(select(AuditLog))).scalars()])
                assert password not in details and token not in details and 'password' not in details
                proof = {'environment': 'temporary isolated database, real HTTP; not production', 'login': login, 'legacy': legacy, 'ten_operations': timings}
                print('IP_LOCATION_ACTUAL', json.dumps(proof, ensure_ascii=False))
    asyncio.run(run())
