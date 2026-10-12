"""Materialize container credentials privately on the authorized AWS host."""
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit


def main():
    result = subprocess.run(['aws', 'secretsmanager', 'get-secret-value', '--region', 'ap-southeast-2',
        '--secret-id', 'corten-ai/runtime', '--query', 'SecretString', '--output', 'text'],
        capture_output=True, text=True, check=True)
    config = json.loads(result.stdout)
    private = Path('/opt/corten/private')
    private.mkdir(mode=0o700, parents=True, exist_ok=True)

    def write(name, content):
        path = private / name
        path.write_text(content, encoding='utf-8')
        path.chmod(0o600)
        return path

    def envfile(name, values):
        lines = []
        for key, value in values.items():
            value = str(value)
            if any(c in value for c in ('\n', '\r', '\0')):
                raise ValueError('Multiline container setting rejected: ' + key)
            lines.append(key + '=' + value)
        return write(name, '\n'.join(lines) + '\n')

    envfile('backend.env', config['backend'])
    origin = config['app_origin']
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise ValueError('A public HTTPS application origin is required')
    envfile('frontend.env', {'APP_ORIGIN': origin})
    envfile('postgres.env', {'POSTGRES_USER': config['database']['user'],
        'POSTGRES_DB': config['database']['name'], 'POSTGRES_PASSWORD': config['database']['password']})
    password = config['redis']['password']
    if len(password) != 64 or any(c not in '0123456789abcdef' for c in password):
        raise ValueError('Unexpected generated Redis credential format')
    redis_config = write('redis.conf', 'bind 0.0.0.0\nprotected-mode yes\nappendonly yes\n'
        'appendfsync everysec\nmaxmemory 128mb\nmaxmemory-policy noeviction\nrequirepass ' + password + '\n')
    os.chown(redis_config, 999, 1000)
    write('redis-password', password + '\n')
    for name in ('postgres', 'redis', 'reports', 'space-files', 'backups'):
        path = Path('/opt/corten/data') / name
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chown('/opt/corten/data/reports', 10001, 10001)
    os.chown('/opt/corten/data/space-files', 10001, 10001)
    print('Private container runtime settings prepared')


if __name__ == '__main__':
    main()
