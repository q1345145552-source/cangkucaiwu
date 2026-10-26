"""Run 56 declared frontend groups with a fresh loopback PostgreSQL/HTTP fixture.

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
EXCLUDED = ['account-attendance.test.cjs', 'account-permissions.test.cjs',
            'button-permissions.test.cjs', 'menu-backend-regression.test.cjs', 'menu-permissions.test.cjs']


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
    parser.add_argument('--tests', nargs='+', help='Specific .test.cjs basenames; default all declared 56')
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
    tests = sorted(p.name for p in (ROOT / 'frontend/tests').glob('*.test.cjs') if p.name not in EXCLUDED)
    assert len(tests) == 56, f'Declared suite count changed: {len(tests)}; review exclusions explicitly'
    if args.tests:
        assert set(args.tests) <= set(tests)
        tests = args.tests
    records = []; lifecycle = []; cleanup_ok = False; fixture = None; pg_started = False; fixture_log = None
    def command(argv, name):
        with (out / name).open('w') as log:
            result = subprocess.run([str(a) for a in argv], env=env, stdout=log, stderr=subprocess.STDOUT)
        lifecycle.append({'command': [str(a) for a in argv], 'exit_code': result.returncode, 'log': str(out / name)})
        (out / 'lifecycle.json').write_text(json.dumps(lifecycle, indent=2))
        result.check_returncode()
    try:
        command([args.postgres_bin / 'initdb', '-D', data, '-U', 'legacy12', '-A', 'trust',
                 '--no-locale', '--encoding=UTF8'], 'initdb.log')
        with (data / 'postgresql.conf').open('a') as config:
            config.write(f"\nlisten_addresses='127.0.0.1'\nport={port}\nunix_socket_directories='{local}'\n")
        command([args.postgres_bin / 'pg_ctl', '-D', data, '-l', out / 'postgres.log', '-w', 'start'], 'postgres-start.log')
        pg_started = True
        fixture_log = (out / 'fixture.log').open('w')
        fixture = subprocess.Popen([sys.executable, str(ROOT / 'frontend/tests/legacy-regression.fixture.py')],
                                   cwd=ROOT, env=env, stdout=fixture_log, stderr=subprocess.STDOUT)
        for _ in range(150):
            if fixture.poll() is not None:
                raise RuntimeError('Isolated fixture exited; inspect fixture.log')
            try:
                if urlopen(f'http://127.0.0.1:{http_port}/health', timeout=1).status == 200:
                    break
            except OSError:
                time.sleep(.2)
        else:
            raise RuntimeError('Isolated fixture did not start')
        for name in tests:
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
                   'log': str(out / (name + '.log'))}
            records.append(row)
            (out / 'results.json').write_text(json.dumps(records, indent=2))
            print(f'{name}: exit {code}', flush=True)
    finally:
        if fixture is not None and fixture.poll() is None:
            fixture.send_signal(signal.SIGINT)
            fixture.wait(timeout=30)
        if fixture_log:
            fixture_log.close()
        if pg_started:
            # A new data directory and dynamic ports belong exclusively to this invocation.
            command([args.postgres_bin / 'psql', '-h', '127.0.0.1', '-p', str(port), '-U', 'legacy12',
                     '-d', 'postgres', '-Atc', "SELECT count(*) FROM information_schema.schemata WHERE schema_name LIKE 'legacy12_%'"], 'remaining-schemas.log')
            command([args.postgres_bin / 'pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop'], 'postgres-stop.log')
            cleanup_ok = (out / 'remaining-schemas.log').read_text().strip() == '0' and not (data / 'postmaster.pid').exists() and fixture.returncode == 0
        summary = {'data_directory': str(data), 'postgres_port': port, 'http_port': http_port,
                   'base_url': env['TEST_API_URL'], 'total': len(records),
                   'passed': sum(r['exit_code'] == 0 for r in records), 'excluded_legacy_standalone': EXCLUDED,
                   'fixture_exit': fixture.returncode if fixture else None, 'cleanup_ok': cleanup_ok,
                   'production_access': False, 'remote_operations': False}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    return int(not cleanup_ok or len(records) != len(tests) or any(r['exit_code'] != 0 for r in records))


if __name__ == '__main__':
    raise SystemExit(main())
