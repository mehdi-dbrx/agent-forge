# Databricks notebook source

# MAGIC %md
# MAGIC # Agent Workshop -- Build Agentic Apps on Databricks

# COMMAND ----------

# MAGIC %pip install databricks-langchain==0.15.0 databricks-ai-bridge==0.14.1 databricks-mcp==0.8.0 databricks-openai==0.11.1 databricks-sdk==0.102.0 databricks-vectorsearch==0.65 langchain==1.2.10 langchain-core==1.2.13 unitycatalog-langchain==0.3.0 mlflow==3.9.0 mlflow-skinny==3.9.0 mlflow-tracing==3.9.0 openai==2.21.0 pandas==2.3.3 gtts -q
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC We're building **Garv** -- an AI ops advisor for airport check-in operations. It monitors live check-in performance, flags at-risk flights, recommends staff redeployment, and answers passenger rights questions using EU regulations. The entire app runs on Databricks.

# COMMAND ----------

# Shared diagram styles + SVG sprites — used by displayHTML diagram cells below
AF_STYLES = """
<svg style="display:none" xmlns="http://www.w3.org/2000/svg">
  <symbol id="af-user"     viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></symbol>
  <symbol id="af-monitor"  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></symbol>
  <symbol id="af-cpu"      viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></symbol>
  <symbol id="af-tool"     viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></symbol>
  <symbol id="af-message"  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></symbol>
  <symbol id="af-book"     viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></symbol>
  <symbol id="af-database" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></symbol>
  <symbol id="af-table"    viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="9" x2="9" y2="21"/></symbol>
  <symbol id="af-bolt"     viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></symbol>
  <symbol id="af-layers"   viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></symbol>
  <symbol id="af-server"   viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></symbol>
  <symbol id="af-package"  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 002 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></symbol>
  <symbol id="af-arrow"    viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></symbol>
  <symbol id="af-cloud"    viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z"/></symbol>
  <symbol id="af-megaphone" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11l18-5v12L3 13v-2z"/><path d="M11.6 16.8a3 3 0 11-5.8-1.6"/></symbol>
  <symbol id="af-search"   viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></symbol>
  <symbol id="af-check"    viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></symbol>
</svg>
<style>
  .af * { box-sizing: border-box; margin: 0; padding: 0; }
  .af { font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f6f7; border-radius: 14px; padding: 1.8rem 2rem; }
  .af-flow { display: flex; align-items: center; justify-content: center; gap: 0.6rem; flex-wrap: wrap; }
  .af-flow-col { display: flex; flex-direction: column; align-items: center; gap: 0.35rem; }
  .af-fbox {
    background: #f0f1f2; border: 1px solid #d6d9dc; border-radius: 12px;
    padding: 1rem 1.4rem; display: flex; flex-direction: column; align-items: center;
    gap: 0.35rem; min-width: 130px; text-align: center;
    font-size: 0.95rem; font-weight: 600; color: #111314;
  }
  .af-fbox small { color: #7e8a95; font-size: 0.78rem; font-weight: 400; }
  .af-fbox.fa { border-color: #eb1600; background: rgba(235,22,0,0.07); }
  .af-fbox.fb { border-color: #1b73e8; background: rgba(27,115,232,0.08); }
  .af-fbox.fg { border-color: #1a9e67; background: rgba(26,158,103,0.08); }
  .af-fbox.fp { border-color: #6d28d9; background: rgba(109,40,217,0.08); }
  .af-fbox.fam { border-color: #b87200; background: rgba(184,114,0,0.08); }
  .af-arrow { color: #bec3c8; display: flex; align-items: center; }
  .af-or { font-size: 0.68rem; color: #7e8a95; font-weight: 600; padding: 0.1rem 0; }
  .af-ico { display: block; width: 32px; height: 32px; }
  .af-ico-sm { width: 20px; height: 20px; }
  .af-cr { color: #eb1600; } .af-cb { color: #1b73e8; } .af-cg { color: #1a9e67; }
  .af-cp { color: #6d28d9; } .af-ca { color: #b87200; } .af-cm { color: #7e8a95; }
  .af-eq { font-size: 1.4rem; font-weight: 800; color: #bec3c8; padding: 0 0.3rem; }
</style>
"""

# COMMAND ----------

# MAGIC %md
# MAGIC An agentic app is built from four ingredients:
# MAGIC
# MAGIC - A **Foundation Model** -- the LLM that reasons, understands context, and decides what to do next
# MAGIC - **Tools** -- functions the model can call to read data, run queries, or take actions (SQL, Genie, Knowledge Assistant)
# MAGIC - A **Prompt** -- the instruction manual that defines the agent's persona, scope, and behavior rules
# MAGIC - A **LangChain Agent** -- the orchestrator that ties it all together in a decide-execute-respond loop
# MAGIC
# MAGIC Combine them and you get a deployed application that can reason, act, and respond -- all governed by Databricks.

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div class="af-flow">
    <div class="af-fbox fa">
      <svg class="af-ico af-cr"><use href="#af-cpu"/></svg>
      Foundation Model
      <small>LLM brain</small>
    </div>
    <span class="af-eq">+</span>
    <div class="af-fbox fb">
      <svg class="af-ico af-cb"><use href="#af-tool"/></svg>
      Tools
      <small>SQL, Genie, VS, KA</small>
    </div>
    <span class="af-eq">+</span>
    <div class="af-fbox fg">
      <svg class="af-ico af-cg"><use href="#af-book"/></svg>
      Prompt
      <small>instructions</small>
    </div>
    <span class="af-eq">+</span>
    <div class="af-fbox fp">
      <svg class="af-ico af-cp"><use href="#af-layers"/></svg>
      LangChain Agent
      <small>orchestrator</small>
    </div>
    <span class="af-eq">=</span>
    <div class="af-fbox fa">
      <svg class="af-ico af-cr"><use href="#af-monitor"/></svg>
      Agentic App
      <small>deployed on Databricks</small>
    </div>
  </div>
</div>
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Meet the App
# MAGIC
# MAGIC Before we build anything, let's see the finished product in action.
# MAGIC
# MAGIC **How to access:**
# MAGIC 1. In the Databricks sidebar, go to **Compute** > **Apps**
# MAGIC 2. Find `agent-app` -- status should be **Running**
# MAGIC 3. Click the app URL: `https://agent-app-7474656474935136.aws.databricksapps.com`
# MAGIC
# MAGIC **Try it now:** The app shows suggested messages in the chat. Fire a few -- try *"Check-in Performance"* and follow the guided flow. Watch how the agent reasons, calls tools, and presents structured responses.
# MAGIC
# MAGIC Take 5 minutes to explore. We'll wait.

# COMMAND ----------

# MAGIC %md
# MAGIC Now that you've seen what the agent can do, let's look behind the scenes at the components that make it work -- and learn how to build each one on Databricks.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Workshop Roadmap
# MAGIC
# MAGIC | # | Module | Time | What you'll do |
# MAGIC |---|--------|------|----------------|
# MAGIC | 1 | **Foundation Models** | 15 min | Find models in UI, Playground, invoke via LangChain |
# MAGIC | 2 | **Unity Catalog** | 10 min | Governance layer that holds all assets |
# MAGIC | 3 | **Tables & Data** | 15 min | Explore 5 project tables, how data gets in |
# MAGIC | 4 | **Functions & Tools** | 20 min | Stored procedures -> UC tools -> LangChain |
# MAGIC | 5 | **Hands-on: PA Announcement** | 20 min | Build a complete feature end-to-end |
# MAGIC | 6 | **Genie** | 15 min | Natural-language SQL, play with Genie room, MCP |
# MAGIC | 7 | **Vector Search** | 15 min | Semantic search on documents, MCP |
# MAGIC | 8 | **Knowledge Assistant** | 10 min | RAG-as-a-service, invoke as tool |
# MAGIC | 9 | **The Agent App** | 20 min | Architecture, prompts, deployment |
# MAGIC | 10 | **Evaluation** | 15 min | MLflow GenAI scorers, improve prompt, re-evaluate |

# COMMAND ----------

# Setup — run this cell first
CATALOG = "amadeus"
SCHEMA = "airops"
SCHEMA_QUALIFIED = f"`{CATALOG}`.`{SCHEMA}`"
print(f"[+] Using schema: {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC Every agentic app starts with a brain. Let's meet ours.

# COMMAND ----------

# MAGIC %md
# MAGIC # Module 1 — Foundation Models
# MAGIC
# MAGIC **What:** Pre-trained LLMs served as API endpoints on Databricks (Claude, Llama, DBRX, etc.)
# MAGIC
# MAGIC - **Where in UI:** Left sidebar -> **AI Gateway** -> see all available foundation models
# MAGIC - Look for `databricks-claude-sonnet-4-6` — that's our agent's brain
# MAGIC
# MAGIC ### Try the Playground
# MAGIC
# MAGIC - Left sidebar -> **Playground** -> select an endpoint -> chat directly
# MAGIC - Try asking: *"What is EU Regulation EC 261?"*
# MAGIC - This is the **raw model** — no tools, no context, just the LLM
# MAGIC
# MAGIC **Do it now:** Open the Playground in another tab, pick `databricks-claude-sonnet-4-6`, and ask it a question.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Invoke a Foundation Model with LangChain
# MAGIC The code below does exactly what the Playground does — but programmatically.

# COMMAND ----------

from databricks_langchain import ChatDatabricks

llm = ChatDatabricks(endpoint="databricks-claude-sonnet-4-6")

# Simple invocation — just the raw LLM, no tools
response = llm.invoke("In one sentence, what is an airport check-in agent?")
print(response.content)

# COMMAND ----------

# MAGIC %md
# MAGIC > **Key takeaway:** A Foundation Model alone is just a text-in / text-out API. It has no access to your data, no ability to take actions. To make it **agentic**, we need to give it **tools** and **context**. That's what the rest of this workshop builds.

# COMMAND ----------

# MAGIC %md
# MAGIC An LLM that can think but can't see your data isn't very useful. We need a place to store tables, documents, and functions — governed and secure. That's Unity Catalog.

# COMMAND ----------

# MAGIC %md
# MAGIC # Module 2 — Unity Catalog
# MAGIC
# MAGIC **What:** Databricks' unified governance layer. **Every asset** in your workspace lives here.
# MAGIC
# MAGIC **Hierarchy:** `Catalog` -> `Schema` -> Assets (Tables, Volumes, Functions, Models)
# MAGIC
# MAGIC ### Our schema: `amadeus.airops`
# MAGIC
# MAGIC | Asset type | Count | Examples |
# MAGIC |-----------|-------|---------|
# MAGIC | **Tables** | 5 | flights, checkin_agents, checkin_metrics, border_officers, border_terminals |
# MAGIC | **Volumes** | 1 | PDF documents (EU passenger rights regulation) |
# MAGIC | **Models** | 0 | (we use a shared serving endpoint) |
# MAGIC | **Functions** | 1 | update_flight_risk (stored procedure) |
# MAGIC
# MAGIC **Where in UI:** Left sidebar -> **Catalog** -> browse `amadeus` -> `airops`
# MAGIC
# MAGIC **Do it now:** Open the Catalog explorer and browse `amadeus.airops`. Click on a table to see its schema and sample data.

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div style="display:flex;flex-direction:column;align-items:center;gap:0.5rem">
    <div class="af-fbox fp" style="min-width:200px">
      <svg class="af-ico af-cp"><use href="#af-layers"/></svg>
      amadeus
      <small>Catalog</small>
    </div>
    <div style="width:2px;height:16px;background:#bec3c8"></div>
    <div class="af-fbox fb" style="min-width:180px">
      <svg class="af-ico af-cb"><use href="#af-database"/></svg>
      airops
      <small>Schema</small>
    </div>
    <div style="width:2px;height:16px;background:#bec3c8"></div>
    <div style="display:flex;gap:0.6rem;flex-wrap:wrap;justify-content:center">
      <div class="af-fbox fg" style="min-width:110px">
        <svg class="af-ico-sm af-cg"><use href="#af-table"/></svg>
        Tables
        <small>5 tables</small>
      </div>
      <div class="af-fbox fam" style="min-width:110px">
        <svg class="af-ico-sm af-ca"><use href="#af-book"/></svg>
        Volumes
        <small>1 volume</small>
      </div>
      <div class="af-fbox fa" style="min-width:110px">
        <svg class="af-ico-sm af-cr"><use href="#af-tool"/></svg>
        Functions
        <small>1 procedure</small>
      </div>
      <div class="af-fbox" style="min-width:110px">
        <svg class="af-ico-sm af-cm"><use href="#af-cpu"/></svg>
        Models
        <small>shared endpoint</small>
      </div>
    </div>
  </div>
</div>
""")

# COMMAND ----------

# Explore what's in our schema programmatically
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

tables = list(w.tables.list(catalog_name=CATALOG, schema_name=SCHEMA))
print(f"[+] Tables in {CATALOG}.{SCHEMA}:")
for t in tables:
    print(f"    - {t.name} ({t.table_type.value})")

volumes = list(w.volumes.list(catalog_name=CATALOG, schema_name=SCHEMA))
print(f"\n[+] Volumes:")
for v in volumes:
    print(f"    - {v.name} (path: /Volumes/{CATALOG}/{SCHEMA}/{v.name})")

# COMMAND ----------

# MAGIC %md
# MAGIC Unity Catalog is the container. Now let's look at what's inside — the live operational data our agent monitors in real time.

# COMMAND ----------

# MAGIC %md
# MAGIC # Module 3 — Tables & Data
# MAGIC
# MAGIC Our agent operates on **5 tables** — this is the live operational data it monitors:
# MAGIC
# MAGIC | Table | Purpose | Key columns |
# MAGIC |-------|---------|-------------|
# MAGIC | `flights` | Flight schedule & risk status | flight_number, zone, departure_time, delay_risk |
# MAGIC | `checkin_metrics` | Zone performance metrics | zone, avg_checkin_time_mins, pct_change, baseline_mins |
# MAGIC | `checkin_agents` | Staff assignments | agent_id, name, zone, counter, at_counter |
# MAGIC | `border_officers` | Border control staffing | officer_id, name, zone, at_post |
# MAGIC | `border_terminals` | E-gate status | terminal_id, zone, status |
# MAGIC
# MAGIC ### How data gets in
# MAGIC
# MAGIC - **SQL INSERT** — seed data (what we did in setup)
# MAGIC - **Upload** — drag & drop CSV/Parquet in Catalog UI
# MAGIC - **Ingestion** — connect to S3, ADLS, Kafka, JDBC via Lakeflow
# MAGIC - **API** — write from your app (our agent updates tables via stored procedures)

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div style="display:flex;flex-direction:column;align-items:center;gap:0.5rem">
    <div style="display:flex;gap:0.6rem;flex-wrap:wrap;justify-content:center">
      <div class="af-fbox fg" style="min-width:140px">
        <svg class="af-ico-sm af-cg"><use href="#af-table"/></svg>
        flights
        <small>schedule &amp; risk</small>
      </div>
      <div class="af-fbox fg" style="min-width:140px">
        <svg class="af-ico-sm af-cg"><use href="#af-table"/></svg>
        checkin_metrics
        <small>zone performance</small>
      </div>
      <div class="af-fbox fg" style="min-width:140px">
        <svg class="af-ico-sm af-cg"><use href="#af-table"/></svg>
        checkin_agents
        <small>staff assignments</small>
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:0.4rem">
      <div style="width:60px;height:2px;background:#bec3c8"></div>
      <div class="af-fbox fa" style="min-width:160px">
        <svg class="af-ico af-cr"><use href="#af-cpu"/></svg>
        Agent
        <small>reads &amp; writes all tables</small>
      </div>
      <div style="width:60px;height:2px;background:#bec3c8"></div>
    </div>
    <div style="display:flex;gap:0.6rem;flex-wrap:wrap;justify-content:center">
      <div class="af-fbox fg" style="min-width:140px">
        <svg class="af-ico-sm af-cg"><use href="#af-table"/></svg>
        border_officers
        <small>border staffing</small>
      </div>
      <div class="af-fbox fg" style="min-width:140px">
        <svg class="af-ico-sm af-cg"><use href="#af-table"/></svg>
        border_terminals
        <small>e-gate status</small>
      </div>
    </div>
  </div>
</div>
""")

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Explore flights
# MAGIC SELECT * FROM `amadeus`.`airops`.flights

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Explore check-in agents
# MAGIC SELECT * FROM `amadeus`.`airops`.checkin_agents

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Explore check-in metrics
# MAGIC SELECT * FROM `amadeus`.`airops`.checkin_metrics

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Explore border officers
# MAGIC SELECT * FROM `amadeus`.`airops`.border_officers

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Explore border terminals
# MAGIC SELECT * FROM `amadeus`.`airops`.border_terminals

# COMMAND ----------

# MAGIC %md
# MAGIC ### How tables are created
# MAGIC
# MAGIC Here's how the `flights` table was created during setup — standard Delta Lake DDL:
# MAGIC
# MAGIC ```sql
# MAGIC CREATE OR REPLACE TABLE `amadeus`.`airops`.flights (
# MAGIC     flight_number STRING,
# MAGIC     zone STRING,
# MAGIC     departure_time TIMESTAMP_NTZ,
# MAGIC     delay_risk STRING,
# MAGIC     status STRING
# MAGIC ) USING DELTA;
# MAGIC
# MAGIC INSERT INTO `amadeus`.`airops`.flights VALUES
# MAGIC ('BA312', 'B', '2026-02-25 10:30:00', 'NONE', 'ON STAND'),
# MAGIC ('BA418', 'B', '2026-02-25 10:30:00', 'NONE', 'ON STAND');
# MAGIC ```
# MAGIC
# MAGIC Tables live in Unity Catalog — permissions, lineage, and audit trails are automatic.

# COMMAND ----------

# MAGIC %md
# MAGIC We have data, but the LLM can't run SQL on its own. We need to build a bridge: wrap database operations as **tools** the agent can call. That's the most important pattern in this workshop.

# COMMAND ----------

# MAGIC %md
# MAGIC # Module 4 — Functions, Procedures & Tools
# MAGIC
# MAGIC **The key idea:** An LLM can't run SQL on its own. We wrap database operations as **tools** the agent can call.

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div class="af-flow">
    <div class="af-fbox fg">
      <svg class="af-ico af-cg"><use href="#af-database"/></svg>
      SQL Procedure
      <small>lives in UC</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fb">
      <svg class="af-ico af-cb"><use href="#af-tool"/></svg>
      Python @tool
      <small>LangChain wrapper</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fa">
      <svg class="af-ico af-cr"><use href="#af-cpu"/></svg>
      Agent
      <small>calls it when needed</small>
    </div>
  </div>
</div>
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Example: The `update_flight_risk` procedure
# MAGIC This procedure lets the agent mark flights as at-risk or normal. It's stored in Unity Catalog.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- View the existing procedure (created during setup)
# MAGIC DESCRIBE PROCEDURE `amadeus`.`airops`.update_flight_risk

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Try calling it — mark BA312 as at-risk
# MAGIC CALL `amadeus`.`airops`.update_flight_risk('BA312', TRUE)

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Check the result
# MAGIC SELECT flight_number, delay_risk FROM `amadeus`.`airops`.flights WHERE flight_number = 'BA312'

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Reset it back
# MAGIC CALL `amadeus`.`airops`.update_flight_risk('BA312', FALSE)

# COMMAND ----------

# MAGIC %md
# MAGIC ### How the procedure is defined
# MAGIC
# MAGIC ```sql
# MAGIC CREATE OR REPLACE PROCEDURE `amadeus`.`airops`.update_flight_risk(
# MAGIC     IN flight_number_param STRING, IN at_risk BOOLEAN
# MAGIC )
# MAGIC LANGUAGE SQL
# MAGIC SQL SECURITY INVOKER
# MAGIC AS
# MAGIC BEGIN
# MAGIC     UPDATE `amadeus`.`airops`.flights
# MAGIC     SET delay_risk = CASE WHEN at_risk THEN 'AT_RISK' ELSE 'NORMAL' END
# MAGIC     WHERE flights.flight_number = flight_number_param;
# MAGIC     SELECT 'UPDATED' AS status;
# MAGIC END;
# MAGIC ```
# MAGIC
# MAGIC Any SQL operation (INSERT, UPDATE, DELETE, complex queries) can be wrapped as a procedure and registered as a tool.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Wrapping as a LangChain tool
# MAGIC
# MAGIC The agent uses `@tool` from LangChain to make procedures callable:
# MAGIC
# MAGIC ```python
# MAGIC from langchain_core.tools import tool
# MAGIC
# MAGIC @tool
# MAGIC def update_flight_risk(flight_number: str, at_risk: bool) -> str:
# MAGIC     """Update a flight's delay_risk status."""
# MAGIC     schema = "`amadeus`.`airops`"
# MAGIC     stmt = f"CALL {schema}.update_flight_risk('{flight_number}', {at_risk})"
# MAGIC     execute_statement(w, warehouse_id, stmt)
# MAGIC     return f"Updated {flight_number}"
# MAGIC ```
# MAGIC
# MAGIC The `@tool` decorator does two things:
# MAGIC 1. **Describes** the function to the LLM (via the docstring + type hints)
# MAGIC 2. **Makes it callable** — the agent sees the tool name, description, and parameters, and decides when to use it

# COMMAND ----------

# Let's create a simple read-only tool and test it
from langchain_core.tools import tool

@tool
def get_flights_by_zone(zone: str) -> str:
    """Get all flights in a given zone. zone: e.g. 'B' or 'C'."""
    result = spark.sql(f"""
        SELECT flight_number, departure_time, delay_risk
        FROM `{CATALOG}`.`{SCHEMA}`.flights
        WHERE zone = '{zone}'
    """)
    return result.toPandas().to_string(index=False)

# Test it directly
print(get_flights_by_zone.invoke("B"))

# COMMAND ----------

# The LLM can now use this tool
from databricks_langchain import ChatDatabricks

llm = ChatDatabricks(endpoint="databricks-claude-sonnet-4-6")
llm_with_tools = llm.bind_tools([get_flights_by_zone])

# Ask the LLM — it decides to call the tool on its own
response = llm_with_tools.invoke("What flights are in zone B?")
print("Tool calls:", response.tool_calls)

# Execute the tool call and feed the result back to the LLM
if response.tool_calls:
    tool_call = response.tool_calls[0]
    tool_result = get_flights_by_zone.invoke(tool_call["args"])
    print(f"\n[+] Tool returned:\n{tool_result}")

    # Send the tool result back so the LLM can formulate a response
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    final = llm_with_tools.invoke([
        HumanMessage(content="What flights are in zone B?"),
        AIMessage(content="", tool_calls=[tool_call]),
        ToolMessage(content=tool_result, tool_call_id=tool_call["id"]),
    ])
    print(f"\n[+] LLM response:\n{final.content}")

# COMMAND ----------

# MAGIC %md
# MAGIC **What just happened:**
# MAGIC
# MAGIC 1. We defined a Python function with `@tool`
# MAGIC 2. We bound it to the LLM with `bind_tools()`
# MAGIC 3. The LLM read the tool's name and docstring, understood what it does, and **decided on its own** to call it with `zone='B'`
# MAGIC 4. We executed the tool and sent the result back -- the LLM formatted a natural language answer
# MAGIC
# MAGIC This is the core of agentic AI — the LLM **reasons** about which tools to use and when.

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div style="display:flex;gap:1.2rem;flex-wrap:wrap;justify-content:center;align-items:stretch">
    <div style="display:flex;flex-direction:column;align-items:center;gap:0.4rem;flex:1;min-width:180px">
      <div style="font-size:0.65rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#6d28d9">Decide</div>
      <div class="af-fbox fp" style="width:100%">
        <svg class="af-ico-sm af-cp"><use href="#af-user"/></svg>
        User asks a question
      </div>
      <div style="color:#bec3c8;font-size:0.75rem">&#9660;</div>
      <div class="af-fbox fp" style="width:100%">
        <svg class="af-ico-sm af-cp"><use href="#af-cpu"/></svg>
        LLM reads available tools
      </div>
      <div style="color:#bec3c8;font-size:0.75rem">&#9660;</div>
      <div class="af-fbox fp" style="width:100%">
        <svg class="af-ico-sm af-cp"><use href="#af-bolt"/></svg>
        Picks tool + arguments
      </div>
    </div>
    <div style="display:flex;align-items:center;color:#bec3c8;font-size:1.2rem;font-weight:700;padding:0 0.3rem">&#8594;</div>
    <div style="display:flex;flex-direction:column;align-items:center;gap:0.4rem;flex:1;min-width:180px">
      <div style="font-size:0.65rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#1a9e67">Execute</div>
      <div class="af-fbox fg" style="width:100%">
        <svg class="af-ico-sm af-cg"><use href="#af-tool"/></svg>
        Tool runs (SQL, API...)
      </div>
      <div style="color:#bec3c8;font-size:0.75rem">&#9660;</div>
      <div class="af-fbox fg" style="width:100%">
        <svg class="af-ico-sm af-cg"><use href="#af-database"/></svg>
        Result returned to LLM
      </div>
      <div style="color:#bec3c8;font-size:0.75rem">&#9660;</div>
      <div class="af-fbox fg" style="width:100%">
        <svg class="af-ico-sm af-cg"><use href="#af-check"/></svg>
        LLM formulates answer
      </div>
    </div>
  </div>
</div>
""")

# COMMAND ----------

# MAGIC %md
# MAGIC You've seen the pattern: procedure -> `@tool` -> `bind_tools` -> the LLM decides. Now build a complete feature yourself, end-to-end.

# COMMAND ----------

# MAGIC %md
# MAGIC # Module 5 — Hands-on Exercise: PA Boarding Announcement
# MAGIC
# MAGIC Now it's your turn. You'll add a complete feature to the agent end-to-end:
# MAGIC
# MAGIC 1. Create a new **passengers** table with seed data
# MAGIC 2. Create a **stored procedure** to update boarding status
# MAGIC 3. Write **3 Python tools** the LLM can call
# MAGIC 4. **Bind tools** to the LLM and test
# MAGIC
# MAGIC **Use case:** A flight is about to close boarding. Some passengers checked in but never showed up at the gate. The agent queries who's missing, generates a standards-compliant French PA announcement, and marks passengers as boarded when they arrive.

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div class="af-flow">
    <div class="af-fbox fg">
      <svg class="af-ico af-cg"><use href="#af-table"/></svg>
      passengers table
      <small>Delta Lake</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fb">
      <svg class="af-ico af-cb"><use href="#af-search"/></svg>
      query_late_passengers
      <small>@tool</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fp">
      <svg class="af-ico af-cp"><use href="#af-megaphone"/></svg>
      generate_pa_announcement
      <small>@tool</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fa">
      <svg class="af-ico af-cr"><use href="#af-message"/></svg>
      PA Broadcast
      <small>French standard</small>
    </div>
  </div>
</div>
""")

# COMMAND ----------

# MAGIC %md
# MAGIC > **Heads up:** This table is shared across all students on the workspace. If you see unexpected data (missing passengers, wrong boarded status), just re-run the cells below -- a colleague is probably working on the same section. Wait a minute and re-run.
# MAGIC
# MAGIC ### Step 1 — Create the `passengers` table

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE amadeus.airops.passengers (
# MAGIC     passenger_id STRING,
# MAGIC     last_name STRING,
# MAGIC     first_name STRING,
# MAGIC     title STRING,
# MAGIC     flight_number STRING,
# MAGIC     zone STRING,
# MAGIC     gate STRING,
# MAGIC     seat STRING,
# MAGIC     checked_in BOOLEAN,
# MAGIC     boarded BOOLEAN
# MAGIC ) USING DELTA
# MAGIC TBLPROPERTIES (delta.enableChangeDataFeed = true);
# MAGIC
# MAGIC INSERT OVERWRITE amadeus.airops.passengers VALUES
# MAGIC   ('PAX001', 'Dumont',    'Claire',   'Mme', 'BA312', 'B', 'B52', '14A', TRUE, TRUE),
# MAGIC   ('PAX002', 'Lefebvre',  'Antoine',  'M.',  'BA312', 'B', 'B52', '14B', TRUE, FALSE),
# MAGIC   ('PAX003', 'Martin',    'Sophie',   'Mme', 'BA312', 'B', 'B52', '22C', TRUE, FALSE),
# MAGIC   ('PAX004', 'Petit',     'Jean',     'M.',  'BA312', 'B', 'B52', '08F', TRUE, TRUE),
# MAGIC   ('PAX005', 'Moreau',    'Isabelle', 'Mme', 'BA418', 'B', 'B54', '03A', TRUE, FALSE),
# MAGIC   ('PAX006', 'Bernard',   'Luc',      'M.',  'BA418', 'B', 'B54', '03B', TRUE, TRUE),
# MAGIC   ('PAX007', 'Dubois',    'Marie',    'Mme', 'BA418', 'B', 'B54', '17D', TRUE, TRUE),
# MAGIC   ('PAX008', 'Lambert',   'Pierre',   'M.',  'AF134', 'C', 'C21', '11A', TRUE, FALSE),
# MAGIC   ('PAX009', 'Garcia',    'Elena',    'Mme', 'AF134', 'C', 'C21', '11B', TRUE, TRUE),
# MAGIC   ('PAX010', 'Roux',      'Thomas',   'M.',  'AF134', 'C', 'C21', '25E', TRUE, FALSE),
# MAGIC   ('PAX011', 'Fontaine',  'Camille',  'Mme', 'AF178', 'C', 'C23', '06A', TRUE, TRUE),
# MAGIC   ('PAX012', 'Chevalier', 'Marc',     'M.',  'AF178', 'C', 'C23', '06B', TRUE, FALSE);

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT * FROM amadeus.airops.passengers ORDER BY flight_number, last_name

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 2 — Create the `mark_passenger_boarded` stored procedure

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE PROCEDURE amadeus.airops.mark_passenger_boarded(
  IN p_passenger_id STRING
)
LANGUAGE SQL
SQL SECURITY INVOKER
AS
BEGIN
  UPDATE amadeus.airops.passengers
  SET boarded = TRUE
  WHERE passenger_id = p_passenger_id;

  SELECT 'UPDATED' AS status;
END;
""")
print("[+] Procedure amadeus.airops.mark_passenger_boarded created")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 3 — Write the tools
# MAGIC
# MAGIC You'll write 3 tools. Each is a Python function decorated with `@tool` so the LLM can call it.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Tool 1: `query_late_passengers`**
# MAGIC
# MAGIC Query the `passengers` table for a given flight: return passengers who checked in but have **not boarded**.
# MAGIC
# MAGIC **Hint:** Use `spark.sql()` to query the table. Filter on `checked_in = TRUE AND boarded = FALSE`.

# COMMAND ----------

from langchain_core.tools import tool

@tool
def query_late_passengers(flight_number: str) -> list[dict]:
    """Query passengers who checked in but have not boarded for a given flight."""
    df = spark.sql(f"""
        SELECT passenger_id, last_name, first_name, title, flight_number, gate, seat
        FROM amadeus.airops.passengers
        WHERE flight_number = '{flight_number}'
          AND checked_in = TRUE
          AND boarded = FALSE
        ORDER BY last_name
    """)
    return [row.asDict() for row in df.collect()]

print("Tool registered:", query_late_passengers.name)

# COMMAND ----------

# MAGIC %md
# MAGIC **Tool 2: `generate_pa_announcement`**
# MAGIC
# MAGIC Generate a standards-compliant French PA boarding announcement for a given flight.
# MAGIC
# MAGIC **Format:**
# MAGIC > *Dernier appel. Mme DUMONT Claire, M. LEFEBVRE Antoine, enregistres sur le vol British Airways BA312 a destination de Londres-Heathrow, sont pries de se presenter immediatement porte B52 pour embarquement immediat. Les portes sont sur le point de fermer.*
# MAGIC
# MAGIC **Mappings:**
# MAGIC
# MAGIC | Prefix | Airline |
# MAGIC |--------|---------|
# MAGIC | BA | British Airways |
# MAGIC | AF | Air France |
# MAGIC
# MAGIC | Flight | Destination |
# MAGIC |--------|-------------|
# MAGIC | BA312 | Londres-Heathrow |
# MAGIC | BA418 | Edimbourg |
# MAGIC | AF134 | Paris-Charles de Gaulle |
# MAGIC | AF178 | Lyon-Saint Exupery |

# COMMAND ----------

AIRLINE_MAP = {"BA": "British Airways", "AF": "Air France"}
DESTINATION_MAP = {
    "BA312": "Londres-Heathrow",
    "BA418": "Edimbourg",
    "AF134": "Paris-Charles de Gaulle",
    "AF178": "Lyon-Saint Exupery",
}

@tool
def generate_pa_announcement(flight_number: str) -> str:
    """Generate a French PA boarding announcement for late passengers on a given flight."""
    passengers = query_late_passengers.invoke({"flight_number": flight_number})
    if not passengers:
        return f"Aucun passager en retard pour le vol {flight_number}."

    title_map = {"Mr": "Monsieur", "Mrs": "Madame", "Ms": "Madame", "Miss": "Madame"}
    names = ", ".join(
        f"{title_map.get(p['title'], p['title'])} {p['last_name'].upper()} {p['first_name']}" for p in passengers
    )
    prefix = flight_number[:2]
    airline = AIRLINE_MAP.get(prefix, prefix)
    destination = DESTINATION_MAP.get(flight_number, "destination inconnue")
    gate = passengers[0]["gate"]

    return (
        f"Dernier appel. {names}, "
        f"enregistr\u00e9s sur le vol {airline} {flight_number} "
        f"\u00e0 destination de {destination}, "
        f"sont pri\u00e9s de se pr\u00e9senter imm\u00e9diatement porte {gate} "
        f"pour embarquement imm\u00e9diat. Les portes sont sur le point de fermer."
    )

print("Tool registered:", generate_pa_announcement.name)

# COMMAND ----------

# MAGIC %md
# MAGIC **Tool 3: `mark_passenger_boarded`**
# MAGIC
# MAGIC Call the stored procedure to mark a passenger as boarded. Return a confirmation message.
# MAGIC
# MAGIC **Hint:** Use `spark.sql("CALL amadeus.airops.mark_passenger_boarded(...)")`

# COMMAND ----------

@tool
def mark_passenger_boarded(passenger_id: str) -> str:
    """Mark a passenger as boarded by calling the stored procedure."""
    spark.sql(f"CALL amadeus.airops.mark_passenger_boarded('{passenger_id}')")
    return f"Passenger {passenger_id} marked as boarded."

print("Tool registered:", mark_passenger_boarded.name)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 4 — Bind tools to the LLM and test
# MAGIC
# MAGIC Now bind all 3 tools to the LLM and let it decide which one to call.

# COMMAND ----------

from databricks_langchain import ChatDatabricks

llm = ChatDatabricks(endpoint="databricks-claude-sonnet-4-6")
llm_with_pa_tools = llm.bind_tools([query_late_passengers, generate_pa_announcement, mark_passenger_boarded])

# Ask the LLM in French — it picks the right tool
response = llm_with_pa_tools.invoke("Quels passagers sont en retard pour le vol BA312 ?")
print("Tool calls:", response.tool_calls)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 5 — Execute the tool call and hear the announcement

# COMMAND ----------

# Execute the tool call the LLM chose
if response.tool_calls:
    tool_call = response.tool_calls[0]
    print(f"LLM chose tool: {tool_call['name']}")
    print(f"With args: {tool_call['args']}\n")

    # Map tool names to functions
    pa_tools = {
        "query_late_passengers": query_late_passengers,
        "generate_pa_announcement": generate_pa_announcement,
        "mark_passenger_boarded": mark_passenger_boarded,
    }
    result = pa_tools[tool_call["name"]].invoke(tool_call["args"])
    print("Result:\n", result)

# COMMAND ----------

# Now ask for the PA announcement directly
response2 = llm_with_pa_tools.invoke("Genere l'annonce PA pour le vol BA312")
if response2.tool_calls:
    tool_call2 = response2.tool_calls[0]
    announcement = pa_tools[tool_call2["name"]].invoke(tool_call2["args"])
    print(announcement)

# COMMAND ----------

# Broadcast the PA announcement over the terminal speakers
from gtts import gTTS
import base64

pa_text = announcement if 'announcement' in dir() else "Dernier appel. Les portes sont sur le point de fermer."

tts = gTTS(text=pa_text, lang='fr')
import hashlib
_user_hash = hashlib.md5(spark.sql("SELECT current_user()").first()[0].encode()).hexdigest()[:6]
_audio_path = f"/tmp/pa_announcement_{_user_hash}.mp3"
tts.save(_audio_path)

with open(_audio_path, "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode()

displayHTML(f"""
<div style="padding:1rem;background:#f5f6f7;border-radius:8px;text-align:center">
  <p style="font-weight:600;margin-bottom:0.3rem">Annonce PA</p>
  <audio controls autoplay><source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3"></audio>
  <p style="font-size:0.85rem;color:#7e8a95;margin-top:0.5rem">{pa_text}</p>
</div>
""")

# COMMAND ----------

# MAGIC %md
# MAGIC **What just happened — you built a complete agent feature:**
# MAGIC
# MAGIC 1. **Data layer** — Created a `passengers` table + stored procedure in Unity Catalog
# MAGIC 2. **Tool layer** — Wrote 3 Python `@tool` functions: query, generate, mutate
# MAGIC 3. **LLM binding** — Used `bind_tools()` so the LLM decides which tool to call
# MAGIC 4. **Execution** — The LLM reasoned about your question (in French!), picked the right tool, and returned a standards-compliant PA announcement
# MAGIC
# MAGIC This is the exact same pattern the full agent uses — just with more tools and a richer prompt.

# COMMAND ----------

# MAGIC %md
# MAGIC You built tools for specific queries you anticipated. But what happens when a user asks something you didn't write a tool for? Instead of writing a tool for every possible question, we can let **Genie** translate natural language into SQL on the fly.

# COMMAND ----------

# MAGIC %md
# MAGIC # Module 6 — Genie
# MAGIC
# MAGIC **What:** Databricks' natural-language-to-SQL engine. Ask questions in plain English, get SQL results.
# MAGIC
# MAGIC ### Why it's powerful
# MAGIC
# MAGIC - No need to write SQL — Genie translates your question into optimized SQL
# MAGIC - It knows your table schemas, joins, and relationships
# MAGIC - Works on any tables attached to a **Genie Space**
# MAGIC
# MAGIC ### Where in UI
# MAGIC
# MAGIC Left sidebar -> **Genie** -> look for `GENIE-AMADEUS-AIROPS`
# MAGIC
# MAGIC Our Genie Space has all 5 tables: `flights`, `checkin_metrics`, `checkin_agents`, `border_officers`, `border_terminals`
# MAGIC
# MAGIC **Do it now:** Open the Genie Space `GENIE-AMADEUS-AIROPS` and try:
# MAGIC - *"How many flights are in zone B?"*
# MAGIC - *"Which agents are currently on break?"*
# MAGIC - *"Show me the average check-in time by zone"*
# MAGIC - *"Which border terminals are out of service?"*

# COMMAND ----------

# MAGIC %md
# MAGIC ### Invoke Genie via Managed MCP
# MAGIC
# MAGIC **MCP (Model Context Protocol)** is an open standard for connecting LLMs to external tools.
# MAGIC Databricks provides **managed MCP servers** for Genie, Vector Search, and Unity Catalog.

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div class="af-flow">
    <div class="af-fbox fp">
      <svg class="af-ico af-cp"><use href="#af-layers"/></svg>
      LangChain Agent
      <small>orchestrator</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fb">
      <svg class="af-ico af-cb"><use href="#af-package"/></svg>
      MCP Client
      <small>protocol bridge</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fa">
      <svg class="af-ico af-cr"><use href="#af-message"/></svg>
      Genie MCP Server
      <small>/api/2.0/mcp/genie/{id}</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fg">
      <svg class="af-ico af-cg"><use href="#af-server"/></svg>
      SQL Warehouse
      <small>executes queries</small>
    </div>
  </div>
</div>
""")

# COMMAND ----------

import os
from databricks.sdk import WorkspaceClient
from databricks_langchain import DatabricksMCPServer, DatabricksMultiServerMCPClient

w = WorkspaceClient()
host = w.config.host.rstrip("/")

# Genie Space ID (set during setup)
genie_space_id = os.environ.get("PROJECT_GENIE_CHECKIN", "").strip()
if not genie_space_id:
    print("[!] PROJECT_GENIE_CHECKIN not set — find your Genie Space ID in the UI")
    print("    Genie → GENIE-AMADEUS-AIROPS → copy the ID from the URL")
else:
    print(f"[+] Genie Space ID: {genie_space_id}")

# COMMAND ----------

# Connect to Genie via MCP and list available tools
if genie_space_id:
    genie_server = DatabricksMCPServer(
        name="genie-checkin",
        url=f"{host}/api/2.0/mcp/genie/{genie_space_id}",
        workspace_client=w,
    )

    async def show_genie_tools():
        client = DatabricksMultiServerMCPClient([genie_server])
        tools = await client.get_tools()
        print(f"[+] Genie MCP provides {len(tools)} tool(s):")
        for t in tools:
            print(f"    - {t.name}: {t.description[:80]}...")
        return tools

    genie_tools = await show_genie_tools()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Adding Genie as a tool in LangChain
# MAGIC
# MAGIC In the agent code (`agent/agent.py`), this is how Genie is wired:
# MAGIC
# MAGIC ```python
# MAGIC from databricks_langchain import DatabricksMCPServer, DatabricksMultiServerMCPClient
# MAGIC
# MAGIC server = DatabricksMCPServer(
# MAGIC     name="genie-checkin",
# MAGIC     url=f"{host}/api/2.0/mcp/genie/{space_id}",
# MAGIC     workspace_client=w,
# MAGIC )
# MAGIC client = DatabricksMultiServerMCPClient([server])
# MAGIC tools = await client.get_tools()  # Added to the agent's tool list
# MAGIC ```
# MAGIC
# MAGIC The agent decides **on its own** when to use Genie vs. a direct SQL tool.
# MAGIC The prompt tells it: *"Prefer SQL tools over Genie — Genie is slower (NLP-to-SQL)."*

# COMMAND ----------

# MAGIC %md
# MAGIC Genie handles structured data in tables. But our agent also needs to answer questions from **unstructured documents** — PDFs, manuals, regulations. That's a different kind of search.

# COMMAND ----------

# MAGIC %md
# MAGIC # Module 7 — Vector Search
# MAGIC
# MAGIC **What:** Semantic search over documents. Converts text into embeddings (vectors) and finds relevant passages by meaning, not keywords.
# MAGIC
# MAGIC ### How it works
# MAGIC
# MAGIC 1. **Upload PDFs** to a Unity Catalog Volume
# MAGIC 2. **Create an index** — Databricks chunks the text, generates embeddings, stores them
# MAGIC 3. **Query** — your question is embedded and matched against stored vectors
# MAGIC
# MAGIC **Our setup:** A Vector Search index over the EU Passenger Rights regulation (EC 261/2004)
# MAGIC
# MAGIC **Where in UI:** Left sidebar -> **Compute** -> **Vector Search endpoints**

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to create a Vector Search index
# MAGIC
# MAGIC ```python
# MAGIC from databricks.sdk import WorkspaceClient
# MAGIC w = WorkspaceClient()
# MAGIC
# MAGIC # 1. Create an endpoint (the compute that serves queries)
# MAGIC w.vector_search_endpoints.create_endpoint(name="my-vs-endpoint")
# MAGIC
# MAGIC # 2. Create an index from a source table (preprocessed from PDFs)
# MAGIC w.vector_search_indexes.create_index(
# MAGIC     name="amadeus.airops.passenger_rights_index",
# MAGIC     endpoint_name="my-vs-endpoint",
# MAGIC     primary_key="chunk_id",
# MAGIC     embedding_source_column={
# MAGIC         "name": "text",
# MAGIC         "model_endpoint_name": "databricks-bge-large-en"
# MAGIC     },
# MAGIC     index_type="DELTA_SYNC",
# MAGIC     source_table_name="amadeus.airops.chunked_docs",
# MAGIC )
# MAGIC ```
# MAGIC
# MAGIC We won't create a new index (it takes time) — we'll use the **existing one** via MCP.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Invoke Vector Search via MCP

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div class="af-flow">
    <div class="af-fbox fa">
      <svg class="af-ico af-cr"><use href="#af-cpu"/></svg>
      Agent
      <small>LangChain</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fb">
      <svg class="af-ico af-cb"><use href="#af-package"/></svg>
      MCP Client
      <small>protocol bridge</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fg">
      <svg class="af-ico af-cg"><use href="#af-search"/></svg>
      VS MCP Server
      <small>/api/2.0/mcp/vector-search/{cat}/{sch}</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox">
      <svg class="af-ico af-cm"><use href="#af-database"/></svg>
      VS Index
      <small>embeddings</small>
    </div>
  </div>
</div>
""")

# COMMAND ----------

# Connect to Vector Search via MCP
vs_index = os.environ.get("PROJECT_VS_INDEX", "").strip()

if vs_index and "." in vs_index:
    parts = vs_index.rsplit(".", 2)
    cat, sch = parts[0], parts[1]

    vs_server = DatabricksMCPServer(
        name="vector-search-docs",
        url=f"{host}/api/2.0/mcp/vector-search/{cat}/{sch}",
        workspace_client=w,
    )

    async def show_vs_tools():
        client = DatabricksMultiServerMCPClient([vs_server])
        tools = await client.get_tools()
        print(f"[+] Vector Search MCP provides {len(tools)} tool(s):")
        for t in tools:
            print(f"    - {t.name}: {t.description[:80]}...")
        return tools

    vs_tools = await show_vs_tools()
else:
    print("[!] PROJECT_VS_INDEX not set — Vector Search MCP not available")
    print("    This is OK — the Knowledge Assistant wraps VS for us (next module)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Actually invoke Vector Search via MCP
# MAGIC Let's use the VS MCP tool to search the EU passenger rights document.

# COMMAND ----------

# Invoke VS tool — semantic search over our PDF documents
if vs_index and "." in vs_index:
    from langchain_core.messages import HumanMessage, ToolMessage

    # Bind VS tools to the LLM
    llm_with_vs = ChatDatabricks(endpoint="databricks-claude-sonnet-4-6").bind_tools(vs_tools)

    # Ask a question — the LLM will call the VS tool
    response = llm_with_vs.invoke("What does EU regulation say about compensation for cancelled flights?")

    if response.tool_calls:
        print("[+] LLM decided to call VS tool:")
        for tc in response.tool_calls:
            print(f"    Tool: {tc['name']}")
            print(f"    Args: {tc['args']}")

        # Execute the tool call and get the result
        tool_by_name = {t.name: t for t in vs_tools}
        for tc in response.tool_calls:
            result = await tool_by_name[tc["name"]].ainvoke(tc["args"])
            print(f"\n[+] VS Search Result (first 600 chars):\n{str(result)[:600]}...")
    else:
        print("[!] LLM did not call a tool — try a different question about passenger rights")
else:
    print("[!] VS not available — skip to Knowledge Assistant module")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Adding VS as a tool in LangChain
# MAGIC
# MAGIC ```python
# MAGIC # Same pattern — just a different MCP URL
# MAGIC vs_server = DatabricksMCPServer(
# MAGIC     name="vector-search-docs",
# MAGIC     url=f"{host}/api/2.0/mcp/vector-search/{catalog}/{schema}",
# MAGIC     workspace_client=w,
# MAGIC )
# MAGIC client = DatabricksMultiServerMCPClient([vs_server])
# MAGIC vs_tools = await client.get_tools()
# MAGIC # Add vs_tools to the agent's tool list alongside Genie and SQL tools
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC Vector Search gives you raw text passages. The Knowledge Assistant goes one step further — it reads those passages and **synthesizes an answer**, like a subject-matter expert who's read the whole document.

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div style="display:flex;gap:1.5rem;justify-content:center;flex-wrap:wrap;align-items:stretch">
    <div style="flex:1;min-width:240px;max-width:340px;display:flex;flex-direction:column;gap:0.5rem">
      <div class="af-fbox fb" style="min-width:0;width:100%">
        <svg class="af-ico af-cb"><use href="#af-search"/></svg>
        Vector Search
        <small>Module 7</small>
      </div>
      <div style="background:#f0f4f8;border-radius:8px;padding:0.8rem;font-size:0.82rem;flex:1">
        <div style="margin-bottom:0.4rem"><strong>You get:</strong> raw text chunks</div>
        <div style="margin-bottom:0.4rem"><strong>You handle:</strong> generation, ranking, formatting</div>
        <div><strong>Best for:</strong> full control over the RAG pipeline</div>
      </div>
    </div>
    <div style="display:flex;align-items:center;font-size:1.2rem;color:#7e8a95;padding:0 0.5rem">vs</div>
    <div style="flex:1;min-width:240px;max-width:340px;display:flex;flex-direction:column;gap:0.5rem">
      <div class="af-fbox fg" style="min-width:0;width:100%">
        <svg class="af-ico af-cg"><use href="#af-book"/></svg>
        Knowledge Assistant
        <small>Module 8</small>
      </div>
      <div style="background:#f0f8f4;border-radius:8px;padding:0.8rem;font-size:0.82rem;flex:1">
        <div style="margin-bottom:0.4rem"><strong>You get:</strong> synthesized answers with citations</div>
        <div style="margin-bottom:0.4rem"><strong>You handle:</strong> nothing &mdash; it&rsquo;s managed</div>
        <div><strong>Best for:</strong> quick, governed RAG out of the box</div>
      </div>
    </div>
  </div>
</div>
""")

# COMMAND ----------

# MAGIC %md
# MAGIC # Module 8 — Knowledge Assistant
# MAGIC
# MAGIC **What:** A managed RAG (Retrieval-Augmented Generation) service. Point it at documents, it handles chunking, embedding, indexing, and retrieval — all in one.
# MAGIC
# MAGIC ### Why use KA over raw Vector Search?
# MAGIC
# MAGIC - **Simpler** — no need to manage indexes, chunking, or embeddings
# MAGIC - **Smarter** — KA adds a generation layer that synthesizes answers from retrieved passages
# MAGIC - **Managed** — Databricks handles the infra, you just upload PDFs
# MAGIC
# MAGIC **Our KA:** `ka-agent-passengers-rights` — source: EU Regulation EC 261/2004 (PDF in UC Volume), deployed as a serving endpoint

# COMMAND ----------

# MAGIC %md
# MAGIC ### How a Knowledge Assistant is created
# MAGIC
# MAGIC ```python
# MAGIC from databricks.sdk import WorkspaceClient
# MAGIC w = WorkspaceClient()
# MAGIC
# MAGIC # 1. Create the KA pointing to a UC Volume with PDFs
# MAGIC ka = w.knowledge_assistants.create_knowledge_assistant(
# MAGIC     display_name="ka-agent-passengers-rights",
# MAGIC     description="EU passenger rights regulation expert",
# MAGIC )
# MAGIC
# MAGIC # 2. Add a knowledge source (the PDFs)
# MAGIC w.knowledge_assistants.create_knowledge_source(
# MAGIC     knowledge_assistant_name=ka.name,
# MAGIC     display_name="EU Passenger Rights",
# MAGIC     source_type="VOLUME",
# MAGIC     source={"volume": f"/Volumes/amadeus/airops/passenger_docs"},
# MAGIC )
# MAGIC
# MAGIC # 3. Wait for it to index — the KA creates a serving endpoint automatically
# MAGIC ```
# MAGIC
# MAGIC We won't create a new KA — we'll use the **existing one** set up by the agent setup notebook.

# COMMAND ----------

# Find the KA endpoint dynamically
ka_endpoint = None
for ka in w.knowledge_assistants.list_knowledge_assistants():
    if ka.endpoint_name:
        ka_endpoint = ka.endpoint_name
        break

if ka_endpoint:
    print(f"[+] KA endpoint: {ka_endpoint}")

    import json
    path = f"/serving-endpoints/{ka_endpoint}/invocations"
    payload = {"input": [{"role": "user", "content": "What compensation is a passenger entitled to for a 4-hour delay on a Paris to New York flight?"}]}
    response = w.api_client.do("POST", path, body=payload)

    try:
        raw = response["output"][0]["content"][0]["text"]
        parsed = json.loads(raw)
        answer = parsed.get("answer", raw)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        answer = str(response)

    print(f"\n[+] KA Response:\n{answer[:500]}")
else:
    print("[!] No KA endpoint found -- KA not available")

# COMMAND ----------

# MAGIC %md
# MAGIC ### KA as a LangChain tool
# MAGIC
# MAGIC In the agent code (`tools/query_passengers_ka.py`), the KA is wrapped as a `@tool`:
# MAGIC
# MAGIC ```python
# MAGIC @tool
# MAGIC def query_passengers_ka(question: str) -> str:
# MAGIC     """Query the Passenger Rights Knowledge Assistant for EU regulation info."""
# MAGIC     response = w.serving_endpoints.query(
# MAGIC         name=ka_endpoint,
# MAGIC         messages=[ChatMessage(role=ChatMessageRole.USER, content=question)],
# MAGIC     )
# MAGIC     return response.choices[0].message.content
# MAGIC ```

# COMMAND ----------

# Let's actually build the tool and have the LLM use it
if ka_endpoint:
    from langchain_core.tools import tool as lc_tool
    from databricks.sdk.service.serving import ChatMessage as CM, ChatMessageRole as CMR

    @lc_tool
    def query_passengers_ka(question: str) -> str:
        """Query the Passenger Rights Knowledge Assistant about EU flight delay/cancellation compensation rules."""
        resp = w.serving_endpoints.query(
            name=ka_endpoint,
            messages=[CM(role=CMR.USER, content=question)],
        )
        return resp.choices[0].message.content

    # Bind the KA tool to the LLM
    llm_with_ka = ChatDatabricks(endpoint="databricks-claude-sonnet-4-6").bind_tools([query_passengers_ka])

    # Ask a question — the LLM decides to call the KA tool
    ka_response = llm_with_ka.invoke("My flight was cancelled and I had to wait 5 hours. What are my rights?")

    if ka_response.tool_calls:
        print("[+] LLM decided to call KA tool:")
        for tc in ka_response.tool_calls:
            print(f"    Tool: {tc['name']}")
            print(f"    Args: {tc['args']}")

        # Execute the tool call
        result = query_passengers_ka.invoke(ka_response.tool_calls[0]["args"])
        print(f"\n[+] KA Answer:\n{result[:600]}...")
    else:
        print("[!] LLM did not call the tool — it may have answered from its own knowledge")
        print(f"    Response: {ka_response.content[:300]}...")
else:
    print("[!] KA not available — PROJECT_KA_PASSENGERS not set")

# COMMAND ----------

# MAGIC %md
# MAGIC **What just happened:** The LLM read the `@tool` docstring, understood the KA handles passenger rights questions, and **decided to delegate** rather than answer from its own knowledge. The KA retrieves from the actual EU regulation PDF — no hallucination.

# COMMAND ----------

# MAGIC %md
# MAGIC We now have every building block: an LLM brain, governed data, SQL tools, Genie for flexible queries, Vector Search for documents, and a Knowledge Assistant for expert answers. Let's see how they all come together in the deployed app.

# COMMAND ----------

# MAGIC %md
# MAGIC # Module 9 — The Agent App
# MAGIC
# MAGIC Now we see how all the building blocks combine into a **deployed application**.

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div class="af-flow">
    <div class="af-flow-col">
      <div class="af-fbox">
        <svg class="af-ico af-cm"><use href="#af-user"/></svg>
        User
        <small>or application</small>
      </div>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-flow-col">
      <div class="af-fbox">
        <svg class="af-ico af-cm"><use href="#af-monitor"/></svg>
        Databricks Apps
        <small>SSO &middot; zero ops</small>
      </div>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-flow-col">
      <div class="af-fbox fa">
        <svg class="af-ico af-cr"><use href="#af-cpu"/></svg>
        Agent
        <small>FM API &middot; LangGraph</small>
      </div>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-flow-col" style="gap:0.4rem">
      <div class="af-fbox fa" style="min-width:110px">
        <svg class="af-ico-sm af-cr"><use href="#af-message"/></svg>
        Genie
        <small>NL &rarr; SQL</small>
      </div>
      <div class="af-or">or</div>
      <div class="af-fbox fa" style="min-width:110px">
        <svg class="af-ico-sm af-cr"><use href="#af-book"/></svg>
        Knowledge Assistant
        <small>RAG &middot; governed</small>
      </div>
      <div class="af-or">or</div>
      <div class="af-fbox fa" style="min-width:110px">
        <svg class="af-ico-sm af-cr"><use href="#af-tool"/></svg>
        SQL / Procedure
        <small>precise actions</small>
      </div>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-flow-col">
      <div class="af-fbox fg">
        <svg class="af-ico af-cg"><use href="#af-database"/></svg>
        Unity Catalog
        <small>governed &middot; live</small>
      </div>
    </div>
  </div>
</div>
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ### App Folder Structure
# MAGIC
# MAGIC ```
# MAGIC agent-forge/
# MAGIC ├── agent/                    <- Python agent (the brain)
# MAGIC │   ├── agent.py              <- LangChain agent setup, tool registration
# MAGIC │   └── start_server.py       <- FastAPI server for agent + table endpoints
# MAGIC │
# MAGIC ├── tools/                    <- Agent tools (each is a @tool function)
# MAGIC │   ├── query_flights_at_risk.py
# MAGIC │   ├── update_flight_risk.py
# MAGIC │   ├── query_checkin_performance_metrics.py
# MAGIC │   ├── update_checkin_agent.py
# MAGIC │   ├── query_passengers_ka.py
# MAGIC │   └── ... (20+ tools)
# MAGIC │
# MAGIC ├── prompt/                   <- System prompt (agent instructions)
# MAGIC │   ├── main.prompt           <- Core behavior rules (~250 lines)
# MAGIC │   └── knowledge.base        <- Operational FAQ injected into prompt
# MAGIC │
# MAGIC ├── data/                     <- SQL & data
# MAGIC │   ├── init/                 <- Table creation scripts
# MAGIC │   ├── func/                 <- Query templates
# MAGIC │   └── proc/                 <- Stored procedures
# MAGIC │
# MAGIC ├── app/                      <- Frontend + Express server
# MAGIC │   ├── client/               <- React + Vite + Tailwind
# MAGIC │   ├── server/               <- Express API proxy
# MAGIC │   └── app.yaml              <- Databricks App config
# MAGIC │
# MAGIC └── config/                   <- KA, VS, Genie configs
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### The System Prompt — How the Agent Behaves
# MAGIC
# MAGIC The file `prompt/main.prompt` is the **instruction manual** for the agent. It defines:
# MAGIC
# MAGIC - **Persona** — "You are Garv, an AI Ops Advisor for airport check-in operations"
# MAGIC - **Scope** — which tables and metrics to use (and which to ignore)
# MAGIC - **Response style** — concise, bullet points, bold values
# MAGIC - **Flow logic** — step-by-step decision trees:
# MAGIC   - If `pct_change >= 20%` -> emit performance alert -> ask about at-risk flights
# MAGIC   - If confirmed -> query flights -> flag at-risk -> offer root cause analysis
# MAGIC   - If confirmed -> analyze staffing -> recommend redeployment -> execute
# MAGIC - **Tool routing** — which tool to use for which question
# MAGIC - **Block formatting** — structured output blocks the UI renders as cards
# MAGIC
# MAGIC **To change agent behavior:** Edit `prompt/main.prompt`. No code changes needed.

# COMMAND ----------

# Let's look at the actual prompt
prompt_path = "/Workspace/Shared/agent-app/prompt/main.prompt"
try:
    with open(prompt_path) as f:
        lines = f.read().split("\n")
    print(f"[+] prompt/main.prompt ({len(lines)} lines)")
    print("=" * 60)
    print("\n".join(lines[:60]))
    print(f"\n... ({len(lines) - 60} more lines)")
except FileNotFoundError:
    print("[!] Prompt file not found at expected workspace path")
    print("    The prompt is deployed with the app code")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Deployment — Databricks Apps
# MAGIC
# MAGIC - **Where in UI:** Left sidebar -> **Apps** -> look for `agent-app`
# MAGIC - **URL:** Each app gets a unique URL like `https://<workspace>.databricks.com/apps/agent-app`
# MAGIC - **Config:** `app.yaml` defines runtime (Node.js 20), env vars, and port
# MAGIC
# MAGIC ### To change code and redeploy
# MAGIC
# MAGIC 1. Edit files in the workspace (Repos or Workspace file browser)
# MAGIC 2. Or push changes via the setup notebook / bundle
# MAGIC 3. Restart the app: Left sidebar -> **Apps** -> `agent-app` -> **Restart**
# MAGIC
# MAGIC ### Key env vars in `app.yaml`
# MAGIC
# MAGIC | Variable | Purpose |
# MAGIC |----------|---------|
# MAGIC | `AGENT_MODEL_ENDPOINT` | Which LLM to use |
# MAGIC | `PROJECT_UNITY_CATALOG_SCHEMA` | Which tables to query (`amadeus.airops`) |
# MAGIC | `PROJECT_GENIE_CHECKIN` | Genie Space ID |
# MAGIC | `PROJECT_KA_PASSENGERS` | Knowledge Assistant endpoint |
# MAGIC | `DATABRICKS_WAREHOUSE_ID` | SQL Warehouse for queries |

# COMMAND ----------

# MAGIC %md
# MAGIC ### How to change the agent
# MAGIC
# MAGIC | What to change | Where |
# MAGIC |---------------|-------|
# MAGIC | Agent personality, flow logic, response format | `prompt/main.prompt` |
# MAGIC | Operational knowledge / FAQ | `prompt/knowledge.base` |
# MAGIC | Add a new tool | Create `tools/my_tool.py` with `@tool`, import in `agent/agent.py` |
# MAGIC | Add a new table | SQL `CREATE TABLE` + add to Genie Space |
# MAGIC | Change which LLM is used | Update `AGENT_MODEL_ENDPOINT` in `app.yaml` |
# MAGIC | Change the UI / add cards | Edit React components in `app/client/src/components/` |
# MAGIC
# MAGIC ### Creating apps
# MAGIC
# MAGIC - You can create a new Databricks App directly from the UI: **Apps** > **Create App** -- pick a template, and the code is stored right in the workspace
# MAGIC - This is great for quick prototyping and getting started fast
# MAGIC - For a better dev experience, connect from your IDE (VS Code, PyCharm), edit locally, and deploy via CLI or the Databricks SDK -- you get version control, linting, and a proper development workflow
# MAGIC - Both approaches work -- start in the UI to explore, move to an IDE when the project gets serious

# COMMAND ----------

# MAGIC %md
# MAGIC You built tools, wired them to an LLM, and deployed an app. But how do you know it's actually good? Evaluation closes the loop -- it turns *"I think it works"* into *"I can prove it works."*

# COMMAND ----------

# MAGIC %md
# MAGIC # Module 10 — Evaluation
# MAGIC
# MAGIC **What:** Use MLflow GenAI to evaluate agent response quality with automated scorers. Define what "good" looks like, measure it, improve, re-measure.

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div class="af-flow">
    <div class="af-fbox fb">
      <svg class="af-ico af-cb"><use href="#af-table"/></svg>
      Eval Dataset
      <small>questions + expectations</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fp">
      <svg class="af-ico af-cp"><use href="#af-cpu"/></svg>
      Agent
      <small>prompt v1</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fa">
      <svg class="af-ico af-cr"><use href="#af-check"/></svg>
      Scorers
      <small>automated judges</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fg">
      <svg class="af-ico af-cg"><use href="#af-bolt"/></svg>
      Metrics
      <small>pass / fail per guideline</small>
    </div>
  </div>
  <div style="display:flex;justify-content:center;margin-top:0.8rem">
    <div style="display:flex;align-items:center;gap:0.5rem;color:#7e8a95;font-size:0.82rem">
      <svg style="width:16px;height:16px;color:#b87200;transform:rotate(180deg)"><use href="#af-arrow"/></svg>
      <span>Improve prompt &rarr; re-run &rarr; compare</span>
      <svg style="width:16px;height:16px;color:#b87200"><use href="#af-arrow"/></svg>
    </div>
  </div>
</div>
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ### What MLflow GenAI evaluation gives you
# MAGIC
# MAGIC - **Datasets** — structured test cases (question + context the agent should work with)
# MAGIC - **Scorers** — automated LLM judges that grade each response against criteria
# MAGIC - **Tracking** — results logged to MLflow experiments, comparable across runs
# MAGIC
# MAGIC We'll use the **Guidelines** scorer: you define rules the agent should follow, and the scorer checks each response against them.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 1 — Load the current system prompt

# COMMAND ----------

# Load the system prompt the agent uses in production
prompt_path = "/Workspace/Shared/agent-app/prompt/main.prompt"
try:
    with open(prompt_path) as f:
        system_prompt_v1 = f.read()
    print(f"[+] Loaded system prompt ({len(system_prompt_v1.splitlines())} lines)")
except FileNotFoundError:
    # Fallback: minimal prompt for evaluation
    system_prompt_v1 = (
        "You are Garv, an AI Ops Advisor for airport check-in operations. "
        "You monitor live event logs and proactively alert the operator when check-in performance issues are detected. "
        "Be concise and factual. Use bullet points, bold key values."
    )
    print("[!] Prompt file not found — using minimal fallback for eval")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 2 — Build the eval dataset
# MAGIC
# MAGIC Each row is a realistic scenario the agent should handle. We include **data context** in the question (as if a tool already returned results) so we're testing how the LLM **formats and reasons**, not whether it can call tools.

# COMMAND ----------

eval_dataset = [
    {
        "inputs": {
            "question": (
                "Zone B check-in performance has degraded. "
                "Data from query: avg_checkin_time=6.2 min, baseline=3.8 min, "
                "pct_change=63%, timestamp=2026-02-25T10:00:00. "
                "What is the situation?"
            ),
        },
    },
    {
        "inputs": {
            "question": (
                "We need a root cause analysis for Zone C. "
                "Check-in staffing: 2 agents active (M. Lee at C01, J. Park at C03), 1 on break (R. Singh). "
                "Border control: 3 officers active, 1 on break (A. Chen, O03). "
                "e-Gates: eGate-C1 operational, eGate-C2 operational, eGate-C3 OUT OF SERVICE. "
                "What is causing the slowdown?"
            ),
        },
    },
    {
        "inputs": {
            "question": "What is the current weather at Heathrow airport?",
        },
    },
    {
        "inputs": {
            "question": (
                "Give me a full status report on check-in performance across all zones. "
                "Data: Zone A: avg=3.5min, baseline=3.4min, pct_change=3%. "
                "Zone B: avg=6.2min, baseline=3.8min, pct_change=63%. "
                "Zone C: avg=4.1min, baseline=3.9min, pct_change=5%. "
                "Zone D: avg=3.3min, baseline=3.5min, pct_change=-6%."
            ),
        },
    },
]

print(f"[+] Eval dataset: {len(eval_dataset)} test cases")
for i, row in enumerate(eval_dataset):
    print(f"    {i+1}. {row['inputs']['question'][:80]}...")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 3 — Define guidelines and run baseline evaluation
# MAGIC
# MAGIC These guidelines define what a **good response** looks like. Some of them are NOT in the current prompt -- that's intentional. We want to see what fails.

# COMMAND ----------

import mlflow
from mlflow.genai.scorers import Guidelines

# Guidelines we'll evaluate against
# The current prompt covers some of these, but NOT all of them
eval_guidelines = [
    "When reporting performance metrics, always include the delta from baseline (e.g., '+2.4 min above baseline')",
    "When analyzing root causes, must cross-reference BOTH check-in staffing AND border control data before concluding",
    "For questions outside check-in operations scope (weather, sports, general knowledge), explicitly decline and state what you CAN help with",
    "When reporting on multiple zones, include a status line for EVERY zone mentioned in the data, not just the anomalous ones",
]

print("[+] Evaluation guidelines:")
for i, g in enumerate(eval_guidelines):
    print(f"    {i+1}. {g[:90]}...")

# COMMAND ----------

# Predict function: calls the LLM with the system prompt
# No tools needed — we're testing prompt quality, not tool execution
def make_predict_fn(system_prompt):
    def predict(question):
        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ])
        return response.content
    return predict

predict_v1 = make_predict_fn(system_prompt_v1)

# Quick sanity check — does the predict function work?
test_response = predict_v1("What is Zone B check-in performance? Data: avg=6.2min, baseline=3.8min, pct_change=63%")
print(f"[+] Predict function works. Sample response ({len(test_response)} chars):")
print(test_response[:300])

# COMMAND ----------

# MAGIC %md
# MAGIC ### Run evaluation (v1 — baseline)

# COMMAND ----------

mlflow.set_experiment(f"/Users/{spark.sql('SELECT current_user()').first()[0]}/agent-workshop-eval")

# COMMAND ----------

results_v1 = mlflow.genai.evaluate(
    data=eval_dataset,
    predict_fn=predict_v1,
    scorers=[Guidelines(guidelines=eval_guidelines)],
)
print("[+] Baseline evaluation complete")
df_v1 = results_v1.tables["eval_results"]
for i, row in df_v1.iterrows():
    q = eval_dataset[i]["inputs"]["question"][:70]
    print(f"  Q{i+1}: {row['guidelines/value']} — {q}...")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Analyze the results
# MAGIC
# MAGIC Look at the scores. You'll likely see:
# MAGIC - **Guideline 1** (delta from baseline): The prompt says "bold key values" but doesn't mandate showing the delta. Hit or miss.
# MAGIC - **Guideline 2** (cross-reference staffing + border): The prompt routes these as **separate flows** — root cause analysis does cross-reference, but only when triggered in sequence. Direct questions may not.
# MAGIC - **Guideline 3** (decline out-of-scope): The prompt defines scope but doesn't tell the agent how to refuse.
# MAGIC - **Guideline 4** (all zones): The prompt focuses on anomaly detection — it may skip normal zones.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 4 — Improve the prompt
# MAGIC
# MAGIC We add explicit instructions for the guidelines that failed. This is the core prompt engineering loop:
# MAGIC **measure -> identify gaps -> patch the prompt -> re-measure.**
# MAGIC
# MAGIC We're editing the prompt **in this notebook only** — no redeployment needed. To ship these changes to the live app, you would:
# MAGIC 1. Edit `prompt/main.prompt` in the workspace file browser
# MAGIC 2. Restart the app: sidebar -> **Apps** -> `agent-app` -> **Restart**

# COMMAND ----------

# Add targeted instructions to the prompt
prompt_patch = """

RESPONSE QUALITY RULES (added via evaluation feedback):
- When reporting performance metrics, always include the delta from baseline (e.g., "+2.4 min above baseline of 3.8 min").
- When analyzing root causes, you MUST cross-reference both check-in staffing AND border control data (officers and e-Gates) in a single response. Do not treat them as separate flows.
- If asked about something outside check-in operations (weather, general knowledge, etc.), explicitly decline: "That falls outside check-in operations. I can help with check-in performance, staffing, flight risk, and passenger rights."
- When asked about all zones or multiple zones, include a status line for every zone in the data — not just the ones with anomalies.
"""

system_prompt_v2 = system_prompt_v1 + prompt_patch

print("[+] Prompt v2 created")
print(f"    v1: {len(system_prompt_v1.splitlines())} lines")
print(f"    v2: {len(system_prompt_v2.splitlines())} lines (+{len(prompt_patch.splitlines())} lines added)")
print(f"\n[+] Added rules:")
for line in prompt_patch.strip().splitlines():
    if line.startswith("- "):
        print(f"    {line}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Run evaluation (v2 — after prompt improvement)

# COMMAND ----------

predict_v2 = make_predict_fn(system_prompt_v2)

results_v2 = mlflow.genai.evaluate(
    data=eval_dataset,
    predict_fn=predict_v2,
    scorers=[Guidelines(guidelines=eval_guidelines)],
)
print("[+] v2 evaluation complete")
df_v2 = results_v2.tables["eval_results"]
for i, row in df_v2.iterrows():
    q = eval_dataset[i]["inputs"]["question"][:70]
    print(f"  Q{i+1}: {row['guidelines/value']} — {q}...")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Compare v1 vs v2

# COMMAND ----------

import pandas as pd

v1_values = results_v1.tables["eval_results"]["guidelines/value"].tolist()
v2_values = results_v2.tables["eval_results"]["guidelines/value"].tolist()

comparison = pd.DataFrame({
    "Test Case": [f"Q{i+1}" for i in range(len(eval_dataset))],
    "Question": [r["inputs"]["question"][:60] + "..." for r in eval_dataset],
    "v1 (baseline)": v1_values,
    "v2 (improved)": v2_values,
})
print(comparison.to_string(index=False))

v1_pass = sum(1 for s in v1_values if s == "yes")
v2_pass = sum(1 for s in v2_values if s == "yes")
print(f"\n[+] Score: v1 = {v1_pass}/{len(v1_values)} passed | v2 = {v2_pass}/{len(v2_values)} passed")
if v2_pass > v1_pass:
    print(f"[+] Improvement: +{v2_pass - v1_pass} test cases now passing")

# COMMAND ----------

# MAGIC %md
# MAGIC **What just happened:** Same questions, same scorers, different prompt. The guidelines you added directly improved the scores. This is the evaluation-driven development loop:
# MAGIC
# MAGIC 1. **Define quality** — write guidelines that describe what good looks like
# MAGIC 2. **Measure** — run `mlflow.genai.evaluate()` against your dataset
# MAGIC 3. **Improve** — patch the prompt (or tools, or model) based on what failed
# MAGIC 4. **Re-measure** — confirm the fix worked without breaking other cases
# MAGIC
# MAGIC In production, you'd run this in CI/CD on every prompt change. MLflow tracks every run so you can compare across versions.
# MAGIC
# MAGIC **To ship prompt v2 to the live app:**
# MAGIC 1. Open the workspace file browser: navigate to your repo -> `prompt/main.prompt`
# MAGIC 2. Append the `RESPONSE QUALITY RULES` block from the cell above
# MAGIC 3. Sidebar -> **Apps** -> `agent-app` -> **Restart**

# COMMAND ----------

# MAGIC %md
# MAGIC That's the full picture. Let's step back and see everything we covered.

# COMMAND ----------

# MAGIC %md
# MAGIC # Recap
# MAGIC
# MAGIC In this workshop, you:
# MAGIC
# MAGIC - Invoked a **Foundation Model** through the Playground and LangChain
# MAGIC - Explored **Unity Catalog** as the governance layer for all assets
# MAGIC - Queried **5 live operational tables** powering the agent
# MAGIC - Created a **stored procedure**, wrapped it as a **@tool**, and let the LLM decide when to call it
# MAGIC - Built a complete **PA announcement feature** end-to-end (table, procedure, 3 tools, LLM binding)
# MAGIC - Connected **Genie** via MCP for natural-language SQL on any question
# MAGIC - Used **Vector Search** via MCP for semantic document retrieval
# MAGIC - Called a **Knowledge Assistant** that synthesizes answers from EU regulations
# MAGIC - Explored the full **deployed agent app** -- architecture, prompt, and config
# MAGIC - Ran **MLflow GenAI evaluation**, improved the prompt, and measured the difference

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0.6rem;max-width:720px;margin:0 auto">
    <div class="af-fbox fp" style="min-width:0">
      <svg class="af-ico-sm af-cp"><use href="#af-cpu"/></svg>
      <small>Module 1</small>
      Foundation Model
    </div>
    <div class="af-fbox fb" style="min-width:0">
      <svg class="af-ico-sm af-cb"><use href="#af-layers"/></svg>
      <small>Module 2</small>
      Unity Catalog
    </div>
    <div class="af-fbox fg" style="min-width:0">
      <svg class="af-ico-sm af-cg"><use href="#af-table"/></svg>
      <small>Module 3</small>
      Tables
    </div>
    <div class="af-fbox fa" style="min-width:0">
      <svg class="af-ico-sm af-cr"><use href="#af-tool"/></svg>
      <small>Module 4</small>
      Functions &amp; Tools
    </div>
    <div class="af-fbox fam" style="min-width:0">
      <svg class="af-ico-sm" style="fill:#b87200"><use href="#af-megaphone"/></svg>
      <small>Module 5</small>
      PA Exercise
    </div>
    <div class="af-fbox fa" style="min-width:0">
      <svg class="af-ico-sm af-cr"><use href="#af-message"/></svg>
      <small>Module 6</small>
      Genie
    </div>
    <div class="af-fbox fb" style="min-width:0">
      <svg class="af-ico-sm af-cb"><use href="#af-search"/></svg>
      <small>Module 7</small>
      Vector Search
    </div>
    <div class="af-fbox fg" style="min-width:0">
      <svg class="af-ico-sm af-cg"><use href="#af-book"/></svg>
      <small>Module 8</small>
      Knowledge Assistant
    </div>
    <div class="af-fbox fp" style="min-width:0">
      <svg class="af-ico-sm af-cp"><use href="#af-cloud"/></svg>
      <small>Module 9</small>
      Agent App
    </div>
    <div class="af-fbox fam" style="min-width:0;grid-column:2">
      <svg class="af-ico-sm" style="fill:#b87200"><use href="#af-check"/></svg>
      <small>Module 10</small>
      Evaluation
    </div>
  </div>
</div>
""")

# COMMAND ----------

# MAGIC %md
# MAGIC | Building Block | Databricks Service | Role in the Agent |
# MAGIC |---------------|-------------------|-------------------|
# MAGIC | **Foundation Model** | AI Gateway | The LLM brain — reasons and decides |
# MAGIC | **Unity Catalog** | UC | Governs all assets (tables, volumes, functions) |
# MAGIC | **Tables** | Delta Lake | Live operational data the agent monitors |
# MAGIC | **Functions** | UC Procedures | Actions the agent can take (update, insert) |
# MAGIC | **Genie** | Genie Spaces | Natural-language SQL for flexible queries |
# MAGIC | **Vector Search** | VS Indexes | Semantic search over documents |
# MAGIC | **Knowledge Assistant** | KA Endpoints | Managed RAG — answers from your docs |
# MAGIC | **Prompt** | Text file | Instructions that control agent behavior |
# MAGIC | **LangChain** | Python | Orchestrator that connects LLM + tools |
# MAGIC | **Databricks Apps** | Apps | Hosted deployment with UI |
# MAGIC | **Evaluation** | MLflow GenAI | Automated scoring, prompt iteration |

# COMMAND ----------

# MAGIC %md
# MAGIC ### The agentic pattern

# COMMAND ----------

displayHTML(AF_STYLES + """
<div class="af">
  <div class="af-flow">
    <div class="af-fbox fa">
      <svg class="af-ico af-cr"><use href="#af-user"/></svg>
      User asks
      <small>natural language</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fp">
      <svg class="af-ico af-cp"><use href="#af-cpu"/></svg>
      LLM reasons
      <small>reads prompt</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fb">
      <svg class="af-ico af-cb"><use href="#af-tool"/></svg>
      Picks tool(s)
      <small>SQL / Genie / KA</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fg">
      <svg class="af-ico af-cg"><use href="#af-database"/></svg>
      Executes
      <small>reads/writes data</small>
    </div>
    <div class="af-arrow"><svg class="af-ico-sm af-cm"><use href="#af-arrow"/></svg></div>
    <div class="af-fbox fa">
      <svg class="af-ico af-cr"><use href="#af-check"/></svg>
      Responds
      <small>structured cards</small>
    </div>
  </div>
</div>
""")

# COMMAND ----------

# MAGIC %md
# MAGIC You now have the full toolkit to build, deploy, and evaluate agentic applications on Databricks. Every component you touched today -- models, tools, data, prompts, evaluation -- is production-ready and governed by Unity Catalog. The patterns you learned scale from a workshop notebook to a real operations center. Go build something.
