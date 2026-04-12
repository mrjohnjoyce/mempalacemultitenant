# MemPalace Neighborhood API Guide

This document describes how to integrate any application (Xojo, React, Python, etc.) with the MemPalace Multi-Tenant Service.

## 1. Authentication & Headers

The service uses HTTP headers to route requests to the correct "Palace" folder. Every request MUST include:

| Header | Description | Example |
| :--- | :--- | :--- |
| `X-Tenant-ID` | Unique ID for the user (usually email). | `alice@company.com` |
| `X-Neighborhood-ID` | Unique ID for the organization/company. | `acme_corp` |

## 2. Endpoints

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

## 3. The "Memory Loop" Workflow

1.  **Recall:** Send the user's question to `/query`.
2.  **Generate:** Send the `augmented_prompt` from the response to your LLM (Gemini).
3.  **Commit:** Send the user's question + the LLM's answer + a 1-line summary to `/ingest`.

By following this loop, the AI will "remember" every conversation the next time the user asks a question.
