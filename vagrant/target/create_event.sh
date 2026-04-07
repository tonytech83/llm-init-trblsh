#!/bin/bash

clear

echo "Stop dummy-fail.service ..."
sudo systemctl stop dummy-fail.service

echo "Reset the fail for dummy-fail.service ..."
sudo systemctl reset-failed dummy-fail.service

echo "Check failed services ..."
systemctl list-units --state=failed

echo "Start dummy-fail.service ..."
sudo systemctl start dummy-fail.service

echo "WE SHOULD HAVE FAILED SERVICE :)"
sleep 5s
systemctl list-units --state=failed