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
# Use persistent secret key from environment or generate one
SECRET_KEY_FILE = "/var/lib/light_status/dashboard_secret.key"
if os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, 'r') as f:
        app.secret_key = f.read().strip()
else:
    app.secret_key = secrets.token_hex(32)
    os.makedirs(os.path.dirname(SECRET_KEY_FILE), exist_ok=True)
    with open(SECRET_KEY_FILE, 'w') as f:
        f.write(app.secret_key)

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
    auth_data = dict(request.args)
    
    if verify_telegram_auth(auth_data):
        session['telegram_user_id'] = int(auth_data['id'])
        session['telegram_username'] = auth_data.get('username') or auth_data.get('first_name')
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
    
    # Get status at start of time range (last event before start_time) to extend line backwards
    status_at_start = conn.execute(
        "SELECT status FROM history WHERE channel_id = ? AND timestamp < ? ORDER BY timestamp DESC LIMIT 1",
        (channel_id, start_time)
    ).fetchone()
    
    # Get current status to extend timeline to now
    current_channel = conn.execute(
        "SELECT is_power_on FROM channels WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    
    # Get all history for status lookups (for daily stats calculation)
    all_history = conn.execute(
        "SELECT timestamp, status FROM history WHERE channel_id = ? ORDER BY timestamp",
        (channel_id,)
    ).fetchall()
    
    conn.close()
    
    # Format for charts
    timeline = []
    
    # Add starting point if we have status before the range (to show full line from start)
    if status_at_start and history:
        timeline.append({
            'time': int(start_time * 1000),
            'status': status_at_start['status']
        })
    
    for h in history:
        timeline.append({
            'time': int(h['timestamp'] * 1000),
            'status': h['status']
        })
    
    # Add current status point at "now" to extend the line
    if current_channel and timeline:
        timeline.append({
            'time': int(now.timestamp() * 1000),
            'status': current_channel['is_power_on']
        })
    
    # Calculate daily stats - use all_history to get complete days
    daily_stats = {}
    
    # First, determine which days are in our time range
    days_in_range = set()
    for h in history:
        dt = datetime.fromtimestamp(h['timestamp'], tz)
        days_in_range.add(dt.strftime('%Y-%m-%d'))
    
    # Add today even if no events
    today_str = now.strftime('%Y-%m-%d')
    days_in_range.add(today_str)
    
    # Now get ALL events for those days (not just events in time range)
    for h in all_history:
        dt = datetime.fromtimestamp(h['timestamp'], tz)
        day = dt.strftime('%Y-%m-%d')
        if day in days_in_range:
            if day not in daily_stats:
                daily_stats[day] = {'events': []}
            daily_stats[day]['events'].append({'time': h['timestamp'], 'status': h['status']})
    
    # Get status at start of each day for proper calculation
    for day in list(daily_stats.keys()):
        day_naive = datetime.strptime(day, '%Y-%m-%d')
        day_date = tz.localize(day_naive)
        day_start = day_date.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        
        # Find status at start of this day from all_history
        status_at_day_start = None
        for h in reversed(all_history):
            if h['timestamp'] < day_start:
                status_at_day_start = h['status']
                break
        
        if status_at_day_start is not None:
            daily_stats[day]['status_at_start'] = status_at_day_start
        elif daily_stats[day]['events']:
            # No history before this day, use first event's status
            daily_stats[day]['status_at_start'] = daily_stats[day]['events'][0]['status']
        else:
            # No events and no history, use current status
            daily_stats[day]['status_at_start'] = current_channel['is_power_on'] if current_channel else 0
    
    # Calculate uptime/downtime per day
    for day, data in daily_stats.items():
        events = sorted(data['events'], key=lambda x: x['time'])
        uptime = downtime = 0
        
        # Properly localize the day start time
        day_naive = datetime.strptime(day, '%Y-%m-%d')
        day_date = tz.localize(day_naive)
        day_start = day_date.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        
        # Start from midnight with status at that time
        prev_status = data.get('status_at_start', 0)
        prev_time = day_start
        
        for event in events:
            duration = event['time'] - prev_time
            if prev_status == 1:
                uptime += duration
            else:
                downtime += duration
            
            prev_status = event['status']
            prev_time = event['time']
        
        # Add period from last event (or day start if no events) to end of day (or now if today)
        if day == now.strftime('%Y-%m-%d'):
            # Today: add from last event to now
            end_time = now.timestamp()
        else:
            # Past day: add from last event to end of day (23:59:59)
            end_of_day = day_date.replace(hour=23, minute=59, second=59)
            end_time = end_of_day.timestamp()
        
        ongoing_duration = end_time - prev_time
        if prev_status == 1:
            uptime += ongoing_duration
        else:
            downtime += ongoing_duration
        
        data['uptime'] = uptime
        data['downtime'] = downtime
        del data['events']
        if 'status_at_start' in data:
            del data['status_at_start']
    
    return jsonify({
        'timeline': timeline,
        'daily': daily_stats
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
