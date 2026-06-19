# BrickForge Telemetry

> Status: PLANNED
> Created: 2026-06-15

## Goal

Track BrickForge adoption and link usage to real customer outcomes. Prove to management: "X users deployed Y agents for Z customers."

## Audience

- Internal SAs/AEs (@databricks.com)
- External users (customers, community devs)
- Both from day one, single flow. Nobody types an email. Ever.

## Architecture

Two tracks, one flow:

- **Databricks users** (workspace connected): token relay + SCIM → identity resolved server-side, zero PII in transit
- **External users** (no workspace): RSA handshake → anonymous client_id, no identity

### Registration (first run, silent, background)

```
BrickForge CLI (any user)
    │
    │  1. Generate client_secret (random bytes)
    │  2. Encrypt with proxy's RSA public key (embedded in package)
    │  3. POST /api/register {encrypted_client_secret}
    │  4. Proxy decrypts, stores client_id <-> client_secret
    │  5. Returns client_id
    │  6. CLI stores client_id + client_secret in ~/.brickforge/telemetry_id
```

User sees nothing. No prompt, no email, no opt-in screen.

### Event flow - Databricks users (SCIM identity resolution)

```
┌─────────────────────┐          ┌─────────────────────┐          ┌─────────────────────┐
│   BrickForge CLI    │          │  Telemetry Proxy    │          │   Workspace-A       │
│   (SA's laptop)     │          │  (central DBX App)  │          │   (SA's workspace)  │
└─────────┬───────────┘          └─────────┬───────────┘          └─────────┬───────────┘
          │                                │                                │
          │  Event fires (e.g. deploy)     │                                │
          │  Email never leaves client     │                                │
          │                                │                                │
          │  POST /api/events (HTTPS)      │                                │
          │  Body: {event, ws_host, app}   │                                │
          │  Header: Bearer <token>        │                                │
          │  Header: X-Client-ID           │                                │
          │  Header: X-Signature (HMAC)    │                                │
          │ ─────────────────────────────► │                                │
          │                                │                                │
          │                                │  Verify HMAC signature         │
          │                                │  Rate limit check              │
          │                                │                                │
          │                                │  GET /api/2.0/.../scim/v2/Me  │
          │                                │  Bearer <same token>          │
          │                                │ ─────────────────────────────► │
          │                                │                                │
          │                                │  {"userName": "mehdi@dbx.com"} │
          │                                │ ◄───────────────────────────── │
          │                                │                                │
          │                                │  Identity resolved.            │
          │                                │  Token discarded immediately.  │
          │                                │                                │
          │                                │  INSERT INTO telemetry         │
          │                                │  (email, event, app, ...)      │
          │                                │ ──────► [Delta Table]          │
          │                                │                                │
          │  200 OK                        │                                │
          │ ◄───────────────────────────── │                                │
          │                                │                                │
```

### Event flow - External users (anonymous)

```
┌─────────────────────┐          ┌─────────────────────┐
│   BrickForge CLI    │          │  Telemetry Proxy    │
│   (external user)   │          │  (central DBX App)  │
└─────────┬───────────┘          └─────────┬───────────┘
          │                                │
          │  POST /api/events (HTTPS)      │
          │  Body: {event, version, ...}   │
          │  Header: X-Client-ID           │
          │  Header: X-Signature (HMAC)    │
          │  (no Bearer token)             │
          │ ─────────────────────────────► │
          │                                │
          │                                │  Verify HMAC signature
          │                                │  Rate limit check
          │                                │  No token → skip SCIM
          │                                │  email = NULL (anonymous)
          │                                │
          │                                │  INSERT INTO telemetry
          │                                │ ──────► [Delta Table]
          │                                │
          │  200 OK                        │
          │ ◄───────────────────────────── │
          │                                │
```

## Security model

**Threat**: casual abuse (spam, junk data). Not state actors.

**Analogy**: lock the door, don't build a vault. If the door is open any fool will peek. If slightly locked, only motivated thieves will try - and this is not a luxury property.

**Three layers, each doing a different job:**

| Layer | What | Job | Implementation |
|---|---|---|---|
| **HTTPS (TLS)** | Transport encryption | **Confidentiality** - no one on the network can read payloads | Free. Python uses HTTPS automatically when URL starts with `https://`. DBX Apps enforce TLS. Zero code. |
| **RSA handshake** | Registration authentication | **Authenticity** - proves client is a real BrickForge install. Blocks random curl spam. | Public key in pip package. Private key in Databricks Secrets. |
| **HMAC-SHA256** | Event signing | **Integrity** - proves payload came from registered client, wasn't tampered with | Shared `client_secret` from RSA registration. CLI signs, proxy verifies. |

**What this stops**: casual spam, random curl abuse, payload tampering, network sniffing.

**What this doesn't stop**: determined reverse engineer who reads source, extracts public key, mimics full flow. Accepted risk - this is a side project, not a startup.

**Additional defenses:**
- Rate limit: 100 events/day per client_id
- Rate limit: per IP
- Payload schema validation
- Dashboard-side anomaly flags

## Identity resolution

**Decision**: SCIM token relay for Databricks users. Anonymous for external users.

The proxy never asks the user who they are. It asks their workspace.

- CLI sends the user's OAuth token (already short-lived) + workspace host
- Proxy forwards token to `https://<workspace>/api/2.0/preview/scim/v2/Me`
- Workspace responds with email and display name
- Proxy writes resolved identity to Delta table
- Token discarded immediately - never stored, logged, or persisted

If no Bearer token is present (external user), SCIM is skipped. Row inserted with `email = NULL`.

**Why not self-reported email?** Spoofable. The whole point is identity resolved from a trusted source.

**Why not email hashing?** SHA-256 of a known email is the email - dictionary attack on a finite employee list takes seconds.

## Data model

```sql
CREATE TABLE catalog.schema.brickforge_telemetry (
    ts              TIMESTAMP,
    event           STRING,       -- install | setup_start | project_create | deploy | export
    client_id       STRING,       -- from RSA registration
    user_email      STRING,       -- resolved via SCIM (DBX users) or NULL (external)
    user_name       STRING,       -- resolved via SCIM or NULL
    brickforge_ver  STRING,       -- __version__
    customer_name   STRING,       -- user-entered on project creation
    sfdc_account_id STRING,       -- user-entered (Salesforce Account ID)
    uc_schema       STRING,       -- catalog.schema from config
    workspace_host  STRING,       -- workspace URL
    app_name        STRING,       -- deployed app name
    cloud           STRING        -- aws | azure | gcp
)
```

## Client registry (proxy-side)

```sql
CREATE TABLE catalog.schema.brickforge_telemetry_clients (
    client_id       STRING,
    client_secret   STRING,       -- stored hashed (SHA-256)
    registered_at   TIMESTAMP,
    last_seen       TIMESTAMP,
    blocked         BOOLEAN DEFAULT false
)
```

## CLI integration

### New fields in config.json

```json
{
  "tracking": {
    "customer_name": "",
    "sfdc_account_id": ""
  }
}
```

Prompted on first project creation in Setup App UI. Optional fields.

### Telemetry client

- File: `brickforge/lib/telemetry.py`
- RSA public key: embedded as `brickforge/lib/telemetry_pub.pem`
- Client credentials: `~/.brickforge/telemetry_id` (JSON: client_id + client_secret) - plain file, not keyring (low-value target)
- All calls: fire-and-forget daemon thread, never block user, silent on failure

### Events to track

| Event | When | Extra fields |
|---|---|---|
| `install` | First run after pip install | version |
| `setup_start` | Setup App opened | workspace_host |
| `project_create` | New project created | customer_name, sfdc_account_id |
| `deploy` | Agent deployed to DBX Apps | app_name, uc_schema, cloud |
| `export` | .forge bundle exported | -|
| `github_push` | Pushed to GitHub | -|

### Auto-detected fields (no user input needed)

- `user_email`: resolved server-side by proxy via SCIM (not sent by CLI)
- `workspace_host`: from config
- `uc_schema`: from config
- `cloud`: from workspace URL detection
- `brickforge_ver`: from `__version__`

## Proxy App

- Databricks App in central workspace
- FastAPI, three endpoints: `/api/register`, `/api/events`, `/api/health`
- App SP has INSERT-only on telemetry tables
- RSA private key in Databricks Secrets scope
- SCIM calls use the user's forwarded token (not the app SP)
- No user-facing UI needed

## Lakeview Dashboard

Panels:
- **Active users** (weekly/monthly unique emails from SCIM-resolved events)
- **Deploys over time** (event=deploy, by week)
- **Top customers** (by deploy count)
- **SA leaderboard** (by email, @databricks.com only)
- **Version adoption** (pie chart by brickforge_ver)
- **SFDC linkage** (deploys grouped by sfdc_account_id, joinable with Logfood)
- **Anonymous vs identified** (external user adoption trend)

## Implementation order

1. Create Delta tables in central workspace
2. Generate RSA key pair, store private in Databricks Secrets
3. Build proxy app (FastAPI: register, events, health)
4. Deploy proxy as Databricks App
5. Embed public key in pip package (`brickforge/lib/telemetry_pub.pem`)
6. Write `brickforge/lib/telemetry.py` (register + track + HMAC signing)
7. Add tracking section to config.json schema + UI fields in Setup App
8. Wire events at call sites (server.py, routes/setup.py, routes/projects.py, deploy)
9. Build Lakeview dashboard
10. Bump version, release

## Design decisions log

### Why not OpenTelemetry?
OTel solves distributed tracing across microservices (spans, latency, error rates). Our problem is product analytics: who deployed what for whom. A row per event. OTel would add collector infrastructure, exporter config, and a backend - all to extract 5 fields. Overkill by a mile.

### Why not Cloudflare Worker + Google Sheet?
Discussed as a fast-ship option (1 day). Rejected - do this cleanly on Databricks from the start. No quick-and-dirty, no building twice.

### Why RSA handshake over plain UUID?
Plain UUID as header: anyone who knows the endpoint URL can spam. RSA raises the bar from "know a URL" to "reverse-engineer the registration protocol." ~50 lines of code, 2-3 hours extra work. Not bulletproof (public key extractable from source), but stops casual abuse. Right tradeoff.

### Why SCIM token relay for identity?

**What is SCIM?** System for Cross-domain Identity Management. REST API for user management. Databricks exposes it at `/api/2.0/preview/scim/v2/`. The `/Me` endpoint returns identity of whoever owns the token. Already on every workspace, nothing to set up.

**The insight:** The proxy doesn't ask the user who they are - it asks their workspace. Like showing a company-issued badge to a bouncer who calls the company to verify. The user never says their name. The company confirms it.

**Workspace-scoped but cross-workspace:** The token is scoped to the SA's workspace, not the central telemetry workspace. But the proxy only needs to *read* identity (SCIM `/Me`), not *write* to that workspace. So it calls the SA's workspace for identity, writes to the central Delta table. Works across any workspace.

### Why plain file for telemetry credentials, not keyring?
Keyring is for sensitive tokens (workspace access, resource permissions). A telemetry `client_id` is a throwaway identifier. If someone finds it, they can send analytics events as you. Who cares. `~/.brickforge/telemetry_id` is fine.

### HTTPS vs HMAC - different jobs
- HTTPS (TLS): **confidentiality** - encrypts everything in transit. Built into Python, zero code.
- HMAC: **authenticity + integrity** - proves message came from registered client, wasn't tampered. Does NOT encrypt.
- Both needed. HTTPS so nobody reads the data. HMAC so nobody forges it.

### TLS in simple terms
1. CLI: "I want to talk securely"
2. Proxy: "Here's my certificate + public key (signed by trusted CA)"
3. CLI: verifies cert, generates random session key, encrypts with proxy's public key
4. Proxy: decrypts with private key - both sides share session key
5. All traffic encrypted from here on

Steps 1-4: milliseconds, once per connection. Step 5: the actual data. Python handles all of this automatically.

## Open questions

- Central workspace: which one? Dedicated or reuse existing?
- Telemetry proxy URL: telemetry.brickforge.dev or direct DBX App URL?
- Opt-out: should CLI have a `--no-telemetry` flag? (probably yes for external users)
