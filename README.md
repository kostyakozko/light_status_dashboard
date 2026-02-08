# Power Status Dashboard

Separate web dashboard for visualizing power status statistics with charts.

## Features

- Channel selector dropdown
- Status timeline (7 days)
- Daily uptime/downtime bar charts
- Auto-refresh every 30 seconds
- Responsive design

## Installation

```bash
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Dashboard will be available at http://localhost:5000

## Deployment

Create systemd service at `/etc/systemd/system/light-status-dashboard.service`:

```ini
[Unit]
Description=Light Status Dashboard
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/light_status_dashboard
ExecStart=/usr/bin/python3 /home/ubuntu/light_status_dashboard/app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable light-status-dashboard
sudo systemctl start light-status-dashboard
```
