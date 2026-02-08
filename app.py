#!/usr/bin/env python3
import sqlite3
import requests
from flask import Flask, render_template, jsonify, session, redirect, url_for, request
from datetime import datetime, timedelta
import pytz
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

DB_FILE = "/var/lib/light_status/config.db"
BOT_API_URL = "http://localhost:8080"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def check_auth():
    """Check if user is authenticated via Telegram"""
    return session.get('telegram_user_id') is not None

@app.route('/')
def index():
    if not check_auth():
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/auth/telegram')
def auth_telegram():
    """Handle Telegram OAuth callback"""
    # Get Telegram auth data from query params
    telegram_id = request.args.get('id')
    first_name = request.args.get('first_name')
    username = request.args.get('username')
    auth_date = request.args.get('auth_date')
    hash_value = request.args.get('hash')
    
    # TODO: Verify hash with bot token
    # For now, just accept if telegram_id exists
    if telegram_id:
        session['telegram_user_id'] = int(telegram_id)
        session['telegram_username'] = username or first_name
        return redirect(url_for('index'))
    
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/channels')
def api_channels():
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Proxy to bot API
    try:
        resp = requests.get(f"{BOT_API_URL}/api/channels", timeout=5)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats/<int:channel_id>')
def api_stats(channel_id):
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    days = request.args.get('days', 7, type=int)
    
    conn = get_db()
    
    # Get channel info
    channel = conn.execute(
        "SELECT timezone FROM channels WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    
    tz = pytz.timezone(channel['timezone'])
    now = datetime.now(tz)
    
    # Get history
    start_time = (now - timedelta(days=days)).timestamp()
    history = conn.execute(
        "SELECT timestamp, status FROM history WHERE channel_id = ? AND timestamp >= ? ORDER BY timestamp",
        (channel_id, start_time)
    ).fetchall()
    
    conn.close()
    
    # Format for charts
    timeline = []
    for h in history:
        timeline.append({
            'time': int(h['timestamp'] * 1000),
            'status': h['status']
        })
    
    # Calculate daily stats
    daily_stats = {}
    for h in history:
        dt = datetime.fromtimestamp(h['timestamp'], tz)
        day = dt.strftime('%Y-%m-%d')
        if day not in daily_stats:
            daily_stats[day] = {'online': 0, 'offline': 0, 'events': []}
        daily_stats[day]['events'].append({'time': h['timestamp'], 'status': h['status']})
    
    # Calculate uptime/downtime per day
    for day, data in daily_stats.items():
        events = sorted(data['events'], key=lambda x: x['time'])
        uptime = downtime = 0
        
        for i in range(len(events) - 1):
            duration = events[i+1]['time'] - events[i]['time']
            if events[i]['status'] == 1:
                uptime += duration
            else:
                downtime += duration
        
        data['uptime'] = uptime
        data['downtime'] = downtime
        del data['events']
    
    return jsonify({
        'timeline': timeline,
        'daily': daily_stats
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
