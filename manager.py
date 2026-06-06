import os
import sys
import time
import subprocess
import signal
import logging
import threading
import requests
from flask import Flask, send_from_directory

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

NODES_CONFIG = [
    {
        "port": 5001,
        "db": os.path.join(PROJECT_ROOT, "db", "db_5001.db"),
        "peers": "http://127.0.0.1:5002,http://127.0.0.1:5003"
    },
    {
        "port": 5002,
        "db": os.path.join(PROJECT_ROOT, "db", "db_5002.db"),
        "peers": "http://127.0.0.1:5001,http://127.0.0.1:5003"
    },
    {
        "port": 5003,
        "db": os.path.join(PROJECT_ROOT, "db", "db_5003.db"),
        "peers": "http://127.0.0.1:5001,http://127.0.0.1:5002"
    }
]

app = Flask(__name__, static_folder=os.path.join(PROJECT_ROOT, 'frontend'), static_url_path='')

@app.route('/')
def index():
    return send_from_directory(os.path.join(PROJECT_ROOT, 'frontend'), 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(os.path.join(PROJECT_ROOT, 'frontend'), path)

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

processes = []
sync_thread_active = True

def start_nodes():
    os.makedirs(os.path.join(PROJECT_ROOT, "db"), exist_ok=True)
    os.makedirs(os.path.join(PROJECT_ROOT, "logs"), exist_ok=True)
    
    node_script_path = os.path.join(PROJECT_ROOT, "backend", "node.py")
    
    for config in NODES_CONFIG:
        port = config["port"]
        db = config["db"]
        peers = config["peers"]
        
        log_file_path = os.path.join(PROJECT_ROOT, "logs", f"node_{port}.log")
        log_file = open(log_file_path, "w")
        
        logging.info(f"Starting Node {port} (DB: {db})")
        
        cmd = [
            sys.executable, 
            node_script_path,
            "--port", str(port),
            "--db", db,
            "--peers", peers
        ]
        
        p = subprocess.Popen(cmd, stdout=log_file, stderr=log_file)
        processes.append((p, log_file))

# ==========================================
# Background Periodic Sync Loop
# ==========================================

def periodic_sync_loop():
    """
    Every 5 seconds, queries all nodes, finds the longest valid chain,
    and propagates it to any node that is shorter.
    """
    global sync_thread_active
    logging.info("Starting background longest chain synchronization loop...")
    
    while sync_thread_active:
        time.sleep(5)
        
        node_chains = {}
        for config in NODES_CONFIG:
            url = f"http://127.0.0.1:{config['port']}"
            try:
                # Query chain with quick timeout
                res = requests.get(f"{url}/chain", timeout=3.0)
                if res.status_code == 200:
                    data = res.json()
                    # Also fetch current wallet addresses
                    wallets_res = requests.get(f"{url}/balances", timeout=3.0)
                    wallets_list = []
                    if wallets_res.status_code == 200:
                        wallets_list = list(wallets_res.json().get('balances', {}).keys())
                    node_chains[url] = {
                        "length": data["length"],
                        "chain": data["chain"],
                        "wallets": wallets_list
                    }
            except Exception:
                pass # Node offline
                
        if len(node_chains) < 2:
            continue # Need at least 2 online nodes to sync
            
        # Find the longest chain
        longest_url = max(node_chains, key=lambda u: node_chains[u]["length"])
        longest_len = node_chains[longest_url]["length"]
        longest_chain = node_chains[longest_url]["chain"]
        longest_wallets = node_chains[longest_url]["wallets"]
        
        # Propagate to any online node that has a shorter chain
        for url, info in node_chains.items():
            if info["length"] < longest_len:
                logging.info(f"Auto-Syncing {url} (Height: {info['length']} -> {longest_len}) from {longest_url}")
                try:
                    requests.post(f"{url}/nodes/sync", json={
                        "chain": longest_chain,
                        "wallets": longest_wallets
                    }, timeout=1.5)
                except Exception as e:
                    logging.warning(f"Failed to sync {url}: {e}")

def cleanup_and_exit(signum=None, frame=None):
    global sync_thread_active
    sync_thread_active = False
    
    logging.info("Shutting down nodes and dashboard...")
    for p, log_file in processes:
        try:
            p.terminate()
            p.wait(timeout=3)
            logging.info(f"Terminated process {p.pid}")
        except Exception as e:
            logging.warning(f"Error terminating process: {e}")
        finally:
            log_file.close()
            
    logging.info("Shutdown completed.")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Consensus Blockchain Dashboard Coordinator")
    parser.add_argument('--port', default=5000, type=int, help='Port to run coordinator dashboard on')
    args = parser.parse_args()
    
    try:
        # 1. Start nodes
        start_nodes()
        time.sleep(2)
        
        # 2. Start periodic sync thread
        t = threading.Thread(target=periodic_sync_loop, daemon=True)
        t.start()
        
        # 3. Serve frontend dashboard
        logging.info(f"Starting Dashboard Coordinator on http://127.0.0.1:{args.port}")
        app.run(host='127.0.0.1', port=args.port, debug=False, threaded=True)
    except KeyboardInterrupt:
        cleanup_and_exit()
    except Exception as e:
        logging.error(f"Error starting coordinator: {e}")
        cleanup_and_exit()
