# MemPalace Neighborhood API Guide

This document describes how to integrate any application (Xojo, React, Python, etc.) with the MemPalace Multi-Tenant Service.

## 1. Authentication & Headers

The service uses HTTP headers to route requests to the correct "Palace" folder. Every request MUST include:

| Header | Description | Example |
| :--- | :--- | :--- |
| `X-Tenant-ID` | Unique ID for the user (usually email). | `alice@company.com` |
| `X-Neighborhood-ID` | Unique ID for the organization/company. | `acme_corp` |

## 2. Endpoints

### `GET /status`
Returns the wing/room breakdown and total drawer count for the user's Personal Palace.

**Headers:**
`X-Tenant-ID`, `X-Neighborhood-ID`

**Response:**
```json
{
  "status": "success",
  "neighborhood": "acme_corp",
  "tenant": "alice@company.com",
  "palace": {
    "total_drawers": 150,
    "taxonomy": {
      "identity": { "persona": 1 },
      "corporate": { "knowledge_base": 149 }
    }
  }
}
```

---

### `POST /wings`
Explicitly create a new wing (project/workspace) in the user's Palace.

**Request Body:**
```json
{ "wing": "project_apollo" }
```

---

### `POST /ingest/bulk`
Ingest multiple pieces of content at once. Use this for "API-based Mining" when you don't have direct filesystem access.

**Request Body:**
```json
{
  "wing": "project_apollo",
  "items": [
    { "title": "Requirements", "content": "Need 5 motors...", "room": "specs" },
    { "title": "Budget", "content": "$50k total", "room": "planning" }
  ]
}
```

---

### `POST /query`
Fetches merged context from the shared Corporate Palace and the user's Personal Palace.

**Request Body:**
```json
{
  "prompt": "What is our policy on remote work?",
  "limit": 5
}
```

**Response:**
```json
{
  "status": "success",
  "context": {
    "corporate": ["Remote work is allowed up to 2 days per week..."],
    "personal": ["I worked from home last Tuesday and it was productive."],
    "facts": [{"subject": "Remote Work", "predicate": "policy", "object": "Hybrid"}]
  },
  "augmented_prompt": "... (A ready-to-use prompt containing all context) ..."
}
```

---

### `POST /ingest`
Saves a completed conversation into the user's private memory. Call this AFTER your AI (Gemini/Claude) has responded.

**Request Body:**
```json
{
  "prompt": "What is our policy on remote work?",
  "response": "According to the corporate handbook, you can work remotely 2 days a week.",
  "diary_summary": "SESSION:2026-04-12|query.remote_policy|ALC.noted:hybrid_2_days|★",
  "agent_name": "Gemini",
  "topic": "policy"
}
```

**Response:**
```json
{
  "status": "success",
  "drawer_id": "drawer_wing_user_...",
  "diary_id": "diary_wing_gemini_..."
}
```

## 3. Loading Base Information (Mining)

Before using the API, you can seed the Corporate or Personal Palaces with existing data. You must **initialize** a directory first to create a `mempalace.yaml` configuration before you can **mine** it.

### Step 1: Activate Environment
```bash
source venv_multitenant/bin/activate
```

### Step 2: Initialize the Directory
This scans your source folder and creates the required `mempalace.yaml` file.
```bash
python -m mempalace init "/path/to/your/docs" --yes
```

### Step 3: Load Corporate (Shared) Palace
Load official company docs into the shared hub:
```bash
python -m mempalace --palace ~/mempalace_neighborhoods/acme_corp/corporate mine "/path/to/your/docs" --wing corporate
```

### Step 4: Load User (Private) Palace
Load private notes into a specific user's isolated storage:
```bash
python -m mempalace --palace ~/mempalace_neighborhoods/acme_corp/tenants/alice@company.com mine "/path/to/private/notes" --wing identity
```

---

## 4. The "Memory Loop" Workflow

1.  **Recall:** Send the user's question to `/query`.
2.  **Generate:** Send the `augmented_prompt` from the response to your LLM (Gemini).
3.  **Commit:** Send the user's question + the LLM's answer + a 1-line summary to `/ingest`.

By following this loop, the AI will "remember" every conversation the next time the user asks a question.
