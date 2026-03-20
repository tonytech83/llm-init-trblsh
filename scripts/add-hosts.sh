#!/bin/bash

echo "* Adjusting the /etc/hosts file ..."

tee /etc/hosts <<'EOF'
127.0.0.1 localhost

192.168.56.13 target.concept.lab target
192.168.56.14 monitor.concept.lab monitor
192.168.56.15 troubleshooter.concept.lab troubleshooter

# The following lines are desirable for IPv6 capable hosts
::1     ip6-localhost ip6-loopback
fe00::0 ip6-localnet
ff00::0 ip6-mcastprefix
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
EOF