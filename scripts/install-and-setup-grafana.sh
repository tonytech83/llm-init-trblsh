#!/bin/bash

echo "* Install the prerequisite packages ..."
apt-get update
apt-get install -y apt-transport-https wget gnupg

echo "* Import the GPG key ..."
mkdir -p /etc/apt/keyrings
wget -O /etc/apt/keyrings/grafana.asc https://apt.grafana.com/gpg-full.key
chmod 644 /etc/apt/keyrings/grafana.asc

echo "* Add a repository for stable releases ..."
echo "deb [signed-by=/etc/apt/keyrings/grafana.asc] https://apt.grafana.com stable main" | tee /etc/apt/sources.list.d/grafana.list

echo "*  Install Grafana ..."
apt-get update
apt-get install -y grafana

echo "* Provision Loki datasource into Grafana ..."
mkdir -p /etc/grafana/provisioning/datasources

tee /etc/grafana/provisioning/datasources/loki.yaml <<'EOF'
apiVersion: 1
datasources:
  - name: Loki
    type: loki
    access: proxy
    url: http://localhost:3100
    isDefault: true
    jsonData:
      maxLines: 1000
EOF

echo "* Enable and restart Grafana to apply provisioned datasource ..."
systemctl enable grafana-server
systemctl restart grafana-server
systemctl status grafana-server --no-pager