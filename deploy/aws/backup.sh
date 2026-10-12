#!/bin/bash
set -euo pipefail
umask 077
exec 9>/opt/corten/private/backup.lock
flock -n 9 || exit 0
cd /opt/corten/current
bucket=$(cat /opt/corten/private/artifacts-bucket)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
file="/opt/corten/data/backups/${stamp}.dump"
docker compose -f deploy/aws/compose.yaml exec -T postgres pg_dump -U corten -d corten_ai --format=custom --no-owner --no-acl > "$file"
test -s "$file"
aws s3 cp "$file" "s3://${bucket}/backups/${stamp}.dump" --region ap-southeast-2 --sse AES256 --only-show-errors
find /opt/corten/data/backups -maxdepth 1 -type f -name '*.dump' -mtime +3 -delete
# Space knowledge files: incremental, encrypted mirror. Deleted files are removed from the copy too.
aws s3 sync /opt/corten/data/space-files "s3://${bucket}/space-files/" --region ap-southeast-2 --sse AES256 \
  --delete --exclude '*.partial' --only-show-errors
echo "Encrypted database backup completed: ${stamp}"
