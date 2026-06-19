# Getting Started

## Prerequisites

- Python 3.11+
- A Databricks workspace with:
    - A running SQL warehouse
    - Access to Unity Catalog
    - A Foundation Model API endpoint (Claude, Llama, Mixtral, etc.)

## Install

```bash
pip install brickforge
```

To pin a specific version:

```bash
pip install brickforge==0.1.0a33
```

## First run

```bash
brickforge
```

This starts the Setup App (FastAPI backend + React frontend) on port 9000. Open `http://localhost:9000` in your browser.

```bash
brickforge --version   # print version and exit
brickforge --help      # show CLI options
```

## Connect your workspace

The first setup block is **Workspace**. Two options:

### Option A: Bridge OAuth (recommended)

1. Click **Bridge-Forge** in the workspace block
2. A shell command appears - copy and run it in your terminal
3. Your browser opens for Databricks OAuth
4. On success, a PAT is created (7-day TTL) and saved automatically

The bridge flow handles everything: OAuth PKCE, PAT creation, IP whitelist, token encryption.

### Option B: Manual entry

1. Click **Manual** in the workspace block
2. Paste your workspace URL (e.g. `https://my-workspace.cloud.databricks.com`)
3. Paste a Personal Access Token
4. Click Save

!!! tip
    BrickForge auto-prepends `https://` if you forget it. Saved workspaces are remembered for quick switching.

## Pick a SQL warehouse

The **SQL Warehouse** block lists all running warehouses in your workspace. Click one to select it.

!!! note
    The warehouse must be in RUNNING state. BrickForge does not start stopped warehouses.

## Set your Unity Catalog schema

The **Unity Catalog** block lets you:

- **Select** an existing `catalog.schema`
- **Create** a new one (BrickForge creates both catalog and schema if needed)

This schema is where all your tables, functions, and procedures land.

## Next steps

### Fastest path: use Mage

Click the **Mage** tab. Describe what you want. Mage handles the rest -- data model, generation, prompts, deploy. See [Mage](mage.md).

### Manual path: Setup Panel

With workspace, warehouse, and schema configured, work through the [setup blocks](setup-blocks.md) top to bottom:

- [Generate synthetic data](data-generation.md) with the AI wizard
- [Configure agent tools](agent-tools.md) (Genie, KA, APIs)
- [Deploy your agent](deploy.md) to Databricks Apps

Each block follows the same pattern: choose an approach, configure, execute, done.
