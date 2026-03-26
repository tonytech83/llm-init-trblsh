#!/bin/bash

echo '* Install Docker Registry ...'
docker run -d -p 5000:5000 --restart always --name registry registry:2

echo '* Adjust the /etc/docker/daemon.json file ...'

tee /etc/docker/daemon.json <<'EOF'
{
    "insecure-registries" : [ "192.168.56.15:5000" ]
}
EOF

echo '* Reload and restart the Docker daemon ...'
systemctl daemon-reload
systemctl restart docker