#!/bin/bash
# Injected by terraform to bootstrap the EC2: only prepares the "environment", no app code.
# Code / dependencies / starting the service is infra/deploy/deploy.py's job, re-run on every deploy.
set -euxo pipefail

dnf update -y
dnf install -y python3.11 python3.11-pip git

APP_ROOT=/opt/sow-app
mkdir -p "$APP_ROOT"
chown -R ec2-user:ec2-user "$APP_ROOT"

# Create an empty venv up front; deploy.py runs pip install -r requirements.txt into it every deploy.
sudo -u ec2-user python3.11 -m venv "$APP_ROOT/venv"

# systemd service: written and enabled here, but deliberately not started yet --
# /opt/sow-app/app is still empty at this point. The first real start happens in
# deploy.py once the app code has been uploaded.
cat > /etc/systemd/system/sow-app.service <<UNIT
[Unit]
Description=SOW Automation FastAPI app (uvicorn)
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=$APP_ROOT/app/backend
ExecStart=$APP_ROOT/venv/bin/uvicorn app:app --host 0.0.0.0 --port ${app_port}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable sow-app.service

touch /opt/sow-app/PROVISIONED
