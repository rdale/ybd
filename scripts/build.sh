#!/bin/bash

whoami
sudo mkdir -p /src
echo 'base: /src' > ybd/ybd.conf
sudo ybd/ybd.py build-essential x86_64