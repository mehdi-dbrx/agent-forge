# BrickForge - YouTube Video Script

> Duration target: 10-11 minutes
> Tone: Direct, no fluff, show-don't-tell. Developer speaking to developers/SAs.

---

## INTRO (0:00 - 0:45)

**[0:00] [Screen: terminal, dark background]**

You want to build an AI agent on Databricks. You need tables, functions, a model endpoint, Genie, maybe a Knowledge Assistant, a chat UI, deploy it as an app, wire up the permissions. That's a dozen services, hundreds of lines of config, and a week of your time.

**[0:15]**

BrickForge wires them all together for you. All you need is a pip install:

```
pip install brickforge
```

**[0:25] [Screen: Setup App opens in browser]**

BrickForge is a single pip package that gives you a visual setup app. You describe your domain, it generates everything. Data, functions, prompts. And deploys a production agent to Databricks Apps. No notebooks. No YAML to write. No repo to clone to get started. You can also bring your own data and wire up existing assets.

**[0:40]**

Let me show you. We'll build one from scratch, but if you're in a hurry - BrickForge ships with pre-built templates. Pick one, connect your workspace, deploy. Under two minutes.

---

## WHY THIS EXISTS (0:50 - 1:30)

**[0:45] [Screen: side-by-side -manual setup vs BrickForge]**

Building a Databricks agent today means stitching together a dozen pieces manually. Unity Catalog schemas, SQL functions, stored procedures, model endpoints, Genie spaces, Knowledge Assistants, the agent code itself, the chat UI, the deploy pipeline, the grants. Each one is a separate doc page, a separate API, a separate config format.

**[0:55]**

BrickForge wraps all of that into 18 setup blocks. Each block follows the same pattern: choose an approach, configure, execute, done. The setup app walks you through them top to bottom.

**[1:05] [Screen: DAG view showing 18 blocks with green/gray status]**

Think of it as a directed graph of your agent's infrastructure. Green means configured. Gray means not yet. You work through them in order, or jump to any block.

**[1:15]**

And here's the key: everything you build is portable. Your entire agent - config, data schemas, functions, prompts, knowledge base - saves as a single `.forge.zip` bundle. Export it, share it with a colleague, load it on a completely different workspace, deploy it there. Build once on your dev workspace, deploy to production. Hand it to a customer, they load it and run. No vendor lock-in, no hidden state. You own the code, the config, everything.

---

## STEP 1: CONNECT (1:30 - 2:30)

**[1:30] [Screen: Setup App, project menu in top bar]**

First thing: create a project. *Click the project dropdown, "New Project", name it.* Each project is a separate agent with its own config, data, and tools. You can have multiple projects on the same workspace. But right now, let's build our first one.

**[1:40] [Screen: Workspace block in drawer]**

First block: connect to your Databricks workspace. Three options - pick a saved workspace, authenticate via bridge-forge, or paste a host and token manually. Bridge-forge opens your browser, authenticates via OAuth, creates a token, and saves it to your OS keychain. One click. Your credentials never touch disk.

**[1:50] [Click bridge-forge, show OAuth flow]**

**[2:00] [Click warehouse block, show picker]**

Then pick a SQL warehouse. BrickForge lists the running ones -*click to select.*

**[2:10] [Show schema block]**

And set your Unity Catalog schema. *Pick an existing catalog or type one.* BrickForge creates the catalog and schema if they don't exist.

**[2:20]**

Three blocks done. Your workspace is connected.

---

## STEP 2: GENERATE DATA + FUNCTIONS (2:15 - 3:30)

**[2:15] [Screen: Data Tables block]**

This is where it gets interesting. You have four options for data: generate synthetic data with AI, connect existing tables, upload CSVs, or use demo data.

**[2:25]**

Let's generate. *Click "Generate Synthetic Data"* -you land in the data wizard.

**[2:30] [Screen: Data Gen wizard, domain textarea]**

Describe your domain in plain English. "E-commerce platform with customers, products, orders, and reviews." *Hit generate.*

**[2:40] [Show LLM generating table schemas, then rows]**

The model designs your table schemas, generates synthetic rows, and saves them as CSVs. *Review the schemas, adjust if needed, then provision to Unity Catalog.*

**[2:55] [Show provision step with SSE terminal output]**

**[3:05]**

Tables created. Now functions. Same wizard - the model generates SQL functions and stored procedures from your table schemas.

**[3:10]**

Watch the terminal here. The SQL generation has a self-healing loop. If a generated function fails when executed against Databricks - wrong column name, syntax error, type mismatch - BrickForge captures the exact error, feeds it back to the model, and the model fixes it. It'll retry up to three times. Most failures resolve on the first retry.

**[3:20] [Show routine gen + self-healing in terminal - error, retry, success]**

**[3:30]**

All your data infrastructure - tables, functions, procedures - generated from a text description. We'll go deeper on the SQL generation pipeline in a future video - there's a 5-layer defense system under the hood.

---

## STEP 3: WIRE THE AGENT (3:40 - 5:10)

**[3:30] [Screen: Model block]**

Pick your Foundation Model. Auto-detect scans your workspace for every available serving endpoint. Claude, Llama, Mixtral, DBRX - anything served via Foundation Model APIs works. BrickForge is model-agnostic. You're not locked into one provider. *Click to select.*

**[3:50] [Show model auto-detect picker with multiple endpoints listed]**

**[3:55]**

Next: the agent prompt. BrickForge generates a system prompt tailored to your domain and tables. *Or edit it manually.*

**[3:55] [Show prompt editor]**

**[4:05]**

Now the interesting wiring. Genie gives your agent natural-language SQL -it asks Genie questions, Genie writes the SQL, queries your tables, returns results. No prompt engineering for SQL.

**[4:15] [Show Genie block, pick existing space]**

**[4:20]**

Agent Bricks -these are toggleable AI building blocks. Knowledge Assistant for RAG over documents, Information Extraction, Document Parsing, Text Classification. Each is a toggle. *Enable KA, pick an existing endpoint or provision one from PDFs.*

**[4:30] [Show Bricks block, toggle KA on, show Lakebase picker]**

**[4:40]**

Then external connections. MCP servers let you plug in any MCP-compatible tool server - weather, Slack, custom internal services. REST APIs connect via UC-governed connections or direct HTTP.

**[4:45] [Show MCP block, add a server]**

**[4:50]**

And A2A - Google's Agent-to-Agent protocol. Your agent can delegate tasks to other agents over HTTP. Add a remote agent URL, BrickForge discovers its capabilities via the Agent Card, and it becomes a callable tool. Multi-agent orchestration out of the box.

**[4:55] [Show A2A block, add an agent URL]**

**[5:00]**

Features toggle: memory (per-user long-term memory via Lakebase), charts (inline in chat), voice input, dashboard (live data tables on the home page). All toggleable, all optional.

**[5:05] [Show Features block with toggles]**

---

## STEP 4: DEPLOY (5:10 - 6:30)

**[5:10] [Screen: Deploy block]**

*Set your app name.* *Hit deploy.*

**[5:20] [Click Deploy Now, show terminal streaming]**

BrickForge bundles your agent code, the chat UI, your config, uploads to the workspace, creates the Databricks App, deploys, waits for it to start, then runs all the UC grants automatically. And on redeploy, the virtual environment is reused - no cold start, no reinstalling 160 packages. Just your code changes, pushed and live.

**[5:35] [Show progress: bundle -> upload -> deploy -> grants -> app is live]**

**[5:55]**

You get a URL. *Click it.*

**[6:00] [Open deployed app in browser]**

That's your agent. Chat UI with your branding, your tools, your data. *Ask it a question.*

**[6:10] [Type a question, show agent calling Genie, returning data, generating a chart]**

**[6:20]**

The agent calls Genie for SQL, uses your stored procedures for mutations, renders charts inline, and the dashboard shows live table data that updates when the agent modifies records.

---

## STEP 5: PORTABLE (6:30 - 7:15)

**[6:30] [Screen: back to Setup App, project menu]**

Your agent is live. But here's what makes this different: everything you just built is portable.

**[6:35]**

*Click the export icon.* That downloads a `.forge.zip` bundle. Your config, prompts, generated SQL, functions, procedures. The entire agent in one file.

**[6:40] [Show export, show the zip in Finder]**

**[6:45]**

Now watch. Different workspace. *Open BrickForge, click import, drop the bundle in.* The project loads with all its config intact. *Hit deploy.* Same agent, new workspace. That's the workflow: build on dev, export, deploy to production. Hand it to a customer, they load it and run.

**[7:00] [Show import flow on a different workspace]**

**[7:10]**

No hidden state. You own everything. And later, we'll push this whole agent to GitHub - but let's keep going.

---

## STEP 6: ITERATE (7:15 - 8:00)

**[7:15] [Screen: Setup App]**

Now iterate. Change the prompt, add a new tool, toggle a feature, redeploy. Same flow, same blocks.

**[7:25] [Show project menu]**

Multiple projects per workspace. Each one is a separate agent with its own config, data, and tools. *Switch between them with one click.*

**[7:30] [Show project switcher, click between projects]**

**[7:35]**

And if you work across multiple workspaces, BrickForge remembers them. Every workspace you connect to is saved. *Click the workspace block, pick from saved workspaces.* One click to switch.

**[7:40] [Show saved workspace list, click to switch]**

**[7:50]**

And when you're done, the cleanup block discovers all resources BrickForge created and lets you tear them down cleanly.

---

## STEP 7: OWN THE CODE (8:00 - 9:00)

**[8:00] [Screen: Source Control block in setup panel]**

This is important. BrickForge is not a black box. Everything it generates is real code you can take over.

**[8:10]**

*Click Source Control, connect a GitHub repo.* BrickForge pushes the full agent source: the LangGraph agent, the tools, the SQL functions, the stored procedures, the chat UI, the system prompt, the config. All of it. Real Python. Real TypeScript. Real SQL.

**[8:20] [Show GitHub repo with pushed code]**

**[8:25]**

Now you're in full control. Clone the repo, run `./start_local.sh`. It checks your Python version, checks for Node.js, handles authentication - finds your Databricks CLI profile or walks you through creating one - installs deps, and starts the server. One command, zero config.

**[8:10] [Show terminal: ./start_local.sh running pre-flight checks, starting server]**

**[8:20]**

Open it in your editor. Tweak the agent logic, customize the chat UI, add your own tools, refactor the prompts. Use Claude Code, Cursor, any AI IDE. Vibe it. Make it yours.

**[8:30] [Show VS Code / editor with agent code open]**

**[8:35]**

Push your changes. Set up CI/CD. Deploy from your pipeline instead of the setup panel. BrickForge got you from zero to working agent. Now you graduate to your own codebase and workflow.

**[8:40] [Show git push, CI pipeline running]**

**[8:50]**

That's the philosophy: BrickForge is the scaffolding, not the cage. Use it to build fast, then own what you built.

---

## WHAT'S UNDER THE HOOD (9:00 - 9:40)

**[9:00] [Screen: architecture diagram]**

Two services in one Databricks App:

- MLflow AgentServer on port 8000 -LangGraph agent with LangChain tools, Foundation Model endpoint
- Chat UI on port 3000 -React frontend, Express backend, Vercel AI SDK for streaming

**[9:15]**

All config lives in a single config.json. No env vars in app.yaml. The agent reads config at boot, flattens to env vars, and every tool discovers itself.

**[9:25]**

Tools are auto-discovered from Unity Catalog. Drop a Python file with @tool functions into the tools folder -it's automatically loaded. No registration, no wiring.

---

## CLOSING (9:40 - 10:10)

**[9:40] [Screen: terminal]**

```
pip install brickforge
brickforge
```

**[9:50]**

That's it. From zero to a deployed AI agent on Databricks. Describe your domain, generate everything, deploy with one click.

**[10:00]**

BrickForge is open source, on PyPI, and in beta. Links in the description.

---

## NEXT VIDEOS (10:10 - 10:40)

**[10:10]**

There's also a built-in evaluation pipeline. MLflow experiment, custom LLM judge, baseline vs with-guideline scoring. You can see how your prompt changes affect quality before you redeploy.

**[10:20] [Quick flash: MLflow eval UI showing comparison metrics]**

In the next videos, we'll go deeper:

- **Agent Evaluation** - run the eval pipeline, tune your prompts with data, compare runs side-by-side
- **Knowledge Assistants** - upload documents, build a RAG pipeline, wire it into your agent with citations
- **Custom Tools** - write your own @tool functions, add external APIs, connect MCP servers
- **Per-User Memory** - enable Lakebase-backed long-term memory so the agent remembers across sessions
- **Vibe Coding** - push to GitHub, clone the repo, customize agent logic and chat UI with AI-assisted coding

**[10:35] [Screen: brickforge.dev landing page]**

---

## VIDEO METADATA

**Title**: BrickForge: Build & Deploy Databricks AI Agents in Minutes

**Description**:
BrickForge is a pip-installable tool that takes you from zero to a live AI agent on Databricks Apps. No code, no notebooks, no YAML.

- pip install brickforge
- Describe your domain in plain English
- AI generates tables, functions, stored procedures, prompts
- Wire Genie, Knowledge Assistants, APIs, MCP servers
- One-click deploy to Databricks Apps
- Live dashboard, inline charts, per-user memory

Links:
- PyPI: https://pypi.org/project/brickforge/
- GitHub: https://github.com/mehdi-dbx/brickforge
- Website: https://brickforge.dev

**Tags**: databricks, ai agents, langchain, langgraph, mlflow, unity catalog, genie, knowledge assistant, mcp, deploy, no-code, pip
