#!/bin/bash

echo "* Add required packages ..."
apt-get update
apt-get install -y gpg wget apt-transport-https

echo "* Add the Alloy repository key ..."
mkdir -p /etc/apt/keyrings
wget -O /etc/apt/keyrings/grafana.asc https://apt.grafana.com/gpg-full.key
chmod 644 /etc/apt/keyrings/grafana.asc
echo "deb [signed-by=/etc/apt/keyrings/grafana.asc] https://apt.grafana.com stable main" | tee /etc/apt/sources.list.d/grafana.list

echo "* Install Alloy ..."
apt-get update
apt-get install -y alloy

echo "* Configure Alloy on Linux ..."
tee /etc/alloy/config.alloy <<'EOF'
// ------------------------------------------------------------
// 1. Read systemd journal
// Priorities: value between 0 and 7 (emerg, alert, crit, error, warning, notice, info, or debug)
// ------------------------------------------------------------
loki.source.journal "read" {
        forward_to    = [loki.write.local.receiver]
        relabel_rules = loki.relabel.relabel_journal.rules
        matches       = "PRIORITY=0 PRIORITY=1 PRIORITY=2 PRIORITY=3"
        labels        = {
                job     = "journald",
                host    = constants.hostname,
        }
}

// ------------------------------------------------------------
// 2. Relabel journald metadata into log labels
// ------------------------------------------------------------
loki.relabel "relabel_journal" {
        forward_to = []

        rule {
                source_labels = ["__journal__systemd_unit"]
                target_label  = "unit"
        }

        rule {
                source_labels = ["__journal__boot_id"]
                target_label  = "boot_id"
        }

        rule {
                source_labels = ["__journal__transport"]
                target_label  = "transport"
        }

        rule {
                source_labels = ["__journal__priority_keyword"]
                target_label  = "level"
        }
}

// ------------------------------------------------------------
// 3. Loki writer (local Loki on localhost:3100)
// ------------------------------------------------------------
loki.write "local" {
        endpoint {
                url = "http://192.168.56.12:3100/loki/api/v1/push"
        }
}
EOF

echo "* Configure Alloy defaults ..."
tee /etc/default/alloy <<'EOF'
# The configuration file holding the Alloy config.
CONFIG_FILE="/etc/alloy/config.alloy"

# User-defined arguments to pass to the run command.
CUSTOM_ARGS="--server.http.listen-addr=0.0.0.0:12345"

# Restart on system upgrade. Defaults to true.
RESTART_ON_UPGRADE=true
EOF

echo "* Reload the configuration file ..."
systemctl reload alloy

echo "* Enable and restart Alloy ..."
systemctl enable alloy
systemctl restart alloy
systemctl status alloy --no-pager