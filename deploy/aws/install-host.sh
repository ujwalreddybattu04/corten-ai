#!/bin/bash
set -euo pipefail
umask 077
dnf install -y docker python3
systemctl enable --now docker
systemctl enable --now amazon-ssm-agent
install -d -m 700 /opt/corten/private /opt/corten/data /opt/corten/releases
install -d -m 755 /usr/local/lib/docker/cli-plugins
curl --fail --location --retry 3 https://github.com/docker/compose/releases/download/v2.39.2/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
curl --fail --location --retry 3 https://github.com/docker/compose/releases/download/v2.39.2/docker-compose-linux-x86_64.sha256 -o /tmp/compose.sha256
cd /usr/local/lib/docker/cli-plugins
printf '%s  docker-compose\n' "$(awk '{print $1}' /tmp/compose.sha256)" | sha256sum --check --status
chmod 755 docker-compose
if ! swapon --show | grep -q /opt/corten/swapfile; then
  test -f /opt/corten/swapfile || (fallocate -l 4G /opt/corten/swapfile && chmod 600 /opt/corten/swapfile && mkswap /opt/corten/swapfile)
  swapon /opt/corten/swapfile
  grep -q '^/opt/corten/swapfile ' /etc/fstab || echo '/opt/corten/swapfile none swap sw 0 0' >> /etc/fstab
fi
docker compose version
echo 'Corten host prerequisites ready'
