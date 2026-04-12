import sys
import os
from pathlib import Path

# Add current directory to path so we can import mempalace
sys.path.append(os.getcwd())

from mempalace.config import MempalaceConfig
from mempalace.knowledge_graph import KnowledgeGraph
import chromadb

# 1. Setup two temporary tenant directories
TEST_ROOT = Path("/tmp/mempalace_test")
if TEST_ROOT.exists():
    import shutil
    shutil.rmtree(TEST_ROOT)

ALICE_DIR = TEST_ROOT / "tenants" / "alice"
BOB_DIR = TEST_ROOT / "tenants" / "bob"

ALICE_DIR.mkdir(parents=True)
BOB_DIR.mkdir(parents=True)

# 2. Initialize Alice's Palace
print("--- Initializing Alice's Palace ---")
alice_config = MempalaceConfig(config_dir=str(ALICE_DIR))
alice_config.init()
alice_kg = KnowledgeGraph(db_path=alice_config.kg_path)
alice_kg.add_triple("Alice", "loves", "Apples")

alice_client = chromadb.PersistentClient(path=alice_config.palace_path)
alice_col = alice_client.get_or_create_collection("mempalace_drawers")
alice_col.add(ids=["drawer_1"], documents=["Alice is a doctor."], metadatas=[{"wing": "personal", "room": "about"}])

# 3. Initialize Bob's Palace
print("--- Initializing Bob's Palace ---")
bob_config = MempalaceConfig(config_dir=str(BOB_DIR))
bob_config.init()
bob_kg = KnowledgeGraph(db_path=bob_config.kg_path)
bob_kg.add_triple("Bob", "loves", "Bananas")

bob_client = chromadb.PersistentClient(path=bob_config.palace_path)
bob_col = bob_client.get_or_create_collection("mempalace_drawers")
bob_col.add(ids=["drawer_1"], documents=["Bob is an engineer."], metadatas=[{"wing": "personal", "room": "about"}])

# 4. Verify Isolation
print("--- Verifying Isolation ---")

# Check KG
alice_facts = alice_kg.query_entity("Alice")
bob_facts = bob_kg.query_entity("Bob")

print(f"Alice's Facts: {alice_facts}")
print(f"Bob's Facts: {bob_facts}")

if any(f['object'] == "Bananas" for f in alice_facts):
    print("FAILURE: Alice saw Bob's bananas!")
else:
    print("SUCCESS: Alice's KG is isolated.")

# Check ChromaDB
alice_docs = alice_col.get(ids=["drawer_1"])['documents']
bob_docs = bob_col.get(ids=["drawer_1"])['documents']

print(f"Alice's Doc: {alice_docs}")
print(f"Bob's Doc: {bob_docs}")

if alice_docs[0] == "Bob is an engineer.":
    print("FAILURE: Alice saw Bob's career!")
else:
    print("SUCCESS: Alice's ChromaDB is isolated.")

