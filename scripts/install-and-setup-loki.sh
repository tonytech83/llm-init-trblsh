#!/bin/bash

echo "* Create a user and group for Loki ..."
useradd -M -r -s /bin/false loki

echo "* Import the GPG key ..."
mkdir -p /etc/apt/keyrings
wget -O /etc/apt/keyrings/grafana.asc https://apt.grafana.com/gpg-full.key
chmod 644 /etc/apt/keyrings/grafana.asc
echo "deb [signed-by=/etc/apt/keyrings/grafana.asc] https://apt.grafana.com stable main" | tee /etc/apt/sources.list.d/grafana.list

echo "* Install Loki ..."
apt-get update
apt-get install -y loki

echo "* Configure Loki on Linux ..."
mkdir -p /etc/loki
tee /etc/loki/config.yml <<'EOF'
auth_enabled: false

server:
  http_listen_address: 0.0.0.0
  http_listen_port: 3100
  grpc_listen_port: 9096
  log_level: info
  grpc_server_max_concurrent_streams: 1000

target: all

common:
  instance_addr: 127.0.0.1
  path_prefix: /tmp/loki
  storage:
    filesystem:
      chunks_directory: /tmp/loki/chunks
      rules_directory: /tmp/loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: 100

limits_config:
  metric_aggregation_enabled: true
  enable_multi_variant_queries: true

schema_config:
  configs:
    - from: 2020-10-24
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

pattern_ingester:
  enabled: true
  metric_aggregation:
    loki_address: localhost:3100

ruler:
  alertmanager_url: http://localhost:9093
  enable_api: true
  rule_path: /tmp/loki/rules-temp   # scratch/temp dir
  ring:
    kvstore:
      store: inmemory
  storage:
    type: local
    local:
      directory: /tmp/loki/rules    # where rule files live
  evaluation_interval: 1m
  poll_interval: 1m

frontend:
  encoding: protobuf

analytics:
  reporting_enabled: false
EOF

echo "* Create a rule aiming **job** with name journald and **level** in err|crit|alert|emerg ..."
mkdir -p /tmp/loki/rules/fake
tee /tmp/loki/rules/fake/journald-logs.yaml <<'EOF'
groups:
    - name: journald-errors
      interval: 15s
      rules:
        - alert: CriticalLogDetected
          expr: sum by (host) (count_over_time({job="journald", level=~"err|crit|alert|emerg"}[1m])) > 0
          labels:
            alertname: CriticalLogDetected
            severity: critical
          annotations:
            description: Detected error-level logs from journald on {{ $labels.host }}
            summary: Critical log detected in journald
EOF

echo "* Create a systemd unit for Loki ..."
tee /etc/systemd/system/loki.service <<'EOF'
[Unit]
Description=Grafana Loki
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=loki
Group=loki
ExecStart=/usr/bin/loki -config.file /etc/loki/config.yml
TimeoutSec = 120
Restart = on-failure
RestartSec = 2

[Install]
WantedBy=multi-user.target
EOF

echo "* Restart Loki to apply config ..."
systemctl enable loki
systemctl restart loki
systemctl status loki --no-pager