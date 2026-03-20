#!/bin/bash

echo "* Create Gitea network ..."
docker network create gitea || true

echo "* Copy manifests and start Gitea ..."
cp -Rv /vagrant/gitea /tmp
docker compose -f /tmp/gitea/gitea-compose.yaml up -d