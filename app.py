#!/usr/bin/env python3
import sqlite3
import requests
import hashlib
import hmac
from flask import Flask, render_template, jsonify, session, redirect, url_for, request
from datetime import datetime, timedelta
import pytz
import secrets
import os

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

DB_FILE = "/var/lib/light_status/config.db"
BOT_API_URL = "http://localhost:8080"
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')  # Set via environment variable

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def verify_telegram_auth(auth_data):
    """Verify Telegram login widget data"""
    check_hash = auth_data.get('hash')
    if not check_hash or not BOT_TOKEN:
        return False
    
    auth_data_copy = {k: v for k, v in auth_data.items() if k != 'hash'}
    data_check_string = '\n'.join([f"{k}={v}" for k, v in sorted(auth_data_copy.items())])
    
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    return calculated_hash == check_hash

def check_auth():
    """Check if user is authenticated via Telegram"""
    return session.get('telegram_user_id') is not None

def check_channel_access(user_id, channel_id):
    """Check if user owns the channel"""
    conn = get_db()
    channel = conn.execute(
        "SELECT owner_id FROM channels WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    conn.close()
    
    return channel and channel['owner_id'] == user_id

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
    print(f"Auth callback received: {dict(request.args)}")  # Debug
    auth_data = dict(request.args)
    
    # If no auth data, show what we received
    if not auth_data:
        return f"No auth data received. Request args: {request.args}, Full URL: {request.url}"
    
    if verify_telegram_auth(auth_data):
        session['telegram_user_id'] = int(auth_data['id'])
        session['telegram_username'] = auth_data.get('username') or auth_data.get('first_name')
        print(f"Auth successful for user {session['telegram_user_id']}")  # Debug
        return redirect(url_for('index'))
    
    print("Auth verification failed")  # Debug
    return f"Auth verification failed. Data: {auth_data}"

@app.route('/auth/test')
def auth_test():
    """Test auth bypass - REMOVE IN PRODUCTION"""
    # Hardcode your Telegram ID for testing
    session['telegram_user_id'] = 31175686  # Your user ID from the database
    session['telegram_username'] = 'test_user'
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/channels')
def api_channels():
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['telegram_user_id']
    
    # Get only user's channels
    conn = get_db()
    channels = conn.execute(
        "SELECT channel_id, channel_name, is_power_on, last_request_time FROM channels WHERE owner_id = ?",
        (user_id,)
    ).fetchall()
    conn.close()
    
    result = []
    for ch in channels:
        result.append({
            'id': ch['channel_id'],
            'name': ch['channel_name'] or f"Channel {ch['channel_id']}",
            'status': 'online' if ch['is_power_on'] else 'offline',
            'last_ping': ch['last_request_time']
        })
    return jsonify(result)

@app.route('/api/stats/<channel_id>')
def api_stats(channel_id):
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        channel_id = int(channel_id)
    except ValueError:
        return jsonify({'error': 'Invalid channel ID'}), 400
    
    user_id = session['telegram_user_id']
    
    # Check access
    if not check_channel_access(user_id, channel_id):
        return jsonify({'error': 'Access denied'}), 403
    
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
