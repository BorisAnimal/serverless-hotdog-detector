#!/bin/bash

export AWS_ACCESS_KEY_ID=<TODO>
export AWS_SECRET_ACCESS_KEY=<TODO>
export TELEGRAM_TOKEN=<TODO>

echo " install npm"
sudo apt install nodejs

echo "install deploy tool"
npm install -g serverless

echo "install python packages from requirements.txt to folder .vendored/"
pip install -r requirements.txt -t vendored
