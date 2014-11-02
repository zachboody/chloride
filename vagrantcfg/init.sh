#!/bin/bash
# Salt configuration

apt-get update
apt-get install python-pip build-essential salt-master python-dev salt-minion -y

cp /vagrant/vagrantcfg/master /etc/salt/master
cp /vagrant/vagrantcfg/minion /etc/salt/minion

/etc/init.d/salt-minion restart

# Python configuration
pip install -r /vagrant/requirements.txt

# Testing modules
pip install websocket-client ipython

salt-key -A -y
/etc/init.d/salt-master restart