# BrickForge

**Describe your agent. Mage builds it.**

BrickForge is a pip-installable tool that takes you from zero to a live, production-grade AI agent on Databricks Apps. Tell **Mage** what you need in plain English and it designs the data model, generates everything, and deploys. Or use the visual **Setup Panel** for step-by-step control. No code, no notebooks, no YAML.

```bash
pip install brickforge
brickforge
```

!!! note "Beta"
    BrickForge is under active development. APIs and features may change.

---

## Two ways to build

| Path | For | How it works |
|------|-----|-------------|
| **[Mage](mage.md)** | Everyone | Conversational AI assistant. Describe your domain, Mage builds the agent. **Magic** mode for zero-config, **Author** mode for full control. |
| **[Setup Panel](setup-blocks.md)** | Power users | Visual DAG with 18 blocks. Configure each resource manually. |

Both produce the same output: a deployed Databricks App with a LangGraph agent and chat UI.

---

## What you get

A deployed Databricks App with:

- **LangGraph agent** backed by a Foundation Model (Claude, DBRX, Llama via serving endpoint)
- **Chat UI** with streaming responses, structured blocks, inline charts, action buttons
- **Auto-discovered tools** from your Unity Catalog schema (functions + stored procedures)
- **Genie NL-to-SQL** via MCP - ask data questions in natural language
- **Knowledge Assistants** - RAG over uploaded documents with source citations
- **Vector Search** - semantic document retrieval
- **External APIs** - REST calls via UC connections or direct HTTP
- **MCP servers** - connect any MCP-compatible tool server
- **A2A agents** - delegate to remote agents via Google A2A protocol
- **Per-user memory** - long-term recall backed by Lakebase
- **Charts** - inline bar, line, area, and pie visualizations

---

## How it works

### With Mage (recommended)

1. Open BrickForge, go to the **Mage** tab
2. Describe your domain: "I need an agent for my pet hotel"
3. Pick **Magic** (hands-off) or **Author** (full visibility)
4. Mage designs, generates, and deploys. You get a live URL.

### With the Setup Panel

| Step | What happens |
|------|-------------|
| **Connect** | Authenticate to any Databricks workspace via one-click OAuth. Token stored in OS keychain, never on disk. |
| **Generate** | Describe your domain in plain English. AI generates table schemas, synthetic data, SQL functions, stored procedures, system prompts, and a knowledge base. |
| **Wire** | Pick a model endpoint. Connect Genie, KA, Vector Search, APIs, MCP servers, or other agents. Toggle features. |
| **Deploy** | One click. Bundles code + config + chat UI, deploys to Databricks Apps, auto-grants all UC permissions. |
| **Iterate** | Save projects, export as `.forge` bundles, share with colleagues. Push to GitHub. Clean up when done. |

---

## 18 setup blocks

Every resource your agent needs, covered by a visual step:

`Workspace` `SQL Warehouse` `Unity Catalog` `Data Tables` `Functions` `Model Endpoint` `Agent Prompt` `Genie Space` `Agent Bricks` `Vector Search` `MCP Servers` `REST APIs` `A2A Agents` `Features` `Lakebase` `MLflow` `Deploy` `GitHub`

Each block follows the same pattern: **choose** an approach, **configure**, **execute**, **done**.

---

## Documentation

| Section | What it covers |
|---------|---------------|
| [Getting Started](getting-started.md) | Install, first run, connect workspace, pick warehouse, set schema |
| [Mage](mage.md) | Conversational agent builder -- Magic mode, Author mode, discovery, self-critique, build pipeline |
| [Setup Blocks](setup-blocks.md) | All 18 blocks - choices, actions, what happens on execute |
| [Data Generation](data-generation.md) | AI wizard: domain description to tables, functions, procedures, prompts |
| [Agent Tools](agent-tools.md) | All tool types: UC functions, Genie, KA, APIs, MCP, A2A, charts, memory |
| [Prompt System](prompt-system.md) | System prompt, knowledge base, generation, project-scoped prompts |
| [Deploy](deploy.md) | Bundle build, upload, app creation, grants pipeline |
| [Projects](projects.md) | Save, load, export .forge bundles, import on different workspaces |
| [Config](config.md) | config.json system, no .env files, token security, flatten() |
| [Evaluation](evaluation.md) | MLflow eval pipeline, LLM judge scorer, test datasets |
| [GitHub Integration](github-integration.md) | Push to GitHub, own the code, vibe on top |
| [Architecture](architecture.md) | Setup App + Agent App, config flow, package structure |

### Reference

| Section | What it covers |
|---------|---------------|
| [Tools Table](reference/tools-table.md) | Complete tools reference with discovery method, feature gates, source files |
| [Config Reference](reference/config-reference.md) | Full config.json schema - every field, type, env var mapping |
| [Known Issues](reference/known-issues.md) | Current known issues and workarounds |

---

## Links

- **Website**: [brickforge.dev](https://brickforge.dev)
- **PyPI**: [pypi.org/project/brickforge](https://pypi.org/project/brickforge/)
- **GitHub**: [github.com/mehdi-dbx/brickforge](https://github.com/mehdi-dbx/brickforge)
