App-specific code lives here so custom product features stay isolated from the
upstream CLI and scraper engine as much as possible.

- `web_api/` contains the FastAPI app, API-focused services, and background workers.
- `frontend/` is reserved for a future UI so it can evolve without scattering files
  across the upstream project layout.

Legacy paths like `api/`, `workers/`, and some `services/` modules remain as thin
compatibility wrappers to keep imports stable while concentrating implementation
under `apps/`.
