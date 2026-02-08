# Light Status Dashboard

Web dashboard for visualizing power status data with interactive charts and Telegram authentication.

## Features

- **Telegram OAuth authentication** - Secure login with your Telegram account
- **Per-user channel access** - See only channels you own
- **Interactive charts** with Chart.js:
  - Status timeline (line chart with step interpolation)
  - Daily uptime bars
  - Daily downtime bars
- **Time range selector** - 24h, 3d, 7d, 14d, 30d
- **Auto-refresh** - Updates every 30 seconds
- **Responsive design** - Works on desktop and mobile

## Requirements

- Python 3.11+
- Access to Light Status Bot database (`/var/lib/light_status/config.db`)
- Domain name configured in @BotFather for Telegram OAuth
- Bot token (same as the monitoring bot)

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Set environment variable with your bot token:

```bash
export BOT_TOKEN="your_bot_token_here"
```

Or configure in systemd service (see Deployment section).

**Configure Telegram OAuth domain:**
1. Go to @BotFather
2. Send `/setdomain`
3. Select your bot
4. Send your domain name (e.g., `yourdomain.com`)

## Run Locally

```bash
export BOT_TOKEN="your_bot_token"
python app.py
```

Dashboard will be available at http://localhost:5000

## Deployment

### Systemd Service

Create `/etc/systemd/system/light-status-dashboard.service`:

```ini
[Unit]
Description=Light Status Dashboard
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/light_status_dashboard
Environment="BOT_TOKEN=your_bot_token_here"
ExecStart=/home/ubuntu/light_status_dashboard/venv/bin/python /home/ubuntu/light_status_dashboard/app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable light-status-dashboard
sudo systemctl start light-status-dashboard
sudo systemctl status light-status-dashboard
```

### Nginx Configuration

Add to your nginx site config:

```nginx
# Dashboard (main site)
location / {
    proxy_pass http://localhost:5000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### SSL Certificate

```bash
sudo certbot --nginx -d yourdomain.com
```

## Architecture

- **Flask** - Web framework
- **Chart.js** - Interactive charts with date-fns adapter
- **SQLite** - Shared database with monitoring bot
- **Telegram Login Widget** - OAuth authentication

## Security

- HMAC-SHA256 verification of Telegram auth data
- Session-based authentication
- Per-user channel access control
- HTTPS required for production (Telegram OAuth requirement)

## Related

**Monitoring Bot:** https://github.com/kostyakozko/light_status_bot

## License

MIT
