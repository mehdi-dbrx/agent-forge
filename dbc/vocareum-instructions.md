# Agent Forge → Vocareum: Setup Instructions

## Big Picture

We're porting Agent Forge into a **Vocareum lab environment**. Vocareum is a managed lab platform used for Databricks training — it spins up ephemeral Databricks workspaces for students. Each student gets their own workspace, one user per workspace.

The goal: create a **setup notebook** (`agent_setup`) that, when executed as a workspace provisioning job, bootstraps everything Agent Forge needs — Unity Catalog objects, seed data, stored procedures, and the agent application.

This notebook will be packaged as `agent_setup.zip`, placed in the Vocareum courseware folder, and referenced in `config.json` as a `workspace_setup` entry. It runs automatically during workspace provisioning with **admin privileges** (workspace admin + metastore admin via the platform's Service Principal).

## What the Notebook Needs to Do

Replicate the Agent Forge data layer and agent runtime. Specifically:

1. **Data layer** (Unity Catalog objects — use catalog `dbacademy`, create schema `airops`):
   - Create `airops` schema with appropriate grants (`ALL PRIVILEGES` to `account users`)
   - Create `flights` table with seed data (4 rows)
   - Create `update_flight_risk` stored procedure
   - Any other tables/views the agent tools expect (checkin metrics, etc.)

2. **Agent runtime**:
   - The agent needs to run somewhere accessible to the student
   - Options: Databricks notebook with inline agent, serving endpoint, or a job
   - The student should be able to interact with it through some interface

3. **Python dependencies**:
   - Can be installed via `%pip install` in the notebook
   - Or declared as cluster libraries
   - Key packages: langchain, langgraph, databricks-langchain, fastapi, uvicorn

## Constraints

- **Each workspace is ephemeral** — spun up fresh for each student. Everything must be reproducible from the notebook alone.
- **The notebook runs as admin** — it has full workspace and metastore privileges. But the lab user (`labuser*@vocareum.com`) has limited permissions, so any objects created need explicit grants to `account users`.
- **Catalog is `dbacademy`** — this is the workspace default, set by the platform. Don't change it or create new catalogs.
- **One user per workspace** — no multi-tenancy concerns.

## Deliverable

A Databricks notebook (Python) named `agent_setup` that can be:
1. Exported/zipped as `agent_setup.zip`
2. Dropped into a courseware folder
3. Run as a serverless job during workspace provisioning

It should be self-contained — all SQL, grants, data seeding, and any agent deployment logic in one notebook (or a small set of notebooks in the same zip).

## Reference

- Agent Forge source code is in this repo — look at `data/init/`, `data/proc/`, `tools/`, `agent/` for what needs to be replicated
- `docs/context-for-claude-code.md` has the full Agent Forge project context
- The Vocareum project with the SOP doc lives at `/Users/mehdi.lamrani/code/code/agentic-vocareum/` if you need to check how the platform works
