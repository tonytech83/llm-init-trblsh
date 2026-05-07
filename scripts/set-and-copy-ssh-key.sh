#!/bin/bash

# 1. Generate the key (no passphrase)
[ -f /home/vagrant/.ssh/troubleshooter_key ] || \
    ssh-keygen -t ed25519 -f /home/vagrant/.ssh/troubleshooter_key -N "" -q

# 2. Fix the permissions
chown vagrant:vagrant /home/vagrant/.ssh/troubleshooter_key*
chmod 600 /home/vagrant/.ssh/troubleshooter_key
chmod 644 /home/vagrant/.ssh/troubleshooter_key.pub

# 3. Install sshpass
echo "* Installing sshpass ..."
apt-get update -q
apt-get install -y sshpass

# 4. Install ssh key to target machine
HOST="192.168.56.13"
KEY="/home/vagrant/.ssh/troubleshooter_key.pub"
USER="vagrant"
PASS="vagrant"

echo "* Install ssh key on $HOST"
sudo -u vagrant sshpass -p "$PASS" ssh-copy-id -i "$KEY" -o StrictHostKeyChecking=no "$USER@$HOST"
