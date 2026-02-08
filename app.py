#!/usr/bin/env python3
import sqlite3
from flask import Flask, render_template, jsonify
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)
DB_FILE = "/var/lib/light_status/config.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/channels')
def api_channels():
    conn = get_db()
    channels = conn.execute(
        "SELECT channel_id, channel_name, is_power_on, last_request_time, timezone FROM channels WHERE owner_id IS NOT NULL"
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

@app.route('/api/stats/<int:channel_id>')
def api_stats(channel_id):
    conn = get_db()
    
    # Get channel info
    channel = conn.execute(
        "SELECT timezone FROM channels WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    
    tz = pytz.timezone(channel['timezone'])
    now = datetime.now(tz)
    
    # Get history for last 7 days
    week_ago = (now - timedelta(days=7)).timestamp()
    history = conn.execute(
        "SELECT timestamp, status FROM history WHERE channel_id = ? AND timestamp >= ? ORDER BY timestamp",
        (channel_id, week_ago)
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
