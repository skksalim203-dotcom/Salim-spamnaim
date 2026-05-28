import os, sys, time, json, ssl, socket, threading, asyncio, base64, binascii, re, jwt, pickle
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

import requests
import urllib3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from google.protobuf.timestamp_pb2 import Timestamp

# custom project modules
from byte import *
from byte import xSEndMsg, Auth_Chat
from xHeaders import *
from black9 import openroom, spmroom
import xKEys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== ফ্লাস্ক অ্যাপ ====================
app = Flask(__name__)
CORS(app)

# ==================== গ্লোবাল ভেরিয়েবল ====================
connected_clients = {}
connected_clients_lock = threading.Lock()
active_power_targets = {}
active_power_lock = threading.Lock()
spam_threads = {}
spam_threads_lock = threading.Lock()

C = "\033[96m"
G = "\033[92m"
Y = "\033[93m"
R = "\033[91m"
RS = "\033[0m"
BOLD = "\033[1m"

# ==================== স্প্যাম ফাংশন ====================
def spam_worker(target_id, duration_minutes=None):
    print(f"\n{C}{'='*60}{RS}")
    print(f"{G}🎯 SPAM STARTED ON: {BOLD}{target_id}{RS}")
    print(f"{C}{'='*60}{RS}\n")
    
    # Console log for web UI
    add_console_log(f"🚀 SPAM STARTED ON: {target_id}", "success")

    start_time = datetime.now()
    total_requests = 0
    round_number = 0

    while True:
        with active_power_lock:
            if target_id not in active_power_targets:
                break

        with connected_clients_lock:
            clients_list = list(connected_clients.values())

        if not clients_list:
            add_console_log(f"⚠️ No active clients available, waiting...", "warning")
            time.sleep(2)
            continue

        round_number += 1
        round_requests = 0

        for idx, client in enumerate(clients_list, 1):
            with active_power_lock:
                if target_id not in active_power_targets:
                    break

            account_id = getattr(client, 'id', 'Unknown')

            try:
                if (hasattr(client, 'CliEnts2') and client.CliEnts2 and
                    hasattr(client, 'key') and client.key and
                    hasattr(client, 'iv') and client.iv):

                    try:
                        open_pkt = openroom(client.key, client.iv)
                        if open_pkt:
                            client.CliEnts2.send(open_pkt)
                    except:
                        pass

                    for i in range(1, 11):
                        with active_power_lock:
                            if target_id not in active_power_targets:
                                break
                        try:
                            spam_pkt = spmroom(client.key, client.iv, target_id)
                            if spam_pkt:
                                client.CliEnts2.send(spam_pkt)
                                total_requests += 1
                                round_requests += 1
                                
                                if total_requests % 50 == 0:
                                    add_console_log(f"📊 Total requests sent: {total_requests}", "info")
                                    
                        except (BrokenPipeError, ConnectionResetError, OSError):
                            with connected_clients_lock:
                                if account_id in connected_clients:
                                    del connected_clients[account_id]
                            add_console_log(f"❌ Client {account_id} disconnected", "error")
                            break
                        except:
                            break
            except:
                pass

            if idx < len(clients_list):
                time.sleep(0.5)

        if round_requests > 0:
            add_console_log(f"📈 Round {round_number}: {round_requests} requests sent to {target_id}", "info")

        if duration_minutes:
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed >= duration_minutes * 60:
                with active_power_lock:
                    if target_id in active_power_targets:
                        del active_power_targets[target_id]
                add_console_log(f"⏰ Duration completed for {target_id}", "info")
                break

        time.sleep(0.3)

    with spam_threads_lock:
        if target_id in spam_threads:
            del spam_threads[target_id]

    print(f"\n{R}{'='*50}{RS}")
    print(f"{R}🛑 SPAM STOPPED ON: {target_id}{RS}")
    print(f"{R}{'='*50}{RS}\n")
    add_console_log(f"🛑 SPAM STOPPED ON: {target_id} (Total: {total_requests} requests)", "error")

# Console log storage for web UI
console_logs = []
console_logs_lock = threading.Lock()

def add_console_log(message, log_type="info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    with console_logs_lock:
        console_logs.append({
            'timestamp': timestamp,
            'message': message,
            'type': log_type
        })
        # Keep last 100 logs
        while len(console_logs) > 100:
            console_logs.pop(0)

def get_console_logs():
    with console_logs_lock:
        return console_logs.copy()

def clear_console_logs():
    with console_logs_lock:
        console_logs.clear()

def start_spam(target_id, duration_minutes=None):
    with active_power_lock:
        if target_id in active_power_targets:
            return False, f"Already spamming on: {target_id}"
        active_power_targets[target_id] = {
            'active': True,
            'start_time': datetime.now(),
            'duration': duration_minutes,
        }

    thread = Thread(target=spam_worker, args=(target_id, duration_minutes), daemon=True)
    with spam_threads_lock:
        spam_threads[target_id] = thread
    thread.start()
    return True, f"Spam started on: {target_id}"

def stop_spam(target_id):
    with active_power_lock:
        if target_id in active_power_targets:
            del active_power_targets[target_id]
            add_console_log(f"🛑 Stop command received for {target_id}", "error")
            return True, f"Spam stopped on: {target_id}"
        return False, f"No active spam on: {target_id}"

def stop_all_spam():
    with active_power_lock:
        targets = list(active_power_targets.keys())
        for target in targets:
            del active_power_targets[target]
    add_console_log(f"🛑 Stopped all spam ({len(targets)} targets)", "error")
    return True, f"Stopped all spam ({len(targets)} targets)"

def get_status():
    with active_power_lock:
        active_targets = list(active_power_targets.keys())
        targets_info = []
        for target in active_targets:
            info = active_power_targets[target]
            duration = info.get('duration')
            start_time = info.get('start_time')
            elapsed = (datetime.now() - start_time).total_seconds() if start_time else 0
            targets_info.append({
                'uid': target,
                'duration': duration,
                'elapsed_minutes': int(elapsed / 60),
                'is_unlimited': duration is None
            })
    
    with connected_clients_lock:
        accounts_count = len(connected_clients)
        accounts_list = list(connected_clients.keys())
    
    return {
        'active_targets': targets_info,
        'active_count': len(active_targets),
        'accounts_count': accounts_count,
        'accounts_list': accounts_list[:50]
    }

# ==================== ফ্লাস্ক রাউট ====================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/start', methods=['POST'])
def api_start():
    data = request.get_json()
    target_id = data.get('uid', '').strip()
    duration = data.get('duration')
    
    if not target_id:
        return jsonify({'success': False, 'message': 'UID is required'})
    
    if not target_id.isdigit():
        return jsonify({'success': False, 'message': 'UID must contain only numbers'})
    
    success, message = start_spam(target_id, duration)
    return jsonify({'success': success, 'message': message})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    data = request.get_json()
    target_id = data.get('uid', '').strip()
    
    if not target_id:
        return jsonify({'success': False, 'message': 'UID is required'})
    
    success, message = stop_spam(target_id)
    return jsonify({'success': success, 'message': message})

@app.route('/api/stop-all', methods=['POST'])
def api_stop_all():
    success, message = stop_all_spam()
    return jsonify({'success': success, 'message': message})

@app.route('/api/status', methods=['GET'])
def api_status():
    status = get_status()
    return jsonify({'success': True, 'data': status})

@app.route('/api/accounts', methods=['GET'])
def api_accounts():
    with connected_clients_lock:
        return jsonify({
            'success': True,
            'count': len(connected_clients),
            'accounts': list(connected_clients.keys())
        })

@app.route('/api/logs', methods=['GET'])
def api_logs():
    return jsonify({
        'success': True,
        'logs': get_console_logs()
    })

@app.route('/api/clear-logs', methods=['POST'])
def api_clear_logs():
    clear_console_logs()
    return jsonify({'success': True, 'message': 'Logs cleared'})

# ==================== HTML টেমপ্লেট ====================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SALIM POWER SPAM - Ultimate Control Panel</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    
    <style>
        :root {
            --bg-color: linear-gradient(135deg, #0a0f1e 0%, #0a0a1a 100%);
            --card-bg: rgba(17, 24, 38, 0.95);
            --text-main: #ffffff;
            --text-muted: #8b9bb4;
            --primary-blue: #00d4ff;
            --secondary-blue: #0051ff;
            --dark-blue: rgba(26, 35, 51, 0.95);
            --border-color: #233045;
            --danger: #ff3366;
            --danger-glow: rgba(255, 51, 102, 0.4);
            --success: #00cc66;
            --success-glow: rgba(0, 204, 102, 0.4);
            --warning: #ffaa00;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Poppins', sans-serif; }
        
        body { 
            background: var(--bg-color);
            color: var(--text-main); 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            min-height: 100vh; 
            padding: 20px; 
            overflow-x: hidden;
            position: relative;
        }
        
        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y="1em" font-size="8" fill="rgba(0,212,255,0.03)">SALIM</text></svg>');
            background-size: 50px 50px;
            pointer-events: none;
            z-index: -1;
        }
        
        #matrix-canvas { 
            position: fixed; 
            top: 0; 
            left: 0; 
            width: 100vw; 
            height: 100vh; 
            z-index: -1; 
            opacity: 0.3;
        }

        .app-container { 
            width: 100%; 
            max-width: 480px; 
            padding: 30px 20px; 
            display: flex; 
            flex-direction: column; 
            gap: 25px; 
            background: rgba(9, 14, 23, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 30px; 
            border: 1px solid rgba(0, 212, 255, 0.2);
            box-shadow: 0 0 60px rgba(0, 212, 255, 0.1);
            z-index: 1; 
            animation: fadeIn 0.5s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .header { text-align: center; margin-bottom: 15px; }
        
        .premium-badge { 
            color: #ffd700; 
            font-size: 0.85rem; 
            font-weight: 600; 
            letter-spacing: 3px;
            display: flex; 
            justify-content: center; 
            align-items: center; 
            gap: 10px; 
            margin-bottom: 10px;
        }
        
        .main-title { 
            font-size: 3.5rem; 
            font-weight: 800; 
            letter-spacing: 3px;
            background: linear-gradient(135deg, var(--primary-blue), var(--secondary-blue), #00ffcc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0 0 30px var(--glow-blue);
            margin: 15px 0;
            line-height: 1.1;
        }
        
        .sub-title { 
            color: var(--text-muted); 
            font-size: 0.75rem; 
            letter-spacing: 4px;
            text-transform: uppercase;
            display: flex; 
            justify-content: center; 
            align-items: center; 
            gap: 15px;
        }
        
        .skull-icon { 
            display: block; 
            color: var(--primary-blue); 
            margin-top: 20px; 
            font-size: 2rem;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; text-shadow: 0 0 10px var(--primary-blue); }
            50% { opacity: 0.7; text-shadow: 0 0 20px var(--primary-blue); }
        }

        .card { 
            background-color: var(--card-bg); 
            border-radius: 24px; 
            padding: 25px 20px; 
            border: 1px solid var(--border-color); 
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-2px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.6);
        }
        
        .card-header { 
            display: flex; 
            align-items: center; 
            gap: 15px; 
            margin-bottom: 20px;
        }
        
        .icon-circle { 
            width: 45px; 
            height: 45px; 
            border-radius: 50%; 
            background: linear-gradient(135deg, var(--secondary-blue), var(--primary-blue));
            display: flex; 
            justify-content: center; 
            align-items: center; 
            color: white; 
            font-size: 1.3rem;
        }
        
        .card-title h3 { font-size: 1.2rem; font-weight: 600; }
        .card-title p { font-size: 0.7rem; color: var(--text-muted); letter-spacing: 1px; text-transform: uppercase; }

        .input-group { margin-bottom: 20px; }
        
        .input-label { 
            display: flex; 
            align-items: center; 
            gap: 8px; 
            color: var(--text-muted); 
            font-size: 0.85rem; 
            margin-bottom: 8px;
            font-weight: 500;
        }
        
        .method-selector { 
            display: flex; 
            gap: 15px; 
            margin-bottom: 20px; 
            padding: 5px; 
        }
        
        .method-option { 
            flex: 1; 
            position: relative; 
        }
        
        .method-option input { 
            position: absolute; 
            opacity: 0; 
            cursor: pointer; 
        }
        
        .method-label { 
            display: block; 
            background: rgba(9, 14, 23, 0.8); 
            border: 2px solid var(--border-color); 
            padding: 12px; 
            border-radius: 14px; 
            text-align: center; 
            font-size: 0.9rem; 
            font-weight: 600;
            cursor: pointer; 
            transition: 0.3s; 
            color: var(--text-muted);
        }
        
        .method-option input:checked + .method-label { 
            border-color: var(--primary-blue); 
            color: var(--primary-blue); 
            background: rgba(0, 212, 255, 0.15);
            box-shadow: 0 0 15px rgba(0, 212, 255, 0.2);
        }

        input[type="text"].plain-input { 
            width: 100%; 
            background-color: rgba(9, 14, 23, 0.9); 
            border: 2px solid var(--border-color); 
            color: white; 
            padding: 15px; 
            border-radius: 14px; 
            font-size: 1rem; 
            outline: none; 
            transition: 0.3s;
            font-weight: 500;
        }
        
        input[type="text"].plain-input:focus { 
            border-color: var(--primary-blue); 
            box-shadow: 0 0 15px rgba(0, 212, 255, 0.3);
        }
        
        input[type="text"].plain-input::placeholder {
            color: rgba(255,255,255,0.3);
        }

        .btn { 
            width: 100%; 
            padding: 15px; 
            border: none; 
            border-radius: 14px; 
            font-size: 1rem; 
            font-weight: 700; 
            cursor: pointer; 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            gap: 10px; 
            transition: 0.3s; 
            margin-top: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .btn-primary { 
            background: linear-gradient(135deg, var(--secondary-blue), var(--primary-blue));
            color: white;
            margin-bottom: 15px;
            box-shadow: 0 5px 20px rgba(0, 81, 255, 0.3);
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 81, 255, 0.4);
        }
        
        .btn-primary:active {
            transform: translateY(0);
        }
        
        .btn-danger { 
            background: linear-gradient(135deg, #ff1a4f, #ff3366);
            color: white;
            margin-bottom: 15px;
            box-shadow: 0 5px 20px rgba(255, 51, 102, 0.3);
        }
        
        .btn-danger:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(255, 51, 102, 0.4);
        }
        
        .btn-outline { 
            background-color: transparent; 
            border: 2px solid var(--border-color);
            color: var(--text-muted);
        }
        
        .btn-outline:hover {
            border-color: var(--warning);
            color: var(--warning);
        }

        .console-box {
            background: rgba(0, 0, 0, 0.95);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            height: 250px;
            padding: 15px;
            font-family: 'Courier New', monospace;
            font-size: 0.75rem;
            overflow-y: auto;
            overflow-x: hidden;
        }
        
        .console-box::-webkit-scrollbar {
            width: 6px;
        }
        
        .console-box::-webkit-scrollbar-track {
            background: rgba(255,255,255,0.05);
            border-radius: 3px;
        }
        
        .console-box::-webkit-scrollbar-thumb {
            background: var(--primary-blue);
            border-radius: 3px;
        }
        
        .console-line { 
            margin-bottom: 6px; 
            font-family: monospace;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            padding-bottom: 4px;
        }
        
        .console-line span.time { 
            color: var(--text-muted); 
            margin-right: 10px;
            font-size: 0.7rem;
        }
        
        .console-line span.success { 
            color: var(--success);
            font-weight: bold;
        }
        
        .console-line span.error { 
            color: var(--danger);
            font-weight: bold;
        }
        
        .console-line span.warning { 
            color: var(--warning);
            font-weight: bold;
        }
        
        .console-line span.info { 
            color: var(--primary-blue);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-top: 15px;
        }
        
        .stat-card {
            background: rgba(0, 212, 255, 0.05);
            border: 1px solid rgba(0, 212, 255, 0.2);
            border-radius: 14px;
            padding: 12px;
            text-align: center;
        }
        
        .stat-number {
            font-size: 1.8rem;
            font-weight: 800;
            color: var(--primary-blue);
        }
        
        .stat-label {
            font-size: 0.7rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .active-target {
            background: rgba(255, 51, 102, 0.1);
            border: 1px solid var(--danger);
            border-radius: 12px;
            padding: 10px;
            margin-top: 10px;
            font-size: 0.8rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .status-badge {
            background: rgba(0, 204, 102, 0.1);
            border: 1px solid var(--success);
            border-radius: 14px;
            padding: 12px;
            text-align: center;
            font-size: 0.85rem;
            font-weight: 600;
            margin-top: 15px;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
        }
        
        .status-dot {
            width: 10px;
            height: 10px;
            background-color: var(--success);
            border-radius: 50%;
            box-shadow: 0 0 12px var(--success);
            animation: blink 1s infinite;
        }
        
        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        .copyright {
            text-align: center;
            color: var(--text-muted);
            font-size: 0.7rem;
            margin-top: 20px;
            padding-top: 15px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }
        
        .btn-icon-only {
            width: auto;
            padding: 10px 15px;
            background: rgba(0,212,255,0.1);
            border: 1px solid var(--primary-blue);
            border-radius: 10px;
            cursor: pointer;
            transition: 0.3s;
        }
        
        .btn-icon-only:hover {
            background: rgba(0,212,255,0.2);
        }
        
        .flex-between {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .spinning {
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        
        .toast {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: var(--card-bg);
            border-left: 4px solid var(--success);
            padding: 12px 20px;
            border-radius: 10px;
            font-size: 0.85rem;
            animation: slideIn 0.3s ease;
            z-index: 1000;
        }
        
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
    </style>
</head>
<body>

    <canvas id="matrix-canvas"></canvas>

    <div id="home-page" class="app-container">
        <header class="header">
            <div class="premium-badge"><i class="fa-solid fa-crown"></i> PREMIUM UNLIMITED</div>
            <h1 class="main-title">SALIM<br>POWER</h1>
            <div class="sub-title"><i class="fa-solid fa-skull"></i> SPAM SYSTEM <i class="fa-solid fa-bolt"></i></div>
            <i class="fa-solid fa-skull skull-icon"></i>
        </header>

        <div class="card">
            <div class="card-header">
                <div class="icon-circle"><i class="fa-solid fa-bolt"></i></div>
                <div class="card-title">
                    <h3>Attack Control</h3>
                    <p>Real-time Spam System</p>
                </div>
            </div>

            <!-- Region Selection -->
            <div class="input-label"><i class="fa-solid fa-earth-asia"></i> SELECT REGION</div>
            <div class="method-selector">
                <label class="method-option">
                    <input type="radio" name="region" value="Bangladesh" checked>
                    <span class="method-label">🇧🇩 Bangladesh</span>
                </label>
            </div>

            <div class="input-group">
                <div class="input-label"><i class="fa-solid fa-crosshairs"></i> TARGET USER ID</div>
                <input type="text" id="targetUidInput" class="plain-input" 
                       placeholder="Enter Game UID (numbers only)" 
                       inputmode="numeric">
            </div>
            
            <button class="btn btn-primary" id="startBtn" onclick="startSpam()">
                <i class="fa-solid fa-fire"></i> START SPAM
            </button>
            
            <button class="btn btn-danger" id="stopBtn" onclick="stopSpam()">
                <i class="fa-solid fa-power-off"></i> STOP SPAM
            </button>
            
            <button class="btn btn-outline" onclick="stopAllSpam()">
                <i class="fa-solid fa-ban"></i> STOP ALL
            </button>
        </div>

        <div class="card">
            <div class="card-header">
                <div class="icon-circle"><i class="fa-solid fa-terminal"></i></div>
                <div class="card-title">
                    <h3>Console Box</h3>
                    <p>Real-time Attack Logs</p>
                </div>
            </div>
            <div class="console-box" id="consoleBox">
                <div class="console-line"><span class="time">[System]</span> <span class="info">SALIM POWER SPAM SYSTEM LOADED</span></div>
                <div class="console-line"><span class="time">[System]</span> <span class="success">Ready for attack!</span></div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number" id="activeTargetsCount">0</div>
                    <div class="stat-label">Active Attacks</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="accountsCount">0</div>
                    <div class="stat-label">Online Accounts</div>
                </div>
            </div>
            
            <div id="activeTargetsList"></div>
            
            <div class="status-badge">
                <div class="status-dot"></div>
                <span>SYSTEM ACTIVE & READY</span>
            </div>
        </div>

        <div class="copyright">
            <i class="fa-solid fa-skull"></i> SALIM POWER SPAM v3.0 | Premium Unlimited Access <i class="fa-solid fa-bolt"></i>
        </div>
    </div>

    <script>
        let autoRefreshInterval = null;
        
        // Canvas Matrix Effect
        const canvas = document.getElementById('matrix-canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        const matrixChars = '01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン'.split('');
        const fontSize = 14;
        const columns = canvas.width / fontSize;
        const drops = Array(Math.floor(columns)).fill(1);

        function drawMatrix() {
            ctx.fillStyle = 'rgba(0, 0, 0, 0.04)';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#00d4ff';
            ctx.font = fontSize + 'px monospace';
            ctx.shadowBlur = 0;
            drops.forEach((y, i) => {
                const text = matrixChars[Math.floor(Math.random() * matrixChars.length)];
                ctx.fillText(text, i * fontSize, y * fontSize);
                if (y * fontSize > canvas.height && Math.random() > 0.975) drops[i] = 0;
                drops[i]++;
            });
        }
        setInterval(drawMatrix, 50);
        
        window.addEventListener('resize', () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        });

        // Console Functions
        function logToConsole(message, type = 'info') {
            const consoleBox = document.getElementById('consoleBox');
            const now = new Date();
            const timeStr = now.getHours().toString().padStart(2, '0') + ':' + 
                          now.getMinutes().toString().padStart(2, '0') + ':' + 
                          now.getSeconds().toString().padStart(2, '0');
            
            const line = document.createElement('div');
            line.className = 'console-line';
            line.innerHTML = `<span class="time">[${timeStr}]</span> <span class="${type}">${message}</span>`;
            
            consoleBox.appendChild(line);
            line.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            
            // Auto scroll
            consoleBox.scrollTop = consoleBox.scrollHeight;
        }

        // Show Toast Message
        function showToast(message, isError = false) {
            const toast = document.createElement('div');
            toast.className = 'toast';
            toast.style.borderLeftColor = isError ? '#ff3366' : '#00cc66';
            toast.innerHTML = `<i class="fa-solid ${isError ? 'fa-circle-exclamation' : 'fa-circle-check'}"></i> ${message}`;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }

        // API Functions
        async function startSpam() {
            const uid = document.getElementById('targetUidInput').value.trim();
            const startBtn = document.getElementById('startBtn');
            
            if (!uid) {
                logToConsole('❌ Please enter a target UID!', 'error');
                showToast('Please enter a target UID!', true);
                return;
            }
            
            if (!/^\\d+$/.test(uid)) {
                logToConsole('❌ UID must contain only numbers!', 'error');
                showToast('UID must contain only numbers!', true);
                return;
            }
            
            startBtn.innerHTML = '<i class="fa-solid fa-spinner spinning"></i> STARTING...';
            startBtn.disabled = true;
            
            try {
                const response = await fetch('/api/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ uid: uid, duration: null })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    logToConsole(`✅ ${data.message}`, 'success');
                    showToast(data.message);
                    document.getElementById('targetUidInput').value = '';
                } else {
                    logToConsole(`❌ ${data.message}`, 'error');
                    showToast(data.message, true);
                }
            } catch (error) {
                logToConsole(`❌ Network error: ${error.message}`, 'error');
                showToast('Network error!', true);
            } finally {
                startBtn.innerHTML = '<i class="fa-solid fa-fire"></i> START SPAM';
                startBtn.disabled = false;
            }
            
            updateStatus();
        }
        
        async function stopSpam() {
            const uid = document.getElementById('targetUidInput').value.trim();
            
            if (!uid) {
                logToConsole('❌ Please enter a target UID to stop!', 'error');
                showToast('Please enter a target UID!', true);
                return;
            }
            
            try {
                const response = await fetch('/api/stop', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ uid: uid })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    logToConsole(`🛑 ${data.message}`, 'error');
                    showToast(data.message);
                } else {
                    logToConsole(`⚠️ ${data.message}`, 'warning');
                    showToast(data.message, true);
                }
            } catch (error) {
                logToConsole(`❌ Network error: ${error.message}`, 'error');
            }
            
            updateStatus();
        }
        
        async function stopAllSpam() {
            try {
                const response = await fetch('/api/stop-all', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                const data = await response.json();
                
                if (data.success) {
                    logToConsole(`🛑 ${data.message}`, 'error');
                    showToast(data.message);
                }
            } catch (error) {
                logToConsole(`❌ Network error: ${error.message}`, 'error');
            }
            
            updateStatus();
        }
        
        async function updateStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                if (data.success) {
                    const status = data.data;
                    
                    document.getElementById('activeTargetsCount').innerText = status.active_count;
                    document.getElementById('accountsCount').innerText = status.accounts_count;
                    
                    const targetsList = document.getElementById('activeTargetsList');
                    if (status.active_targets.length > 0) {
                        targetsList.innerHTML = status.active_targets.map(target => `
                            <div class="active-target">
                                <span><i class="fa-solid fa-bullseye"></i> ${target.uid}</span>
                                <span style="font-size:0.7rem;">
                                    ${target.is_unlimited ? '∞ UNLIMITED' : `${target.elapsed_minutes}/${target.duration} min`}
                                </span>
                            </div>
                        `).join('');
                    } else {
                        targetsList.innerHTML = '<div class="active-target" style="text-align:center; color:#8b9bb4;">No active attacks</div>';
                    }
                }
            } catch (error) {
                console.error('Status update error:', error);
            }
        }
        
        async function fetchLogs() {
            try {
                const response = await fetch('/api/logs');
                const data = await response.json();
                
                if (data.success && data.logs.length > 0) {
                    const consoleBox = document.getElementById('consoleBox');
                    // Clear only if we have new logs (don't clear, just update)
                    if (data.logs.length > 0) {
                        consoleBox.innerHTML = data.logs.map(log => `
                            <div class="console-line">
                                <span class="time">[${log.timestamp}]</span>
                                <span class="${log.type}">${escapeHtml(log.message)}</span>
                            </div>
                        `).join('');
                        consoleBox.scrollTop = consoleBox.scrollHeight;
                    }
                }
            } catch (error) {
                console.error('Log fetch error:', error);
            }
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Auto refresh status and logs
        setInterval(updateStatus, 2000);
        setInterval(fetchLogs, 1000);
        
        // Initial load
        updateStatus();
        
        // Enter key support
        document.getElementById('targetUidInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                startSpam();
            }
        });
        
        logToConsole('💀 SALIM POWER SPAM SYSTEM READY', 'success');
        logToConsole('📡 Waiting for attack commands...', 'info');
    </script>
</body>
</html>
'''

# ==================== অ্যাকাউন্ট লোড ====================
ACCOUNTS = []

def load_accounts_from_file(filename="accs.txt"):
    accounts = []
    try:
        with open(filename, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith("#"):
                    if ":" in line:
                        parts = line.split(":")
                        accounts.append({'id': parts[0].strip(), 'password': parts[1].strip()})
                    else:
                        accounts.append({'id': line.strip(), 'password': ''})
        print(f"{G}📦 Loaded {len(accounts)} accounts{RS}")
        add_console_log(f"📦 Loaded {len(accounts)} accounts from accs.txt", "success")
    except FileNotFoundError:
        print(f"{Y}⚠️ accs.txt not found! Creating sample file...{RS}")
        with open(filename, "w") as f:
            f.write("# accs.txt - Format: UID:PASSWORD\n")
            f.write("# Example: 4575104506:password123\n")
            f.write("4575104506:examplepass\n")
        add_console_log("⚠️ accs.txt created, please add your accounts", "warning")
    return accounts

ACCOUNTS = load_accounts_from_file()

# ==================== FF Client ====================
class FF_CLient():
    def __init__(self, id, password):
        self.id = id
        self.password = password
        self.key = None
        self.iv = None
        add_console_log(f"🔐 Initializing account: {id}", "info")
        self.Get_FiNal_ToKen_0115()

    def Connect_SerVer_OnLine(self, Token, tok, host, port, key, iv, host2, port2):
        try:
            self.AutH_ToKen_0115 = tok    
            self.CliEnts2 = socket.create_connection((host2, int(port2)))
            self.CliEnts2.send(bytes.fromhex(self.AutH_ToKen_0115))
            with connected_clients_lock:
                if self.id not in connected_clients:
                    connected_clients[self.id] = self
                    print(f"{G}✅ Online: {self.id} (Total: {len(connected_clients)}){RS}")
                    add_console_log(f"✅ Account {self.id} is now ONLINE", "success")
        except Exception as e:
            print(f"{R}❌ Online error {self.id}: {e}{RS}")
            add_console_log(f"❌ Online error {self.id}: {e}", "error")
            return
        while True:
            try:
                self.DaTa2 = self.CliEnts2.recv(99999)
                if '0500' in self.DaTa2.hex()[0:4] and len(self.DaTa2.hex()) > 30:
                    self.packet = json.loads(DeCode_PackEt(f'08{self.DaTa2.hex().split("08", 1)[1]}'))
                    self.AutH = self.packet['5']['data']['7']['data']
            except: pass
                                                            
    def Connect_SerVer(self, Token, tok, host, port, key, iv, host2, port2):
        self.AutH_ToKen_0115 = tok    
        self.CliEnts = socket.create_connection((host, int(port)))
        self.CliEnts.send(bytes.fromhex(self.AutH_ToKen_0115))  
        self.DaTa = self.CliEnts.recv(1024)          	        
        threading.Thread(target=self.Connect_SerVer_OnLine, args=(Token, tok, host, port, key, iv, host2, port2)).start()
        try: self.Exemple = xMsGFixinG('12345678')
        except: pass
        self.key = key
        self.iv = iv
        with connected_clients_lock:
            if self.id not in connected_clients:
                connected_clients[self.id] = self
                print(f"{G}✅ Registered: {self.id}{RS}")
                add_console_log(f"✅ Account {self.id} registered successfully", "success")
        while True:      
            try:
                self.DaTa = self.CliEnts.recv(1024)   
                if len(self.DaTa) == 0 or (hasattr(self, 'DaTa2') and len(self.DaTa2) == 0):
                    try:
                        self.CliEnts.close()
                        if hasattr(self, 'CliEnts2'): self.CliEnts2.close()
                        self.Connect_SerVer(Token, tok, host, port, key, iv, host2, port2)                    		                    
                    except:
                        try:
                            self.CliEnts.close()
                            if hasattr(self, 'CliEnts2'): self.CliEnts2.close()
                            self.Connect_SerVer(Token, tok, host, port, key, iv, host2, port2)
                        except:
                            self.CliEnts.close()
                            if hasattr(self, 'CliEnts2'): self.CliEnts2.close()
                            ResTarT_BoT()	            
            except Exception as e:
                print(f"{R}❌ Connection error {self.id}: {e}{RS}")
                add_console_log(f"❌ Connection error {self.id}: {e}", "error")
                with connected_clients_lock:
                    if self.id in connected_clients: del connected_clients[self.id]
                self.Connect_SerVer(Token, tok, host, port, key, iv, host2, port2)
                                    
    def GeT_Key_Iv(self, serialized_data):
        my_message = xKEys.MyMessage()
        my_message.ParseFromString(serialized_data)
        timestamp, key, iv = my_message.field21, my_message.field22, my_message.field23
        timestamp_obj = Timestamp()
        timestamp_obj.FromNanoseconds(timestamp)
        timestamp_seconds = timestamp_obj.seconds
        timestamp_nanos = timestamp_obj.nanos
        combined_timestamp = timestamp_seconds * 1_000_000_000 + timestamp_nanos
        return combined_timestamp, key, iv    

    def Guest_GeneRaTe(self, uid, password):
        self.url = "https://100067.connect.garena.com/oauth/guest/token/grant"
        self.headers = {
            "Host": "100067.connect.garena.com",
            "User-Agent": "GarenaMSDK/4.0.19P4(G011A ;Android 9;en;US;)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "close",
        }
        self.dataa = {
            "uid": f"{uid}",
            "password": f"{password}",
            "response_type": "token",
            "client_type": "2",
            "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
            "client_id": "100067",
        }
        try:
            self.response = requests.post(self.url, headers=self.headers, data=self.dataa).json()
            self.Access_ToKen, self.Access_Uid = self.response['access_token'], self.response['open_id']
            time.sleep(0.2)
            print(f'{C}🔐 Login: {self.id}{RS}')
            return self.ToKen_GeneRaTe(self.Access_ToKen, self.Access_Uid)
        except Exception as e: 
            print(f"{R}❌ Login error {self.id}: {e}{RS}")
            add_console_log(f"❌ Login error {self.id}: {e}", "error")
            time.sleep(10)
            return self.Guest_GeneRaTe(uid, password)
                                        
    def GeT_LoGin_PorTs(self, JwT_ToKen, PayLoad, dynamic_url="https://clientbp.ggpolarbear.com"):
        self.UrL = f'{dynamic_url}/GetLoginData'
        self.HeadErs = {
            'Expect': '100-continue',
            'Authorization': f'Bearer {JwT_ToKen}',
            'X-Unity-Version': '2022.3.47f1',
            'X-GA': 'v1 1',
            'ReleaseVersion': 'OB53',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)',
            'Connection': 'close',
            'Accept-Encoding': 'deflate, gzip',
        }        
        try:
            self.Res = requests.post(self.UrL, headers=self.HeadErs, data=PayLoad, verify=False)
            self.BesTo_data = json.loads(DeCode_PackEt(self.Res.content.hex()))  
            address, address2 = self.BesTo_data['32']['data'], self.BesTo_data['14']['data'] 
            ip, ip2 = address[:len(address) - 6], address2[:len(address2) - 6]
            port, port2 = address[len(address) - 5:], address2[len(address2) - 5:]             
            return ip, port, ip2, port2          
        except Exception as e:
            print(f"{R}❌ Failed to get ports: {e}{RS}")
            add_console_log(f"❌ Failed to get ports: {e}", "error")
        return None, None, None, None
        
    def ToKen_GeneRaTe(self, Access_ToKen, Access_Uid):
        self.UrL = "https://loginbp.ggwhitehawk.com/MajorLogin"
        self.HeadErs = {
            'X-Unity-Version': '2022.3.47f1',
            'ReleaseVersion': 'OB53',
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-GA': 'v1 1',
            'Content-Length': '928',
            'User-Agent': 'UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)',
            'Host': 'loginbp.ggwhitehawk.com',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'deflate, gzip'
        }   
        
        self.dT = bytes.fromhex('1a13323032352d31312d32362030313a35313a3238220966726565206669726528013a07312e3132332e314232416e64726f6964204f532039202f204150492d3238202850492f72656c2e636a772e32303232303531382e313134313333294a0848616e6468656c64520c4d544e2f537061636574656c5a045749464960800a68d00572033234307a2d7838362d3634205353453320535345342e3120535345342e32204156582041565832207c2032343030207c20348001e61e8a010f416472656e6f2028544d292036343092010d4f70656e474c20455320332e329a012b476f6f676c657c36323566373136662d393161372d343935622d396631362d303866653964336336353333a2010e3137362e32382e3133392e313835aa01026172b201203433303632343537393364653836646134323561353263616164663231656564ba010134c2010848616e6468656c64ca010d4f6e65506c7573204135303130ea014063363961653230386661643732373338623637346232383437623530613361316466613235643161313966616537343566633736616334613065343134633934f00101ca020c4d544e2f537061636574656cd2020457494649ca03203161633462383065636630343738613434323033626638666163363132306635e003b5ee02e8039a8002f003af13f80384078004a78f028804b5ee029004a78f029804b5ee02b00404c80401d2043d2f646174612f6170702f636f6d2e6474732e667265656669726574682d66705843537068495636644b43376a4c2d574f7952413d3d2f6c69622f61726de00401ea045f65363261623933353464386662356662303831646233333861636233333439317c2f646174612f6170702f636f6d2e6474732e667265656669726574682d66705843537068495636644b43376a4c2d574f7952413d3d2f626173652e61706bf00406f804018a050233329a050a32303139313139303236a80503b205094f70656e474c455332b805ff01c00504e005be7eea05093372645f7061727479f205704b717348543857393347646347335a6f7a454e6646775648746d377171316552554e6149444e67526f626f7a4942744c4f695943633459367a767670634943787a514632734f453463627974774c7334785a62526e70524d706d5752514b6d654f35766373386e51594268777148374bf805e7e4068806019006019a060134a2060134b2062213521146500e590349510e460900115843395f005b510f685b560a6107576d0f0366')
        
        self.dT = self.dT.replace(b'2025-07-30 14:11:20', str(datetime.now())[:-7].encode())
        self.dT = self.dT.replace(b'c69ae208fad72738b674b2847b50a3a1dfa25d1a19fae745fc76ac4a0e414c94', Access_ToKen.encode())
        self.dT = self.dT.replace(b'4306245793de86da425a52caadf21eed', Access_Uid.encode())
        
        try:
            hex_data = self.dT.hex()
            encoded_data = EnC_AEs(hex_data)
            if not all(c in '0123456789abcdefABCDEF' for c in encoded_data):
                encoded_data = hex_data
            self.PaYload = bytes.fromhex(encoded_data)
        except Exception as e:
            print(f"{R}❌ Encoding error: {e}{RS}")
            self.PaYload = self.dT
        
        self.ResPonse = requests.post(self.UrL, headers=self.HeadErs, data=self.PaYload, verify=False)        
        if self.ResPonse.status_code == 200 and len(self.ResPonse.text) > 10:
            try:
                self.BesTo_data = json.loads(DeCode_PackEt(self.ResPonse.content.hex()))
                self.JwT_ToKen = self.BesTo_data['8']['data']           
                self.combined_timestamp, self.key, self.iv = self.GeT_Key_Iv(self.ResPonse.content)
                ip, port, ip2, port2 = self.GeT_LoGin_PorTs(self.JwT_ToKen, self.PaYload)            
                return self.JwT_ToKen, self.key, self.iv, self.combined_timestamp, ip, port, ip2, port2
            except Exception as e:
                print(f"{R}❌ Response parsing error: {e}{RS}")
                time.sleep(5)
                return self.ToKen_GeneRaTe(Access_ToKen, Access_Uid)
        else:
            print(f"{R}❌ Token generation error, status: {self.ResPonse.status_code}{RS}")
            time.sleep(5)
            return self.ToKen_GeneRaTe(Access_ToKen, Access_Uid)
      
    def Get_FiNal_ToKen_0115(self):
        try:
            result = self.Guest_GeneRaTe(self.id, self.password)
            if not result:
                print(f"{Y}⚠️ Failed to get token {self.id}, retrying...{RS}")
                time.sleep(5)
                return self.Get_FiNal_ToKen_0115()
                
            token, key, iv, Timestamp, ip, port, ip2, port2 = result
            
            if not all([ip, port, ip2, port2]):
                print(f"{Y}⚠️ Failed to get ports {self.id}, retrying...{RS}")
                time.sleep(5)
                return self.Get_FiNal_ToKen_0115()
                
            self.JwT_ToKen = token        
            try:
                self.AfTer_DeC_JwT = jwt.decode(token, options={"verify_signature": False})
                self.AccounT_Uid = self.AfTer_DeC_JwT.get('account_id')
                self.EncoDed_AccounT = hex(self.AccounT_Uid)[2:]
                self.HeX_VaLue = DecodE_HeX(Timestamp)
                self.TimE_HEx = self.HeX_VaLue
                self.JwT_ToKen_ = token.encode().hex()
                print(f'{C}🆔 Account UID: {self.AccounT_Uid}{RS}')
            except Exception as e:
                print(f"{R}❌ Token decode error {self.id}: {e}{RS}")
                time.sleep(5)
                return self.Get_FiNal_ToKen_0115()
                
            try:
                self.Header = hex(len(EnC_PacKeT(self.JwT_ToKen_, key, iv)) // 2)[2:]
                length = len(self.EncoDed_AccounT)
                self.__ = '00000000'
                if length == 9: self.__ = '0000000'
                elif length == 8: self.__ = '00000000'
                elif length == 10: self.__ = '000000'
                elif length == 7: self.__ = '000000000'
                self.Header = f'0115{self.__}{self.EncoDed_AccounT}{self.TimE_HEx}00000{self.Header}'
                self.FiNal_ToKen_0115 = self.Header + EnC_PacKeT(self.JwT_ToKen_, key, iv)
            except Exception as e:
                print(f"{R}❌ Final token error {self.id}: {e}{RS}")
                time.sleep(5)
                return self.Get_FiNal_ToKen_0115()
                
            self.AutH_ToKen = self.FiNal_ToKen_0115
            self.Connect_SerVer(self.JwT_ToKen, self.AutH_ToKen, ip, port, key, iv, ip2, port2)        
            return self.AutH_ToKen, key, iv
            
        except Exception as e:
            print(f"{R}❌ {self.id} connection failed: {e}{RS}")
            add_console_log(f"❌ {self.id} connection failed: {e}", "error")
            time.sleep(10)
            return self.Get_FiNal_ToKen_0115()

def start_account(account):
    try:
        print(f"{G}🚀 Starting: {account['id']}{RS}")
        add_console_log(f"🚀 Starting account: {account['id']}", "info")
        FF_CLient(account['id'], account['password'])
    except Exception as e:
        print(f"{R}❌ {account['id']} failed: {e}{RS}")
        add_console_log(f"❌ {account['id']} failed: {e}", "error")
        time.sleep(5)
        start_account(account)

def run_accounts():
    add_console_log("📡 Starting all accounts...", "info")
    for account in ACCOUNTS:
        Thread(target=start_account, args=(account,), daemon=True).start()
        time.sleep(2)
    add_console_log(f"✅ All {len(ACCOUNTS)} accounts started", "success")

# ==================== মেইন ====================
def main():
    Thread(target=run_accounts, daemon=True).start()
    
    port = int(os.environ.get("PORT", 3139))
    
    print(f"""
    {C}{BOLD}
    ╔══════════════════════════════════════════════════════════════════╗
    ║                    🎯 SALIM POWER SPAM SYSTEM 🎯                 ║
    ║                                                                  ║
    ║     ✅ UNLIMITED SPAM MODE - FULLY AUTOMATED                     ║
    ║     ✅ DARK THEME UI WITH REAL-TIME CONSOLE                      ║
    ║     ✅ START/STOP SPAM BY TARGET UID                             ║
    ║     ✅ MULTI-ACCOUNT SUPPORT                                     ║
    ║                                                                  ║
    ║     🌐 Web Panel: http://127.0.0.1:{port}                        ║
    ║     👑 Developer: SALIM CODEX                                        ║
    ║     💀 STATUS: SYSTEM ACTIVE                                     ║
    ╚══════════════════════════════════════════════════════════════════╝
    {RS}
    """)
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

if __name__ == "__main__":
    main()