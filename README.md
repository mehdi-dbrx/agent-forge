# agent-forge

## Getting Started

### 1. Install dependencies

#### Python

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync
```

This creates `.venv/` and installs all pinned dependencies from `uv.lock` — including `databricks-sdk>=0.102.0`.

> Fallback (without uv): `pip install -r requirements.txt`

#### Visual app (optional)

Requires [Node.js](https://nodejs.org/) (v18+).

```bash
cd visual && bash start.sh
```

`start.sh` installs Node deps automatically on first run via `npm ci`. Opens the architecture explorer at **http://localhost:9000**.

### 2. Configure environment

```bash
cp config/.env.example .env.local
```

Then run the guided setup script — it walks through every required env var and provisions Databricks resources interactively:

```bash
./scripts/sh/setup_dbx_env.sh
```

To check current configuration status without making changes:

```bash
./scripts/sh/setup_dbx_env.sh --check
```

### 3. Run locally

```bash
./scripts/sh/start_local.sh
```

---

## Project Structure

See [`docs/Build & setup flow.md`](docs/Build%20&%20setup%20flow.md) for a full overview of scripts, data init, tools, and agent layers.
