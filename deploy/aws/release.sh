#!/bin/bash
# Run through Systems Manager on the Corten host; never paste secret values.
set -euo pipefail
umask 077
test "$#" -eq 3 || { echo 'Usage: release.sh BUCKET RELEASE_KEY SHA256' >&2; exit 2; }
bucket=$1
key=$2
digest=$3
[[ "$digest" =~ ^[a-f0-9]{64}$ ]] || exit 2
[[ "$key" == releases/* ]] || exit 2
exec 9>/opt/corten/private/release.lock
flock -n 9 || { echo 'Another release is running' >&2; exit 1; }
archive="/opt/corten/releases/${digest}.tar.gz"
target="/opt/corten/releases/${digest}"
aws s3 cp "s3://${bucket}/${key}" "$archive" --region ap-southeast-2 --only-show-errors
printf '%s  %s\n' "$digest" "$archive" | sha256sum --check --status
python3 - "$archive" <<'PY'
from pathlib import PurePosixPath
import sys
import tarfile
with tarfile.open(sys.argv[1]) as archive:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or not (member.isdir() or member.isfile()):
            raise ValueError('Unsafe source archive member')
PY
install -d -m 755 "$target"
tar -xzf "$archive" -C "$target" --no-same-owner
find "$target" -type d -exec chmod 0755 {} +
# Keep the previous release link until all images and migrations are verified.
cd "$target"
python3 deploy/aws/prepare-runtime.py
docker compose -f deploy/aws/compose.yaml config --quiet
docker compose -f deploy/aws/compose.yaml build backend frontend
docker compose -f deploy/aws/compose.yaml run --rm -T backend python - < deploy/aws/verify-personal-storage.py
if test -L /opt/corten/current; then
  /bin/bash /opt/corten/current/deploy/aws/backup.sh
fi
docker compose -f deploy/aws/compose.yaml run --rm backend python -m src.db.migrate
ln -sfn "$target" /opt/corten/current
printf '%s\n' "$bucket" > /opt/corten/private/artifacts-bucket
install -m 0644 deploy/aws/corten-backup.service deploy/aws/corten-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now corten-backup.timer
docker compose -f deploy/aws/compose.yaml up -d --wait --wait-timeout 180
curl --retry 3 --retry-all-errors --retry-delay 2 --fail --silent --show-error \
  --max-time 20 http://127.0.0.1/api/v1/search/status
echo 'Corten release ready'
