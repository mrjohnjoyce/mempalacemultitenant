"""
knowledge_graph.py — Temporal Entity-Relationship Graph for MemPalace
=====================================================================

Real knowledge graph with:
  - Entity nodes (people, projects, tools, concepts)
  - Typed relationship edges (daughter_of, does, loves, works_on, etc.)
  - Temporal validity (valid_from → valid_to — knows WHEN facts are true)
  - Closet references (links back to the verbatim memory)

Storage: SQLite (local, no dependencies, no subscriptions)
Query: entity-first traversal with time filtering
"""

import hashlib
import json
import os
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path


class KnowledgeGraph:
    def __init__(self, db_path: str):
        """Initialize the knowledge graph with a specific SQLite path."""
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = None
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        conn = self._conn()
        conn.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'unknown',
                properties TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS triples (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                valid_from TEXT,
                valid_to TEXT,
                confidence REAL DEFAULT 1.0,
                source_closet TEXT,
                source_file TEXT,
                extracted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (subject) REFERENCES entities(id),
                FOREIGN KEY (object) REFERENCES entities(id)
            );

            CREATE INDEX IF NOT EXISTS idx_triples_subject ON triples(subject);
            CREATE INDEX IF NOT EXISTS idx_triples_object ON triples(object);
            CREATE INDEX IF NOT EXISTS idx_triples_predicate ON triples(predicate);
            CREATE INDEX IF NOT EXISTS idx_triples_valid ON triples(valid_from, valid_to);
        """)
        conn.commit()

    def _conn(self):
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self):
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _entity_id(self, name: str) -> str:
        return name.lower().replace(" ", "_").replace("'", "")

    # ── Write operations ──────────────────────────────────────────────────

    def add_entity(self, name: str, entity_type: str = "unknown", properties: dict = None):
        """Add or update an entity node."""
        eid = self._entity_id(name)
        props = json.dumps(properties or {})
        with self._lock:
            conn = self._conn()
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO entities (id, name, type, properties) VALUES (?, ?, ?, ?)",
                    (eid, name, entity_type, props),
                )
        return eid

    def add_triple(
        self,
        subject: str,
        predicate: str,
        obj: str,
        valid_from: str = None,
        valid_to: str = None,
        confidence: float = 1.0,
        source_closet: str = None,
        source_file: str = None,
    ):
        """Add a relationship triple: subject → predicate → object."""
        sub_id = self._entity_id(subject)
        obj_id = self._entity_id(obj)
        pred = predicate.lower().replace(" ", "_")

        with self._lock:
            conn = self._conn()
            with conn:
                conn.execute(
                    "INSERT OR IGNORE INTO entities (id, name) VALUES (?, ?)", (sub_id, subject)
                )
                conn.execute(
                    "INSERT OR IGNORE INTO entities (id, name) VALUES (?, ?)", (obj_id, obj)
                )

                existing = conn.execute(
                    "SELECT id FROM triples WHERE subject=? AND predicate=? AND object=? AND valid_to IS NULL",
                    (sub_id, pred, obj_id),
                ).fetchone()

                if existing:
                    return existing["id"]

                triple_id = f"t_{sub_id}_{pred}_{obj_id}_{hashlib.sha256(f'{valid_from}{datetime.now().isoformat()}'.encode()).hexdigest()[:12]}"

                conn.execute(
                    """INSERT INTO triples (id, subject, predicate, object, valid_from, valid_to, confidence, source_closet, source_file)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        triple_id,
                        sub_id,
                        pred,
                        obj_id,
                        valid_from,
                        valid_to,
                        confidence,
                        source_closet,
                        source_file,
                    ),
                )
        return triple_id

    def invalidate(self, subject: str, predicate: str, obj: str, ended: str = None):
        """Mark a relationship as no longer valid (set valid_to date)."""
        sub_id = self._entity_id(subject)
        obj_id = self._entity_id(obj)
        pred = predicate.lower().replace(" ", "_")
        ended = ended or date.today().isoformat()

        with self._lock:
            conn = self._conn()
            with conn:
                conn.execute(
                    "UPDATE triples SET valid_to=? WHERE subject=? AND predicate=? AND object=? AND valid_to IS NULL",
                    (ended, sub_id, pred, obj_id),
                )

    # ── Query operations ──────────────────────────────────────────────────

    def query_entity(self, name: str, as_of: str = None, direction: str = "outgoing"):
        """Get all relationships for an entity."""
        eid = self._entity_id(name)
        results = []
        with self._lock:
            conn = self._conn()

            if direction in ("outgoing", "both"):
                query = "SELECT t.*, e.name as obj_name FROM triples t JOIN entities e ON t.object = e.id WHERE t.subject = ?"
                params = [eid]
                if as_of:
                    query += " AND (t.valid_from IS NULL OR t.valid_from <= ?) AND (t.valid_to IS NULL OR t.valid_to >= ?)"
                    params.extend([as_of, as_of])
                for row in conn.execute(query, params).fetchall():
                    results.append(
                        {
                            "direction": "outgoing",
                            "subject": name,
                            "predicate": row["predicate"],
                            "object": row["obj_name"],
                            "valid_from": row["valid_from"],
                            "valid_to": row["valid_to"],
                            "confidence": row["confidence"],
                            "source_closet": row["source_closet"],
                            "current": row["valid_to"] is None,
                        }
                    )

            if direction in ("incoming", "both"):
                query = "SELECT t.*, e.name as sub_name FROM triples t JOIN entities e ON t.subject = e.id WHERE t.object = ?"
                params = [eid]
                if as_of:
                    query += " AND (t.valid_from IS NULL OR t.valid_from <= ?) AND (t.valid_to IS NULL OR t.valid_to >= ?)"
                    params.extend([as_of, as_of])
                for row in conn.execute(query, params).fetchall():
                    results.append(
                        {
                            "direction": "incoming",
                            "subject": row["sub_name"],
                            "predicate": row["predicate"],
                            "object": name,
                            "valid_from": row["valid_from"],
                            "valid_to": row["valid_to"],
                            "confidence": row["confidence"],
                            "source_closet": row["source_closet"],
                            "current": row["valid_to"] is None,
                        }
                    )
        return results

    def query_relationship(self, predicate: str, as_of: str = None):
        """Get all triples with a given relationship type."""
        pred = predicate.lower().replace(" ", "_")
        conn = self._conn()
        query = """
            SELECT t.*, s.name as sub_name, o.name as obj_name
            FROM triples t
            JOIN entities s ON t.subject = s.id
            JOIN entities o ON t.object = o.id
            WHERE t.predicate = ?
        """
        params = [pred]
        if as_of:
            query += " AND (t.valid_from IS NULL OR t.valid_from <= ?) AND (t.valid_to IS NULL OR t.valid_to >= ?)"
            params.extend([as_of, as_of])

        results = []
        for row in conn.execute(query, params).fetchall():
            results.append(
                {
                    "subject": row["sub_name"],
                    "predicate": pred,
                    "object": row["obj_name"],
                    "valid_from": row["valid_from"],
                    "valid_to": row["valid_to"],
                    "current": row["valid_to"] is None,
                }
            )
        return results

    def timeline(self, entity_name: str = None):
        """Get all facts in chronological order, optionally filtered by entity."""
        conn = self._conn()
        if entity_name:
            eid = self._entity_id(entity_name)
            rows = conn.execute(
                """
                SELECT t.*, s.name as sub_name, o.name as obj_name
                FROM triples t
                JOIN entities s ON t.subject = s.id
                JOIN entities o ON t.object = o.id
                WHERE (t.subject = ? OR t.object = ?)
                ORDER BY t.valid_from ASC NULLS LAST
                LIMIT 100
            """,
                (eid, eid),
            ).fetchall()
        else:
            rows = conn.execute("""
                SELECT t.*, s.name as sub_name, o.name as obj_name
                FROM triples t
                JOIN entities s ON t.subject = s.id
                JOIN entities o ON t.object = o.id
                ORDER BY t.valid_from ASC NULLS LAST
                LIMIT 100
            """).fetchall()

        return [
            {
                "subject": r["sub_name"],
                "predicate": r["predicate"],
                "object": r["obj_name"],
                "valid_from": r["valid_from"],
                "valid_to": r["valid_to"],
                "current": r["valid_to"] is None,
            }
            for r in rows
        ]

    def stats(self):
        conn = self._conn()
        entities = conn.execute("SELECT COUNT(*) as cnt FROM entities").fetchone()["cnt"]
        triples = conn.execute("SELECT COUNT(*) as cnt FROM triples").fetchone()["cnt"]
        current = conn.execute(
            "SELECT COUNT(*) as cnt FROM triples WHERE valid_to IS NULL"
        ).fetchone()["cnt"]
        expired = triples - current
        predicates = [
            r["predicate"]
            for r in conn.execute(
                "SELECT DISTINCT predicate FROM triples ORDER BY predicate"
            ).fetchall()
        ]
        return {
            "entities": entities,
            "triples": triples,
            "current_facts": current,
            "expired_facts": expired,
            "relationship_types": predicates,
        }
