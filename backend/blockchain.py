import hashlib
import json
import time
import sqlite3
from typing import List, Dict, Any, Optional

class Transaction:
    def __init__(self, sender: str, recipient: str, amount: float, timestamp: float = None, tx_id: str = ""):
        self.sender = sender
        self.recipient = recipient
        self.amount = amount
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.tx_id = tx_id if tx_id else self.calculate_hash()

    def calculate_hash(self) -> str:
        sha = hashlib.sha256()
        payload = f"{self.sender}:{self.recipient}:{self.amount}:{self.timestamp}"
        sha.update(payload.encode('utf-8'))
        return sha.hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_id": self.tx_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": self.amount,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Transaction':
        return cls(
            sender=data["sender"],
            recipient=data["recipient"],
            amount=float(data["amount"]),
            timestamp=float(data["timestamp"]),
            tx_id=data.get("tx_id", "")
        )

class Block:
    def __init__(self, index: int, transactions: List[Transaction], previous_hash: str, timestamp: float = None, block_hash: str = ""):
        self.index = index
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.hash = block_hash if block_hash else self.calculate_hash()

    def calculate_hash(self) -> str:
        sha = hashlib.sha256()
        tx_hashes = "".join([tx.tx_id for tx in self.transactions])
        payload = f"{self.index}:{self.timestamp}:{tx_hashes}:{self.previous_hash}"
        sha.update(payload.encode('utf-8'))
        return sha.hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "previous_hash": self.previous_hash,
            "hash": self.hash
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Block':
        txs = [Transaction.from_dict(tx_data) for tx_data in data["transactions"]]
        return cls(
            index=int(data["index"]),
            transactions=txs,
            previous_hash=data["previous_hash"],
            timestamp=float(data["timestamp"]),
            block_hash=data["hash"]
        )

class Blockchain:
    def __init__(self, node_id: int, db_path: str):
        self.node_id = node_id
        self.db_path = db_path
        self.chain: List[Block] = []
        
        self.init_db()
        self.load_chain_from_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create blocks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                block_index INTEGER PRIMARY KEY,
                timestamp REAL,
                previous_hash TEXT,
                hash TEXT
            )
        ''')
        
        # Create transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                tx_id TEXT PRIMARY KEY,
                block_index INTEGER,
                sender TEXT,
                recipient TEXT,
                amount REAL,
                timestamp REAL,
                FOREIGN KEY(block_index) REFERENCES blocks(block_index)
            )
        ''')

        # Create wallets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wallets (
                address TEXT PRIMARY KEY
            )
        ''')
        
        # Ensure default wallets
        for user in ["Alice", "Bob", "Charlie", "Dave"]:
            cursor.execute("INSERT OR IGNORE INTO wallets (address) VALUES (?)", (user,))
            
        conn.commit()
        conn.close()

    def clear_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transactions")
        cursor.execute("DELETE FROM blocks")
        cursor.execute("DELETE FROM wallets")
        for user in ["Alice", "Bob", "Charlie", "Dave"]:
            cursor.execute("INSERT OR IGNORE INTO wallets (address) VALUES (?)", (user,))
        conn.commit()
        conn.close()
        self.chain = []
        self.create_genesis_block()

    def save_block_to_db(self, block: Block):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO blocks (block_index, timestamp, previous_hash, hash)
            VALUES (?, ?, ?, ?)
        ''', (block.index, block.timestamp, block.previous_hash, block.hash))
        
        for tx in block.transactions:
            cursor.execute('''
                INSERT OR REPLACE INTO transactions (tx_id, block_index, sender, recipient, amount, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (tx.tx_id, block.index, tx.sender, tx.recipient, tx.amount, tx.timestamp))
            
        conn.commit()
        conn.close()

    def load_chain_from_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT block_index, timestamp, previous_hash, hash FROM blocks ORDER BY block_index ASC")
        blocks_data = cursor.fetchall()
        
        self.chain = []
        
        for b_data in blocks_data:
            b_index, b_timestamp, b_nonce_unused, b_prev_hash = b_data[:4]
            b_hash = b_data[3]
            
            cursor.execute('''
                SELECT sender, recipient, amount, timestamp, tx_id
                FROM transactions
                WHERE block_index = ?
                ORDER BY timestamp ASC
            ''', (b_index,))
            txs_data = cursor.fetchall()
            
            txs = []
            for tx_data in txs_data:
                sender, recipient, amount, timestamp, tx_id = tx_data
                txs.append(Transaction(
                    sender=sender,
                    recipient=recipient,
                    amount=amount,
                    timestamp=timestamp,
                    tx_id=tx_id
                ))
            
            block = Block(
                index=b_index,
                transactions=txs,
                previous_hash=b_prev_hash,
                timestamp=b_timestamp,
                block_hash=b_hash
            )
            self.chain.append(block)
            
        conn.close()
        
        if not self.chain:
            self.create_genesis_block()

    def create_genesis_block(self):
        genesis_tx = Transaction(
            sender="SYSTEM",
            recipient="Genesis",
            amount=0.0
        )
        genesis_block = Block(
            index=0,
            transactions=[genesis_tx],
            previous_hash="0",
            timestamp=1600000000.0
        )
        self.chain.append(genesis_block)
        self.save_block_to_db(genesis_block)

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    def get_balance(self, address: str) -> float:
        """
        Replays transaction ledger from SQLite chain.
        """
        balance = 0.0
        for block in self.chain:
            for tx in block.transactions:
                if tx.sender == address:
                    balance -= tx.amount
                if tx.recipient == address:
                    balance += tx.amount
        return balance

    def add_block(self, block: Block) -> bool:
        """
        Appends block to local chain and saves to database.
        """
        if block.index != self.last_block.index + 1:
            return False
        if block.previous_hash != self.last_block.hash:
            return False
        if block.hash != block.calculate_hash():
            return False
            
        self.chain.append(block)
        self.save_block_to_db(block)
        return True

    def validate_chain(self, chain_to_validate: List[Block]) -> bool:
        if not chain_to_validate:
            return False
        # Genesis block
        if chain_to_validate[0].index != 0 or chain_to_validate[0].previous_hash != "0":
            return False
            
        for i in range(1, len(chain_to_validate)):
            prev = chain_to_validate[i-1]
            curr = chain_to_validate[i]
            if curr.previous_hash != prev.hash:
                return False
            if curr.hash != curr.calculate_hash():
                return False
        return True

    def replace_chain(self, new_blocks: List[Block]) -> bool:
        if not self.validate_chain(new_blocks):
            return False
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transactions")
        cursor.execute("DELETE FROM blocks")
        cursor.execute("DELETE FROM wallets")
        
        # Ensure default wallets
        for user in ["Alice", "Bob", "Charlie", "Dave"]:
            cursor.execute("INSERT OR IGNORE INTO wallets (address) VALUES (?)", (user,))
            
        conn.commit()
        conn.close()
        
        for block in new_blocks:
            self.save_block_to_db(block)
            # Rebuild dynamic wallets from transactions in SQLite
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            for tx in block.transactions:
                if tx.sender != "SYSTEM":
                    cursor.execute("INSERT OR IGNORE INTO wallets (address) VALUES (?)", (tx.sender,))
                if tx.recipient != "SYSTEM" and tx.recipient != "Genesis":
                    cursor.execute("INSERT OR IGNORE INTO wallets (address) VALUES (?)", (tx.recipient,))
            conn.commit()
            conn.close()
            
        self.chain = new_blocks
        return True

    def add_wallet(self, address: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT OR IGNORE INTO wallets (address) VALUES (?)", (address,))
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()

    def get_wallets(self) -> List[str]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT address FROM wallets")
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]
