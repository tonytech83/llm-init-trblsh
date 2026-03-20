#!/bin/bash

echo "* Check if Gitea is running and ready ..."
while true; do 
  echo 'Trying to connect to gitea at http://192.168.56.12:3000 ...'; 
  if [ $(curl -s -o /dev/null -w "%{http_code}" http://192.168.56.12:3000) == "200" ]; then 
    echo '... connected.'; 
    break; 
  else 
    echo '... no success. Sleep for 5s and retry ...'; 
    sleep 5; 
  fi 
done

echo "* Create vagrant (with admin role) user in Gitea ..."
docker container exec -u git gitea gitea admin user create --username vagrant --password vagrant --email vagrant@do2.lab --admin

echo "* Configure git ..."
sudo -u vagrant -- git config --global user.name "Vagrant User"
sudo -u vagrant -- git config --global user.email vagrant@do2.lab

echo "* Generate Runner registration token ..."
docker container exec -u git gitea gitea actions generate-runner-token | tee /tmp/gitea/runner-token.txt

echo "* Download Gitea Runner binary ..."
wget -O act_runner -q https://dl.gitea.com/act_runner/0.2.13/act_runner-0.2.13-linux-amd64
install -o root -g root -m 0755 act_runner /usr/local/bin/act_runner

echo "* Register the Gitea Runner ..."
cd /home/vagrant
sudo -u vagrant -- act_runner register --no-interactive --instance http://192.168.56.12:3000 --token $(cat /tmp/gitea/runner-token.txt)

echo "* Create a SystemD service unit for the Gitea Runner ..."
cat > /etc/systemd/system/act_runner.service <<'EOF'
[Unit]
Description=Gitea Actions runner
Documentation=https://gitea.com/gitea/act_runner
After=docker.service

[Service]
ExecStart=/usr/local/bin/act_runner daemon
ExecReload=/bin/kill -s HUP $MAINPID
WorkingDirectory=/home/vagrant
TimeoutSec=0
RestartSec=10
Restart=always
User=vagrant

[Install]
WantedBy=multi-user.target
EOF

echo "* Start the Gitea Runner ..."
systemctl daemon-reload
systemctl enable --now act_runner