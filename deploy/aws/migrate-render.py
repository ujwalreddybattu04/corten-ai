"""Copy the approved Render database into a NEW AWS PostgreSQL database."""
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit, unquote


def main():
    destination = Path('/opt/corten/private')
    response = subprocess.run(['aws', 'secretsmanager', 'get-secret-value', '--region', 'ap-southeast-2',
        '--secret-id', 'corten-ai/render-database-migration', '--query', 'SecretString', '--output', 'text'],
        capture_output=True, text=True, check=True)
    source = urlsplit(json.loads(response.stdout)['url'])
    if not source.hostname or not source.hostname.endswith('.render.com'):
        raise ValueError('Unexpected source database provider')
    env = {'PGHOST': source.hostname, 'PGPORT': str(source.port or 5432),
        'PGUSER': unquote(source.username or ''), 'PGPASSWORD': unquote(source.password or ''),
        'PGDATABASE': unquote(source.path.lstrip('/')), 'PGSSLMODE': 'verify-full', 'PGSSLROOTCERT': '/run/ca.pem'}
    path = destination / 'render-source.env'
    for value in env.values():
        if '\n' in value or '\r' in value:
            raise ValueError('Invalid database connection setting')
    path.write_text(''.join(k + '=' + v + '\n' for k, v in env.items()), encoding='utf-8')
    path.chmod(0o600)
    work = Path('/opt/corten/data/migration')
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    run = lambda args, **kwargs: subprocess.run(args, check=True, **kwargs)
    source_client = ['docker', 'run', '--rm', '--cap-drop=ALL', '--security-opt=no-new-privileges',
        '--env-file', str(path), '-v', '/etc/pki/tls/certs/ca-bundle.crt:/run/ca.pem:ro',
        '-v', str(work) + ':/work', 'postgres:18-alpine']
    try:
        run(source_client + ['psql', '-tAc', 'SHOW server_version'])
        run(source_client + ['pg_dump', '--format=custom', '--no-owner', '--no-acl', '--file=/work/render.dump'])
        config = json.loads(subprocess.run(['aws', 'secretsmanager', 'get-secret-value', '--region', 'ap-southeast-2',
            '--secret-id', 'corten-ai/runtime', '--query', 'SecretString', '--output', 'text'],
            capture_output=True, text=True, check=True).stdout)
        target = destination / 'restore-target.env'
        target.write_text('PGHOST=postgres\nPGUSER=corten\nPGDATABASE=corten_ai\nPGPASSWORD=' +
            config['database']['password'] + '\n', encoding='utf-8')
        target.chmod(0o600)
        client = ['docker', 'run', '--rm', '--network', 'corten_default', '--env-file', str(target),
            '-v', str(work) + ':/work:ro', 'postgres:18-alpine']
        check = subprocess.run(client + ['psql', '-tAc',
            "SELECT count(*) FROM pg_tables WHERE schemaname='public'"], check=True, capture_output=True, text=True)
        if int(check.stdout.strip()) != 0:
            raise RuntimeError('Destination is not empty; refusing to overwrite any AWS application data')
        run(client + ['pg_restore', '--single-transaction', '--exit-on-error', '--no-owner', '--no-privileges', '--dbname=corten_ai', '/work/render.dump'])
        run(client + ['psql', '-tAc', 'SELECT count(*) AS users FROM users'])
        (work / 'completed').write_text('Verified initial Render database copy\n')
    finally:
        path.unlink(missing_ok=True)
        (destination / 'restore-target.env').unlink(missing_ok=True)
    print('Initial database copy completed; temporary connection files removed')


if __name__ == '__main__':
    main()
