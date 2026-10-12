"""Restore a backup in an isolated temporary database; leave production untouched."""
import json
from pathlib import Path
import subprocess
import uuid
import hashlib

from importlib.util import module_from_spec, spec_from_file_location


def main():
    backups = sorted(Path('/opt/corten/data/backups').glob('*.dump'))
    if not backups:
        raise RuntimeError('No backup exists to verify')
    name = 'corten_restore_verify_' + uuid.uuid4().hex
    downloaded = Path('/opt/corten/private') / (name + '.dump')
    bucket = Path('/opt/corten/private/artifacts-bucket').read_text().strip()
    subprocess.run(['aws', 's3', 'cp', 's3://'+bucket+'/backups/'+backups[-1].name,
        str(downloaded), '--region', 'ap-southeast-2', '--only-show-errors'], check=True)
    downloaded.chmod(0o600)
    if hashlib.sha256(downloaded.read_bytes()).digest() != hashlib.sha256(backups[-1].read_bytes()).digest():
        downloaded.unlink()
        raise RuntimeError('Downloaded S3 backup checksum differs')
    compose = Path(__file__).resolve().with_name('compose.yaml')
    prefix = ['docker', 'compose', '-f', str(compose), 'exec', '-T', 'postgres']
    def sql(database, command):
        return subprocess.run(prefix + ['psql', '-U', 'corten', '-d', database, '-At',
            '-v', 'ON_ERROR_STOP=1', '-c', command], check=True, capture_output=True, text=True).stdout
    spec = spec_from_file_location('verify_migration', Path(__file__).with_name('verify-migration.py'))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    created = False
    try:
        sql('postgres', 'CREATE DATABASE ' + name)
        created = True
        with downloaded.open('rb') as stream:
            subprocess.run(prefix + ['pg_restore', '-U', 'corten', '--dbname='+name,
                '--single-transaction', '--exit-on-error', '--no-owner', '--no-privileges'],
                stdin=stream, check=True)
        actual = sql(name, module.COUNTS)
        expected = sql('corten_ai', module.COUNTS)
        if actual != expected:
            raise RuntimeError('Backup restored but counts differ; inspect concurrent writes')
        print(json.dumps({'backup': backups[-1].name, 'restored_counts': actual.splitlines(),
            'counts_match': True, 'downloaded_from_s3': True, 'production_unchanged': True}))
    finally:
        if created:
            sql('postgres', 'DROP DATABASE ' + name)
        downloaded.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
