import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import chromadb

# Import core MemPalace components from the current package
from mempalace.config import MempalaceConfig
from mempalace.knowledge_graph import KnowledgeGraph
from mempalace.searcher import search_memories

app = FastAPI(title="MemPalace Neighborhood Service")

# 1. THE ROOT STORAGE (Override via env if needed)
NEIGHBORHOOD_ROOT = Path(os.environ.get("MEMPALACE_NEIGHBORHOOD_ROOT", "/Users/johnjoyce/mempalace_neighborhoods"))
NEIGHBORHOOD_ROOT.mkdir(parents=True, exist_ok=True)

class PalaceInstance:
    """A wrapper for a single isolated MemPalace instance (Tenant or Corporate)."""
    
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        # Ensure the directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Force the palace path to be this directory for isolation
        self.palace_path = str(config_dir)
        self.kg_path = str(config_dir / "knowledge_graph.sqlite3")
        
        self.config = MempalaceConfig(config_dir=str(config_dir))
        self.config.init()  
        
        # Initialize core components using the isolated paths
        self.kg = KnowledgeGraph(db_path=self.kg_path)
        self.chroma_client = chromadb.PersistentClient(path=self.palace_path)
        self.collection = self.chroma_client.get_or_create_collection(self.config.collection_name)
        
    def get_status(self):
        """Get the hierarchical wing -> room breakdown for this palace."""
        count = self.collection.count()
        taxonomy = {}
        try:
            all_meta = self.collection.get(include=["metadatas"], limit=10000)["metadatas"]
            for m in all_meta:
                w = m.get("wing", "unknown")
                r = m.get("room", "unknown")
                if w not in taxonomy:
                    taxonomy[w] = {}
                taxonomy[w][r] = taxonomy[w].get(r, 0) + 1
        except Exception:
            pass
        return {
            "total_drawers": count,
            "taxonomy": taxonomy
        }

    def add_wing(self, wing: str):
        """Explicitly initialize a wing by adding a placeholder drawer."""
        drawer_id = f"init_{wing}_{datetime.now().strftime('%Y%m%d')}"
        self.collection.upsert(
            ids=[drawer_id],
            documents=[f"Initial placeholder for wing: {wing}"],
            metadatas=[{
                "wing": wing,
                "room": "general",
                "type": "placeholder",
                "filed_at": datetime.now().isoformat()
            }]
        )
        return drawer_id

    def search(self, query: str, limit: int = 5):
        """Perform semantic search in this specific palace."""
        return search_memories(
            query,
            palace_path=self.palace_path,
            n_results=limit
        )

    def query_facts(self, entity: str):
        """Query facts from the knowledge graph."""
        return self.kg.query_entity(entity)

    def add_drawer(self, wing: str, room: str, content: str):
        """File verbatim content into the palace."""
        drawer_id = f"drawer_{wing}_{room}_{hashlib.sha256((wing + room + content[:100]).encode()).hexdigest()[:24]}"
        self.collection.upsert(
            ids=[drawer_id],
            documents=[content],
            metadatas=[{
                "wing": wing,
                "room": room,
                "filed_at": datetime.now().isoformat()
            }]
        )
        return drawer_id

    def add_diary_entry(self, agent_name: str, entry: str, topic: str = "general"):
        """Write a diary entry."""
        wing = f"wing_{agent_name.lower().replace(' ', '_')}"
        now = datetime.now()
        entry_id = f"diary_{wing}_{now.strftime('%Y%m%d_%H%M%S')}"
        self.collection.add(
            ids=[entry_id],
            documents=[entry],
            metadatas=[{
                "wing": wing,
                "room": "diary",
                "topic": topic,
                "agent": agent_name,
                "filed_at": now.isoformat()
            }]
        )
        return entry_id

class Neighborhood:
    """Manages the relationship between a Corporate hub and its Tenants."""
    
    def __init__(self, neighborhood_id: str):
        self.id = neighborhood_id
        self.path = NEIGHBORHOOD_ROOT / neighborhood_id
        
        # Corporate Shared Palace
        self.corporate_path = self.path / "corporate"
        self.corporate = PalaceInstance(self.corporate_path)
        
        # Active tenant cache
        self.tenants = {}

    def get_tenant(self, tenant_id: str) -> PalaceInstance:
        """Fetch or create an isolated palace for a specific tenant."""
        if tenant_id not in self.tenants:
            tenant_path = self.path / "tenants" / tenant_id
            self.tenants[tenant_id] = PalaceInstance(tenant_path)
        return self.tenants[tenant_id]

# Singleton cache for neighborhoods
_neighborhood_cache = {}

def get_neighborhood(n_id: str) -> Neighborhood:
    if n_id not in _neighborhood_cache:
        _neighborhood_cache[n_id] = Neighborhood(n_id)
    return _neighborhood_cache[n_id]

class PromptRequest(BaseModel):
    prompt: str
    limit: Optional[int] = 5

class WingRequest(BaseModel):
    wing: str

class BulkItem(BaseModel):
    title: str
    content: str
    room: Optional[str] = "general"

class BulkIngestRequest(BaseModel):
    wing: str
    items: List[BulkItem]

class IngestRequest(BaseModel):
    prompt: str
    response: str
    diary_summary: Optional[str] = None
    agent_name: str = "Gemini"
    topic: str = "general"
    facts: Optional[List[dict]] = None  # List of {subject, predicate, object}

@app.get("/status")
async def get_palace_status(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_neighborhood_id: str = Header(..., alias="X-Neighborhood-ID")
):
    """
    Returns the wing/room breakdown for the user's personal palace.
    """
    try:
        nb = get_neighborhood(x_neighborhood_id)
        personal = nb.get_tenant(x_tenant_id)
        status = personal.get_status()
        return {
            "status": "success",
            "neighborhood": x_neighborhood_id,
            "tenant": x_tenant_id,
            "palace": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/wings")
async def create_wing(
    request: WingRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_neighborhood_id: str = Header(..., alias="X-Neighborhood-ID")
):
    """
    Explicitly creates a new wing in the user's personal palace.
    """
    try:
        nb = get_neighborhood(x_neighborhood_id)
        personal = nb.get_tenant(x_tenant_id)
        drawer_id = personal.add_wing(request.wing)
        return {"status": "success", "wing": request.wing, "drawer_id": drawer_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ingest/bulk")
async def bulk_ingest(
    request: BulkIngestRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_neighborhood_id: str = Header(..., alias="X-Neighborhood-ID")
):
    """
    Bulk ingest content into a specific wing.
    Useful for 'Mining' via the API without filesystem access.
    """
    try:
        nb = get_neighborhood(x_neighborhood_id)
        personal = nb.get_tenant(x_tenant_id)
        
        drawer_ids = []
        for item in request.items:
            # We prefix the content with the title for better retrieval
            full_content = f"TITLE: {item.title}\n\n{item.content}"
            d_id = personal.add_drawer(wing=request.wing, room=item.room, content=full_content)
            drawer_ids.append(d_id)
            
        return {
            "status": "success", 
            "wing": request.wing, 
            "items_added": len(drawer_ids),
            "drawer_ids": drawer_ids
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query")
async def query_neighborhood(
    request: PromptRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_neighborhood_id: str = Header(..., alias="X-Neighborhood-ID")
):
    """
    Main endpoint for Xojo integration. 
    Performs federated search across Corporate and Personal Palaces.
    """
    try:
        nb = get_neighborhood(x_neighborhood_id)
        personal = nb.get_tenant(x_tenant_id)
        
        # 1. Search Shared Corporate Context
        corp_results = nb.corporate.search(request.prompt, limit=request.limit)
        
        # 2. Search Personal Private Context
        pers_results = personal.search(request.prompt, limit=request.limit)
        
        # 3. Pull Knowledge Graph Facts (Entity-based)
        entity_hint = " ".join(request.prompt.split()[:3])
        corp_facts = nb.corporate.query_facts(entity_hint)
        pers_facts = personal.query_facts(entity_hint)
        
        # 4. Construct the Augmented Prompt
        augmented_prompt = f"""Using the following context, please answer the user's question.

### CORPORATE KNOWLEDGE (OFFICIAL)
{json.dumps(corp_results, indent=2)}
{json.dumps(corp_facts, indent=2)}

### PERSONAL MEMORIES (PRIVATE)
{json.dumps(pers_results, indent=2)}
{json.dumps(pers_facts, indent=2)}

### USER QUESTION
{request.prompt}
"""

        return {
            "status": "success",
            "context": {
                "corporate": corp_results,
                "personal": pers_results,
                "facts": corp_facts + pers_facts
            },
            "augmented_prompt": augmented_prompt
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ingest")
async def ingest_conversation(
    request: IngestRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_neighborhood_id: str = Header(..., alias="X-Neighborhood-ID")
):
    """
    Final step: Saves the conversation and summary into the tenant's private palace.
    Call this AFTER Gemini responds in Xojo.
    """
    try:
        nb = get_neighborhood(x_neighborhood_id)
        personal = nb.get_tenant(x_tenant_id)

        # 1. Save the verbatim conversation
        full_convo = f"USER: {request.prompt}\n\nASSISTANT: {request.response}"
        drawer_id = personal.add_drawer(wing="wing_user", room="conversations", content=full_convo)

        # 2. Save the Diary Entry (if provided)
        diary_id = None
        if request.diary_summary:
            diary_id = personal.add_diary_entry(
                agent_name=request.agent_name,
                entry=request.diary_summary,
                topic=request.topic
            )

        # 3. Add Knowledge Graph Facts (if extracted by Gemini)
        if request.facts:
            for fact in request.facts:
                personal.kg.add_triple(
                    subject=fact.get("subject"),
                    predicate=fact.get("predicate"),
                    obj=fact.get("object"),
                    valid_from=datetime.now().strftime("%Y-%m-%d")
                )

        return {
            "status": "success",
            "drawer_id": drawer_id,
            "diary_id": diary_id,
            "facts_added": len(request.facts) if request.facts else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
