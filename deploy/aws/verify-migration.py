"""Compare source/target row counts without exposing account data or credentials."""
import json
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlsplit


COUNTS = """SELECT tablename, (xpath('/row/c/text()',query_to_xml(
    format('SELECT count(*) c FROM %I.%I',schemaname,tablename),false,true,'')))[1]::text
    FROM pg_tables WHERE schemaname='public' ORDER BY tablename"""


def main():
    secret = subprocess.run(['aws', 'secretsmanager', 'get-secret-value', '--region',
        'ap-southeast-2', '--secret-id', 'corten-ai/render-database-migration',
        '--query', 'SecretString', '--output', 'text'], check=True, capture_output=True, text=True)
    source = urlsplit(json.loads(secret.stdout)['url'])
    if not source.hostname or not source.hostname.endswith('.render.com'):
        raise ValueError('Unexpected source database provider')
    path = Path('/opt/corten/private/verify-source.env')
    values = {'PGHOST': source.hostname, 'PGPORT': str(source.port or 5432),
        'PGUSER': unquote(source.username or ''), 'PGPASSWORD': unquote(source.password or ''),
        'PGDATABASE': unquote(source.path.lstrip('/')), 'PGSSLMODE': 'verify-full',
        'PGSSLROOTCERT': '/run/ca.pem'}
    if any(any(c in v for c in '\r\n\0') for v in values.values()):
        raise ValueError('Invalid connection setting')
    path.write_text(''.join(k+'='+v+'\n' for k,v in values.items()), encoding='utf-8')
    path.chmod(0o600)
    try:
        source_result = subprocess.run(['docker', 'run', '--rm', '--env-file', str(path),
            '-v', '/etc/pki/tls/certs/ca-bundle.crt:/run/ca.pem:ro', 'postgres:18-alpine',
            'psql', '-At', '-v', 'ON_ERROR_STOP=1', '-c', COUNTS], check=True, capture_output=True, text=True)
        target_result = subprocess.run(['docker', 'compose', '-f', str(Path(__file__).resolve().with_name('compose.yaml')),
            'exec', '-T', 'postgres', 'psql', '-U', 'corten', '-d', 'corten_ai',
            '-At', '-v', 'ON_ERROR_STOP=1', '-c', COUNTS], check=True, capture_output=True, text=True)
        equal = source_result.stdout == target_result.stdout
        print(json.dumps({'source_counts': source_result.stdout.splitlines(),
            'aws_counts': target_result.stdout.splitlines(), 'counts_match': equal}))
        if not equal:
            raise RuntimeError('Row counts differ. Inspect concurrent Render writes; do not overwrite AWS data.')
    finally:
        path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
