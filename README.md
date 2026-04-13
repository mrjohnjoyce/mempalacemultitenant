# MemPalace Multi-Tenant (Neighborhoods)

This fork extends MemPalace to support multi-tenant environments where users can have isolated personal palaces while sharing access to a corporate "neighborhood" palace.

## Architecture

*   **The Neighborhood (The Organization):** A shared root directory containing a `corporate` palace and many `tenants` palaces.
*   **Isolation:** Every tenant has their own SQLite database for facts (Knowledge Graph) and their own ChromaDB directory for vector memories.
*   **The Conductor:** `neighborhood_service.py` is a FastAPI gateway that handles authentication (via headers) and federated search.

## How to use the CLI

You can now point any MemPalace command to a specific directory using the `--palace` flag:

```bash
# Initialize a corporate palace
mempalace init ~/company_docs --palace ~/neighborhoods/corporate

# Mine docs into the corporate palace
mempalace mine ~/company_docs --palace ~/neighborhoods/corporate

# Search a specific tenant's palace
mempalace search "my project status" --palace ~/neighborhoods/tenants/alice
```

## How to use the Web API (FastAPI)

1.  Set the root storage path:
    `export MEMPALACE_NEIGHBORHOOD_ROOT=~/my_neighborhoods`

2.  Start the service:
    `uvicorn neighborhood_service:app --port 8000`

3.  Query via Xojo (or any HTTP client):
    ```http
    POST /query
    X-Tenant-ID: alice@company.com
    X-Neighborhood-ID: acme_corp
    Content-Type: application/json

    {
      "prompt": "What is our policy on remote work?"
    }
    ```

The response will include a merged context from both the `acme_corp/corporate` palace and the `acme_corp/tenants/alice@company.com` palace.

## Deployment for Xojo Web

The Xojo Web app acts as the front-end gateway. It handles user login and then makes requests to this Python service using the user's email as the `X-Tenant-ID`. The service automatically handles the creation and isolation of each user's data folder.
