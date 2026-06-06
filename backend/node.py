import argparse
import logging
import requests
import time
from flask import Flask, jsonify, request
from blockchain import Blockchain, Transaction, Block

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# CORS setup
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

blockchain = None
peers = set()
simulated_delay = 0.0

@app.before_request
def apply_delay():
    if request.path == '/delay':
        return
    if simulated_delay > 0.0:
        time.sleep(simulated_delay)

@app.route('/chain', methods=['GET'])
def get_chain():
    return jsonify({
        'chain': [b.to_dict() for b in blockchain.chain],
        'length': len(blockchain.chain)
    }), 200

@app.route('/balances', methods=['GET'])
def get_balances():
    wallets = blockchain.get_wallets()
    balances = {wallet: blockchain.get_balance(wallet) for wallet in wallets}
    return jsonify({'balances': balances}), 200

@app.route('/nodes/register', methods=['POST'])
def register_peers():
    values = request.get_json()
    node_list = values.get('nodes')
    if not node_list:
        return jsonify({'message': 'Missing nodes list'}), 400
        
    for peer in node_list:
        peers.add(peer)
    return jsonify({'message': 'Peers registered', 'total_peers': list(peers)}), 200

@app.route('/nodes/list', methods=['GET'])
def list_peers():
    return jsonify({'peers': list(peers)}), 200

# ==========================================
# Consensus Voting & Transaction Submission
# ==========================================

@app.route('/transactions/vote', methods=['POST'])
def vote_transaction():
    """
    Endpoint for peers to vote on a transaction's validity.
    """
    tx_data = request.get_json()
    if not tx_data:
        return jsonify({'vote': 'no', 'reason': 'Missing transaction data'}), 400
        
    sender = tx_data.get('sender')
    amount = float(tx_data.get('amount', 0))
    
    if sender == "SYSTEM":
        # System spawns are automatically approved
        return jsonify({'vote': 'yes', 'reason': 'System minting approved.'}), 200
        
    # Check balance
    balance = blockchain.get_balance(sender)
    if balance >= amount:
        return jsonify({'vote': 'yes', 'reason': 'Valid balance.'}), 200
    else:
        return jsonify({'vote': 'no', 'reason': f'Insufficient balance ({balance} < {amount}).'}), 200

@app.route('/transactions/submit', methods=['POST'])
def submit_transaction():
    """
    Submits a transaction to the network. Triggers P2P voting.
    If 50% + 1 nodes approve, it mines a block and propagates it.
    """
    tx_data = request.get_json()
    if not tx_data:
        return jsonify({'message': 'Missing transaction data'}), 400
        
    sender = tx_data.get('sender')
    recipient = tx_data.get('recipient')
    amount = float(tx_data.get('amount', 0))
    
    wallets = blockchain.get_wallets()
    if sender not in wallets and sender != "SYSTEM":
        return jsonify({'message': 'Invalid sender wallet'}), 400
    if recipient not in wallets:
        return jsonify({'message': 'Invalid recipient wallet'}), 400
    if amount <= 0:
        return jsonify({'message': 'Amount must be positive'}), 400

    tx = Transaction(sender=sender, recipient=recipient, amount=amount)

    # 1. Collect votes from all registered peers + self
    votes = {}
    
    # Self-vote
    self_balance = blockchain.get_balance(sender)
    if sender == "SYSTEM" or self_balance >= amount:
        votes[f"http://127.0.0.1:{blockchain.node_id}"] = {"vote": "yes", "reason": "Self approved"}
    else:
        votes[f"http://127.0.0.1:{blockchain.node_id}"] = {"vote": "no", "reason": f"Self rejected (Balance: {self_balance})"}
        
    # Query peers
    for peer in list(peers):
        try:
            res = requests.post(f"{peer}/transactions/vote", json=tx.to_dict(), timeout=3.5)
            if res.status_code == 200:
                votes[peer] = res.json()
            else:
                votes[peer] = {"vote": "no", "reason": "Error response from peer"}
        except requests.exceptions.RequestException:
            votes[peer] = {"vote": "no", "reason": "Offline"}

    # 2. Count votes
    yes_votes = sum(1 for v in votes.values() if v.get('vote') == 'yes')
    no_votes = sum(1 for v in votes.values() if v.get('vote') != 'yes')
    
    # Total nodes in registry = peers + self
    total_nodes = len(peers) + 1
    # 50% + 1 threshold
    threshold = (total_nodes // 2) + 1
    
    logging.info(f"Transaction voting: {yes_votes} YES / {no_votes} NO out of {total_nodes} nodes (Threshold: {threshold})")
    
    if yes_votes >= threshold:
        # Create and mine block containing transaction
        new_block = Block(
            index=blockchain.last_block.index + 1,
            transactions=[tx],
            previous_hash=blockchain.last_block.hash
        )
        
        # Save block locally
        blockchain.add_block(new_block)
        
        # Broadcast block to peer nodes
        broadcast_block(new_block.to_dict())
        
        return jsonify({
            'approved': True,
            'message': 'Consensus reached. Transaction approved and block mined.',
            'votes': votes,
            'block': new_block.to_dict()
        }), 200
    else:
        return jsonify({
            'approved': false,
            'message': f'Consensus failed. Required {threshold} votes, got {yes_votes}.',
            'votes': votes
        }), 400

@app.route('/mint', methods=['POST'])
def mint_coins():
    """
    Directly mints coins without P2P voting (authorized SYSTEM operation).
    """
    values = request.get_json()
    recipient = values.get('recipient')
    amount = float(values.get('amount', 0))
    
    wallets = blockchain.get_wallets()
    if recipient not in wallets:
        return jsonify({'message': 'Invalid recipient wallet'}), 400
    if amount <= 0:
        return jsonify({'message': 'Amount must be positive'}), 400
        
    tx = Transaction(sender="SYSTEM", recipient=recipient, amount=amount)
    
    new_block = Block(
        index=blockchain.last_block.index + 1,
        transactions=[tx],
        previous_hash=blockchain.last_block.hash
    )
    
    blockchain.add_block(new_block)
    
    # Broadcast to peers
    broadcast_block(new_block.to_dict())
    
    return jsonify({
        'message': 'Coins spawned successfully.',
        'block': new_block.to_dict()
    }), 200

@app.route('/blocks/receive', methods=['POST'])
def receive_block():
    values = request.get_json()
    if not values or 'block' not in values:
        return jsonify({'message': 'Missing block data'}), 400
        
    block = Block.from_dict(values['block'])
    if blockchain.add_block(block):
        logging.info(f"Accepted and saved block #{block.index} from peer.")
        return jsonify({'message': 'Block saved.'}), 200
    else:
        return jsonify({'message': 'Block rejected (invalid link or hash).'}), 400

@app.route('/nodes/sync', methods=['POST'])
def sync_chain():
    values = request.get_json()
    if not values or 'chain' not in values:
        return jsonify({'message': 'Missing chain data'}), 400
        
    try:
        blocks = [Block.from_dict(b_dict) for b_dict in values['chain']]
    except Exception as e:
        return jsonify({'message': f'Parsing failed: {str(e)}'}), 400
        
    if blockchain.replace_chain(blocks):
        # Synchronize wallets if provided
        wallets = values.get('wallets')
        if wallets:
            for w in wallets:
                blockchain.add_wallet(w)
        logging.info(f"Synchronized database to master chain of height {len(blockchain.chain)}")
        return jsonify({'message': 'Synchronization successful.'}), 200
    else:
        return jsonify({'message': 'Synchronization failed: invalid chain.'}), 400

@app.route('/wallets/create', methods=['POST'])
def create_wallet():
    values = request.get_json()
    if not values or 'address' not in values:
        return jsonify({'message': 'Missing address'}), 400
    address = values.get('address').strip()
    if not address:
        return jsonify({'message': 'Address cannot be empty'}), 400
        
    if blockchain.add_wallet(address):
        # Broadcast to peers
        broadcast_wallet(address)
        return jsonify({'message': f'Wallet {address} created successfully'}), 200
    else:
        return jsonify({'message': 'Wallet already exists or database error'}), 400

@app.route('/wallets/receive', methods=['POST'])
def receive_wallet():
    values = request.get_json()
    if not values or 'address' not in values:
        return jsonify({'message': 'Missing address'}), 400
    address = values.get('address').strip()
    if blockchain.add_wallet(address):
        logging.info(f"Replicated wallet {address} from peer.")
        return jsonify({'message': 'Wallet saved.'}), 200
    return jsonify({'message': 'Wallet already exists or not saved.'}), 200

@app.route('/delay', methods=['POST', 'OPTIONS'])
def set_delay():
    if request.method == 'OPTIONS':
        return '', 200
    global simulated_delay
    values = request.get_json()
    if not values or 'delay' not in values:
        return jsonify({'message': 'Missing delay value'}), 400
    simulated_delay = float(values['delay']) / 1000.0
    logging.info(f"Set simulated delay to {simulated_delay}s")
    return jsonify({'message': f'Delay set to {simulated_delay * 1000:.0f}ms'}), 200

@app.route('/clear', methods=['POST'])
def clear_db():
    blockchain.clear_db()
    return jsonify({'message': 'Database reset successfully.'}), 200

# ==========================================
# P2P Broadcast Helpers
# ==========================================

def broadcast_block(block_dict: dict):
    payload = {'block': block_dict}
    for peer in list(peers):
        try:
            requests.post(f"{peer}/blocks/receive", json=payload, timeout=1.5)
        except requests.exceptions.RequestException:
            pass # peer offline

def broadcast_wallet(address: str):
    payload = {'address': address}
    for peer in list(peers):
        try:
            requests.post(f"{peer}/wallets/receive", json=payload, timeout=1.5)
        except requests.exceptions.RequestException:
            pass # peer offline

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--db', required=True, type=str)
    parser.add_argument('--peers', default='', type=str)
    args = parser.parse_args()

    blockchain = Blockchain(node_id=args.port, db_path=args.db)
    logging.info(f"Started client port {args.port} with database {args.db}")
    
    if args.peers:
        peer_list = [p.strip() for p in args.peers.split(',') if p.strip()]
        for peer in peer_list:
            peers.add(peer)
            
    app.run(host='127.0.0.1', port=args.port, debug=False, threaded=True)
