import os
import time
from backend.blockchain import Blockchain, Block, Transaction

def test_blockchain_basics():
    print("Testing Blockchain Basics...")
    db_path = "test_consensus_verify.db"
    
    if os.path.exists(db_path):
        os.remove(db_path)
        
    try:
        # 1. Initialize
        bc = Blockchain(node_id=888, db_path=db_path)
        assert len(bc.chain) == 1, "Genesis block missing"
        assert bc.get_balance("Alice") == 0.0, "Alice starting balance should be 0"
        
        # 2. Add System Minting
        tx_mint = Transaction(sender="SYSTEM", recipient="Alice", amount=150.0)
        block1 = Block(index=1, transactions=[tx_mint], previous_hash=bc.last_block.hash)
        added = bc.add_block(block1)
        assert added == True, "Failed to add block 1"
        assert bc.get_balance("Alice") == 150.0, "Alice balance should be 150"
        
        # 3. Add Transfer
        tx_transfer = Transaction(sender="Alice", recipient="Bob", amount=50.0)
        block2 = Block(index=2, transactions=[tx_transfer], previous_hash=bc.last_block.hash)
        added2 = bc.add_block(block2)
        assert added2 == True, "Failed to add block 2"
        
        assert bc.get_balance("Alice") == 100.0, "Alice balance should be 100"
        assert bc.get_balance("Bob") == 50.0, "Bob balance should be 50"
        
        # 4. Load from SQLite to verify persistence
        bc2 = Blockchain(node_id=888, db_path=db_path)
        assert len(bc2.chain) == 3, f"Expected 3 blocks loaded, got {len(bc2.chain)}"
        assert bc2.get_balance("Alice") == 100.0
        assert bc2.get_balance("Bob") == 50.0
        
        print("OK - Local blockchain and SQLite persistence tests passed.")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
            
    print("\nOK - Verification successful. All blockchain tests passed.")

if __name__ == "__main__":
    test_blockchain_basics()
