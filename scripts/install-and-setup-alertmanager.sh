#!/bin/bash

ALERTMANAGER_VERSION="0.28.1"
ALERTMANAGER_ARCH="linux-amd64"
ALERTMANAGER_PKG="alertmanager-${ALERTMANAGER_VERSION}.${ALERTMANAGER_ARCH}"

echo "* Create a user and group for Alertmanager ..."
useradd -M -r -s /bin/false alertmanager

echo "* Download and install the Alertmanager binaries ..."
wget -q "https://github.com/prometheus/alertmanager/releases/download/v${ALERTMANAGER_VERSION}/${ALERTMANAGER_PKG}.tar.gz"
tar xfz "${ALERTMANAGER_PKG}.tar.gz"
cp "${ALERTMANAGER_PKG}/alertmanager" /usr/local/bin/
cp "${ALERTMANAGER_PKG}/amtool"       /usr/local/bin/
chown alertmanager:alertmanager /usr/local/bin/alertmanager /usr/local/bin/amtool

echo "* Create directories ..."
mkdir -p /etc/alertmanager /var/lib/alertmanager
chown -R alertmanager:alertmanager /etc/alertmanager /var/lib/alertmanager

echo "* Cleaning up downloaded files ..."
rm -rf "${ALERTMANAGER_PKG}" "${ALERTMANAGER_PKG}.tar.gz"

echo "* Create configuration file ..."
tee /etc/alertmanager/alertmanager.yml <<'EOF'
route:
  group_by: ['hostname']
  group_wait: 30s
  group_interval: 1m
  repeat_interval: 2m
  receiver: 'web.hook'
receivers:
  - name: 'web.hook'
    webhook_configs:
      - url: 'https://webhook.site/8b0d4532-590f-40fe-89b0-d9bc72ee86d5'
EOF

echo "* Create a systemd unit for Alertmanager ..."
tee /etc/systemd/system/alertmanager.service <<'EOF'
[Unit]
Description=Prometheus Alertmanager
Wants=network-online.target
After=network-online.target

[Service]
User=alertmanager
Group=alertmanager
Type=simple
ExecStart=/usr/local/bin/alertmanager --config.file=/etc/alertmanager/alertmanager.yml --storage.path=/var/lib/alertmanager/

[Install]
WantedBy=multi-user.target
EOF

echo "* Start and enable the alertmanager service ..."
systemctl daemon-reload
systemctl enable alertmanager
systemctl start alertmanager
systemctl status alertmanager --no-pager