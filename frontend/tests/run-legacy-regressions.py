"""Run the original 61 frontend groups plus reviewed import groups with fresh loopback PostgreSQL/HTTP fixtures.

Requires the project's Python test dependencies, native PostgreSQL binaries and
the installed frontend node_modules. Never reads deployment files or remote data.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
HTTP_GROUPS = {'account-attendance.test.cjs', 'account-permissions.test.cjs',
               'button-permissions.test.cjs', 'menu-backend-regression.test.cjs', 'menu-permissions.test.cjs',
               'config-center-access.test.cjs', 'employee-self.test.cjs', 'payroll-supervisor.test.cjs'}


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--postgres-bin', required=True, type=Path)
    parser.add_argument('--node-modules', required=True, type=Path)
    parser.add_argument('--node', default=shutil.which('node'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--tests', nargs='+', help='Specific .test.cjs basenames; default original 61 plus import groups')
    args = parser.parse_args()
    assert args.node and (args.node_modules / 'typescript').is_dir()
    assert (args.postgres_bin / 'initdb').is_file()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    local = Path(tempfile.mkdtemp(prefix='legacy12-isolated-'))
    data = local / 'data'
    port = free_port(); http_port = free_port()
    while http_port == port or http_port in (18080, 18082):
        http_port = free_port()
    env = os.environ.copy()
    url = f'postgresql+asyncpg://legacy12@127.0.0.1:{port}/postgres'
    env.update(SECRET_KEY='legacy12-synthetic-local-key-not-for-production-20261027', DATABASE_URL=url, LEGACY12_DATABASE_URL=url, LEGACY12_HTTP_PORT=str(http_port),
               LEGACY12_FIXTURE_FILE=str(out / 'fixture.json'), TEST_API_URL=f'http://127.0.0.1:{http_port}/api/v1',
               NODE_PATH=str(args.node_modules.resolve()), INVENTORY_REGISTRY_FILE=str(out / 'registry.json'),
               SUPPLIER12_MENU_REPORT=str(out / 'supplier-menu.json'))
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.core.menu_registry import MENU_PERMISSIONS
    (out / 'registry.json').write_text(json.dumps([p.as_dict() for p in MENU_PERMISSIONS], ensure_ascii=False))
    tests = sorted(p.name for p in (ROOT / 'frontend/tests').glob('*.test.cjs'))
    manifest = json.loads((ROOT / 'frontend/tests/legacy-regression-suite.json').read_text())
    assert len(manifest['original_61']) == 61
    expected = manifest['original_61'] + manifest['added_import_groups'] + manifest['added_supplier_usability_groups']
    assert len(expected) == len(set(expected))
    assert set(tests) == set(expected), f'Suite differs from reviewed manifest: missing={set(expected)-set(tests)}, extra={set(tests)-set(expected)}'
    if args.tests:
        assert set(args.tests) <= set(tests)
        tests = args.tests
    records = []; lifecycle = []; fixture_runs = []; cleanup_ok = False; fixture = None; pg_started = False; fixture_log = None
    def command(argv, name):
        with (out / name).open('w') as log:
            result = subprocess.run([str(a) for a in argv], env=env, stdout=log, stderr=subprocess.STDOUT)
        lifecycle.append({'command': [str(a) for a in argv], 'exit_code': result.returncode, 'log': str(out / name)})
        (out / 'lifecycle.json').write_text(json.dumps(lifecycle, indent=2))
        result.check_returncode()
    def stop_fixture():
        nonlocal fixture, fixture_log
        if fixture is None:
            return
        if fixture.poll() is None:
            fixture.send_signal(signal.SIGINT)
            fixture.wait(timeout=30)
        fixture_runs[-1]['exit_code'] = fixture.returncode
        fixture_log.close()
        fixture_log = None
        fixture = None
        (out / 'fixture-runs.json').write_text(json.dumps(fixture_runs, indent=2))
        assert fixture_runs[-1]['exit_code'] == 0, 'Fixture shutdown failed; inspect its log'
    def start_fixture(group):
        nonlocal fixture, fixture_log
        stop_fixture()
        number = len(fixture_runs) + 1
        folder = out / f'fixture-{number:02d}-{group.removesuffix(".test.cjs")}'
        folder.mkdir()
        env['LEGACY12_FIXTURE_FILE'] = str(folder / 'fixture.json')
        fixture_log = (folder / 'fixture.log').open('w')
        argv = [sys.executable, str(ROOT / 'frontend/tests/legacy-regression.fixture.py')]
        fixture = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=fixture_log, stderr=subprocess.STDOUT)
        fixture_runs.append({'group': group, 'command': argv, 'metadata': env['LEGACY12_FIXTURE_FILE'],
                             'log': str(folder / 'fixture.log'), 'pid': fixture.pid})
        for _ in range(150):
            if fixture.poll() is not None:
                raise RuntimeError('Isolated fixture exited; inspect its log')
            try:
                if urlopen(f'http://127.0.0.1:{http_port}/health', timeout=1).status == 200:
                    return
            except OSError:
                time.sleep(.2)
        raise RuntimeError('Isolated fixture did not start')
    try:
        command([args.postgres_bin / 'initdb', '-D', data, '-U', 'legacy12', '-A', 'trust',
                 '--no-locale', '--encoding=UTF8'], 'initdb.log')
        with (data / 'postgresql.conf').open('a') as config:
            config.write(f"\nlisten_addresses='127.0.0.1'\nport={port}\nunix_socket_directories='{local}'\n")
        command([args.postgres_bin / 'pg_ctl', '-D', data, '-l', out / 'postgres.log', '-w', 'start'], 'postgres-start.log')
        pg_started = True
        for name in tests:
            # Writes in account/button groups must not contaminate other groups or
            # permission subjects. Each HTTP group receives its own newly seeded schema.
            if name in HTTP_GROUPS or fixture is None:
                start_fixture(name)
            env['LEGACY_TEST_REPORT'] = str(out / (name + '.data.json'))
            cmd = [args.node, str(ROOT / 'frontend/tests' / name)]
            start = time.monotonic()
            with (out / (name + '.log')).open('w') as log:
                try:
                    result = subprocess.run(cmd, cwd=ROOT / 'frontend', env=env, stdout=log,
                                            stderr=subprocess.STDOUT, timeout=120)
                    code = result.returncode
                except subprocess.TimeoutExpired:
                    code = 124
            row = {'test': name, 'command': cmd, 'exit_code': code, 'seconds': time.monotonic() - start,
                   'log': str(out / (name + '.log')), 'fixture': env['LEGACY12_FIXTURE_FILE']}
            records.append(row)
            (out / 'results.json').write_text(json.dumps(records, indent=2))
            print(f'{name}: exit {code}', flush=True)
    finally:
        stop_fixture()
        if pg_started:
            # A new data directory and dynamic ports belong exclusively to this invocation.
            command([args.postgres_bin / 'psql', '-h', '127.0.0.1', '-p', str(port), '-U', 'legacy12',
                     '-d', 'postgres', '-Atc', "SELECT count(*) FROM information_schema.schemata WHERE schema_name LIKE 'legacy12_%'"], 'remaining-schemas.log')
            command([args.postgres_bin / 'pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop'], 'postgres-stop.log')
            cleanup_ok = (out / 'remaining-schemas.log').read_text().strip() == '0' and not (data / 'postmaster.pid').exists() and all(r['exit_code'] == 0 for r in fixture_runs)
        summary = {'data_directory': str(data), 'postgres_port': port, 'http_port': http_port,
                   'base_url': env['TEST_API_URL'], 'total': len(records),
                   'passed': sum(r['exit_code'] == 0 for r in records), 'excluded_legacy_standalone': [],
                   'fixture_runs': len(fixture_runs), 'cleanup_ok': cleanup_ok,
                   'production_access': False, 'remote_operations': False}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    return int(not cleanup_ok or len(records) != len(tests) or any(r['exit_code'] != 0 for r in records))


if __name__ == '__main__':
    raise SystemExit(main())
