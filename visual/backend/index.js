'use strict'

require('dotenv').config({ path: require('path').resolve(__dirname, '../../.env.local') })

const express        = require('express')
const fs             = require('fs')
const path           = require('path')
const { spawn }      = require('child_process')
const { execFile }   = require('child_process')
const { buildGraph } = require('./lib/graph-builder')

const PORT        = process.env.VISUAL_BACKEND_PORT || 9001
const LAYOUT_FILE = path.resolve(__dirname, '../graph-layout.json')
const ENV_FILE    = path.resolve(__dirname, '../../.env.local')
const PROJECT_ROOT = path.resolve(__dirname, '../..')
const app         = express()

const SENSITIVE_PATTERN = /TOKEN|SECRET|PASSWORD|PAT\b/i

// Parse .env.local into ordered list of active entries, preserving raw lines
function parseEnvFile() {
  let raw = ''
  try { raw = fs.readFileSync(ENV_FILE, 'utf8') } catch { return [] }

  const entries = []
  const seen = new Set()

  for (const line of raw.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eq = trimmed.indexOf('=')
    if (eq < 0) continue
    const key = trimmed.slice(0, eq).trim()
    const value = trimmed.slice(eq + 1)
    if (seen.has(key)) continue  // last active wins — skip duplicates above
    seen.add(key)
    entries.push({ key, value, sensitive: SENSITIVE_PATTERN.test(key) })
  }
  return entries
}

// Update values in .env.local, preserving all comments and structure.
// Only touches the last active (uncommented) line for each key.
function writeEnvValues(updates) {
  let raw = ''
  try { raw = fs.readFileSync(ENV_FILE, 'utf8') } catch { raw = '' }

  const lines = raw.split('\n')
  // Find last active line index for each key
  const lastActive = {}
  lines.forEach((line, i) => {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) return
    const eq = trimmed.indexOf('=')
    if (eq < 0) return
    const key = trimmed.slice(0, eq).trim()
    if (key in updates) lastActive[key] = i
  })

  for (const [key, newVal] of Object.entries(updates)) {
    if (lastActive[key] !== undefined) {
      lines[lastActive[key]] = `${key}=${newVal}`
    } else {
      // Key not present — append
      lines.push(`${key}=${newVal}`)
    }
  }

  fs.writeFileSync(ENV_FILE, lines.join('\n'))
}

// Comment out specific keys in .env.local (for switching to same-workspace mode)
function commentOutKeys(keys) {
  let raw = ''
  try { raw = fs.readFileSync(ENV_FILE, 'utf8') } catch { return }
  const keySet = new Set(keys)
  const out = raw.split('\n').map(line => {
    const trimmed = line.trim()
    if (trimmed.startsWith('#')) return line
    const eq = trimmed.indexOf('=')
    if (eq < 0) return line
    const key = trimmed.slice(0, eq).trim()
    return keySet.has(key) ? '#' + line : line
  })
  fs.writeFileSync(ENV_FILE, out.join('\n'))
}

app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'GET,PUT,POST,OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type')
  if (req.method === 'OPTIONS') return res.sendStatus(204)
  next()
})
app.use(express.json())

function loadLayout() {
  try {
    return JSON.parse(fs.readFileSync(LAYOUT_FILE, 'utf8'))
  } catch {
    return {}
  }
}

function saveLayout(positions) {
  fs.writeFileSync(LAYOUT_FILE, JSON.stringify(positions, null, 2))
}

app.get('/health', (_req, res) => {
  res.json({ ok: true })
})

app.get('/api/graph', (_req, res) => {
  try {
    const graph    = buildGraph()
    const saved    = loadLayout()
    // Merge saved positions over computed defaults
    graph.nodes = graph.nodes.map((n) =>
      saved[n.id] ? { ...n, position: saved[n.id] } : n
    )
    res.json(graph)
  } catch (err) {
    console.error('[graph-builder] error:', err)
    res.status(500).json({ error: String(err) })
  }
})

// PUT /api/layout  body: { id: { x, y }, ... }
app.put('/api/layout', (req, res) => {
  try {
    const positions = req.body
    if (typeof positions !== 'object' || Array.isArray(positions)) {
      return res.status(400).json({ error: 'expected object { nodeId: {x,y} }' })
    }
    saveLayout(positions)
    res.json({ ok: true })
  } catch (err) {
    console.error('[layout] save error:', err)
    res.status(500).json({ error: String(err) })
  }
})

app.get('/api/env', (_req, res) => {
  try {
    res.json(parseEnvFile())
  } catch (err) {
    res.status(500).json({ error: String(err) })
  }
})

// PUT /api/env  body: { KEY: "new value", ... }
app.put('/api/env', (req, res) => {
  try {
    const updates = req.body
    if (typeof updates !== 'object' || Array.isArray(updates)) {
      return res.status(400).json({ error: 'expected { KEY: value, ... }' })
    }
    writeEnvValues(updates)
    res.json({ ok: true })
  } catch (err) {
    console.error('[env] save error:', err)
    res.status(500).json({ error: String(err) })
  }
})

// ─── Setup endpoints ───────────────────────────────────────────────────────────

const STEP_ENV_KEYS = {
  host:      ['DATABRICKS_HOST'],
  auth:      ['DATABRICKS_TOKEN'],
  warehouse: ['DATABRICKS_WAREHOUSE_ID'],
  schema:    ['PROJECT_UNITY_CATALOG_SCHEMA'],
  model:     ['AGENT_MODEL_ENDPOINT'],
  genie:     ['PROJECT_GENIE_CHECKIN'],
  ka:        ['PROJECT_KA_PASSENGERS'],
  mlflow:    ['MLFLOW_EXPERIMENT_ID'],
  grants:    [],  // always re-runnable, no single env key
}

// GET /api/setup/status — parse .env.local, return per-step status
app.get('/api/setup/status', (_req, res) => {
  try {
    const entries = parseEnvFile()
    const env = {}
    for (const { key, value } of entries) env[key] = value

    const steps = {}
    for (const [step, keys] of Object.entries(STEP_ENV_KEYS)) {
      const allSet = keys.length === 0 ? false : keys.every(k => env[k] && env[k].trim())
      steps[step] = {
        status: keys.length === 0 ? 'unknown' : (allSet ? 'configured' : 'missing'),
        values: Object.fromEntries(keys.map(k => [k, env[k] || ''])),
      }
    }

    res.json({ steps, env })
  } catch (err) {
    res.status(500).json({ error: String(err) })
  }
})

// GET /api/setup/profiles — list databricks CLI profiles
app.get('/api/setup/profiles', (_req, res) => {
  execFile('databricks', ['auth', 'profiles'], { cwd: PROJECT_ROOT, timeout: 10000 }, (err, stdout) => {
    if (err) {
      return res.json({ profiles: [], error: String(err) })
    }
    const lines = stdout.split('\n').slice(1).filter(l => l.trim())
    const profiles = []
    for (const line of lines) {
      const parts = line.trim().split(/\s{2,}/)
      if (parts.length >= 2) {
        const name  = parts[0].trim()
        const host  = parts[1].trim()
        const valid = line.toUpperCase().includes('YES')
        if (name && host) profiles.push({ name, host, valid })
      }
    }
    res.json({ profiles })
  })
})

// GET /api/setup/resources?type=warehouses|catalogs|genie
app.get('/api/setup/resources', (req, res) => {
  const type = req.query.type

  const SCRIPTS = {
    warehouses: `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import json
w = WorkspaceClient()
out = [{'id': wh.id, 'name': wh.name, 'state': str(wh.state).split('.')[-1]} for wh in w.warehouses.list()]
print(json.dumps(out))
`.trim(),
    catalogs: `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import json
w = WorkspaceClient()
out = [c.name for c in w.catalogs.list() if c.name]
print(json.dumps(out))
`.trim(),
    genie: `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import json
w = WorkspaceClient()
try:
  r = w.genie.list_spaces()
  spaces = getattr(r, 'spaces', []) or []
except:
  spaces = []
out = [{'id': str(getattr(s,'space_id',None) or getattr(s,'id','')), 'name': getattr(s,'title','?')} for s in spaces]
print(json.dumps(out))
`.trim(),
  }

  const script = SCRIPTS[type]
  if (!script) return res.status(400).json({ error: 'unknown type: ' + type })

  execFile('uv', ['run', 'python', '-c', script], {
    cwd: PROJECT_ROOT,
    timeout: 20000,
  }, (err, stdout, stderr) => {
    if (err) {
      return res.json({ items: [], error: stderr || String(err) })
    }
    try {
      const items = JSON.parse(stdout.trim())
      res.json({ items })
    } catch {
      res.json({ items: [], error: 'parse error: ' + stdout.slice(0, 200) })
    }
  })
})

// POST /api/setup/exec — SSE stream, runs actual setup commands
const PAT_SCRIPT = `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from scripts.py.setup_dbx_env import _profile_for_host, _isolated_client, _redact, write_env_entry, ENV_FILE
import os
host = os.environ['DATABRICKS_HOST'].strip()
profile = _profile_for_host(host)
if not profile: print('[x] No matching CLI profile for', host); exit(1)
w = _isolated_client(profile)
t = w.tokens.create(comment='agent-forge-init', lifetime_seconds=604800)
write_env_entry(ENV_FILE, 'DATABRICKS_TOKEN', t.token_value)
print('[+] PAT generated (7d):', _redact(t.token_value))
`.trim()

const SAVE_WAREHOUSE_SCRIPT = (id) => `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
import re; from pathlib import Path
f = Path('.env.local')
lines = f.read_text().splitlines() if f.exists() else []
new = []; found = False
for line in lines:
    m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=', line)
    if m and m.group(1) == 'DATABRICKS_WAREHOUSE_ID': new.append('DATABRICKS_WAREHOUSE_ID=${id}'); found = True
    else: new.append(line)
if not found: new.append('DATABRICKS_WAREHOUSE_ID=${id}')
f.write_text('\\n'.join(new) + '\\n')
print('[+] DATABRICKS_WAREHOUSE_ID =', '${id}')
`.trim().replace(/\$\{id\}/g, id)

const SAVE_SCHEMA_SCRIPT = (catalog, schema) => `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient
import re; from pathlib import Path; import json
w = WorkspaceClient()
spec = '${catalog}.${schema}'
try:
    w.schemas.get(full_name=spec)
    print('[+] schema exists:', spec)
except:
    try:
        w.catalogs.get(name='${catalog}')
        w.schemas.create(name='${schema}', catalog_name='${catalog}')
        print('[+] schema created:', spec)
    except Exception as e2:
        try:
            w.catalogs.create(name='${catalog}')
            w.schemas.create(name='${schema}', catalog_name='${catalog}')
            print('[+] catalog + schema created:', spec)
        except Exception as e3:
            print('[x]', str(e3)); exit(1)
f = Path('.env.local')
lines = f.read_text().splitlines() if f.exists() else []
new = []; found = False
for line in lines:
    m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=', line)
    if m and m.group(1) == 'PROJECT_UNITY_CATALOG_SCHEMA': new.append('PROJECT_UNITY_CATALOG_SCHEMA=' + spec); found = True
    else: new.append(line)
if not found: new.append('PROJECT_UNITY_CATALOG_SCHEMA=' + spec)
f.write_text('\\n'.join(new) + '\\n')
print('[+] PROJECT_UNITY_CATALOG_SCHEMA =', spec)
`.trim().replace(/\$\{catalog\}/g, catalog).replace(/\$\{schema\}/g, schema)

const SAVE_GENIE_SCRIPT = (id, name) => `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
import re; from pathlib import Path
f = Path('.env.local')
lines = f.read_text().splitlines() if f.exists() else []
new = []; found = False
for line in lines:
    m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=', line)
    if m and m.group(1) == 'PROJECT_GENIE_CHECKIN': new.append('PROJECT_GENIE_CHECKIN=${id}'); found = True
    else: new.append(line)
if not found: new.append('PROJECT_GENIE_CHECKIN=${id}')
f.write_text('\\n'.join(new) + '\\n')
print('[+] PROJECT_GENIE_CHECKIN = ${id}  (${name})')
`.trim().replace(/\$\{id\}/g, id).replace(/\$\{name\}/g, name)

app.post('/api/setup/exec', (req, res) => {
  const { action, params = {} } = req.body || {}

  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache')
  res.setHeader('X-Accel-Buffering', 'no')
  res.setHeader('Connection', 'keep-alive')

  const write = (type, data) => {
    if (!res.writableEnded) {
      res.write(`event:${type}\ndata:${JSON.stringify(data)}\n\n`)
    }
  }

  const done = (ok, code = ok ? 0 : 1) => {
    write('done', { ok, code })
    if (!res.writableEnded) res.end()
  }

  // Load .env.local vars into subprocess environment
  const envEntries = parseEnvFile()
  const subEnv = { ...process.env }
  for (const { key, value } of envEntries) subEnv[key] = value

  function runCommand(cmd, args, extraEnv = {}) {
    const proc = spawn(cmd, args, {
      cwd: PROJECT_ROOT,
      env: { ...subEnv, ...extraEnv },
    })
    proc.stdout.on('data', d => write('line', { text: d.toString(), stream: 'out' }))
    proc.stderr.on('data', d => write('line', { text: d.toString(), stream: 'err' }))
    proc.on('error', err => {
      write('line', { text: '[x] ' + err.message + '\n', stream: 'err' })
      done(false)
    })
    proc.on('close', code => done(code === 0, code))
    req.on('close', () => { try { proc.kill() } catch {} })
  }

  function synthetic(lines) {
    for (const line of lines) write('line', { text: line + '\n', stream: 'out' })
    done(true)
  }

  switch (action) {
    case 'exec-pat':
      runCommand('uv', ['run', 'python', '-c', PAT_SCRIPT])
      break

    case 'exec-assets':
      runCommand('uv', ['run', 'python', 'data/init/create_all_assets.py'])
      break

    case 'exec-mlflow':
      runCommand('uv', ['run', 'python', 'data/init/create_mlflow_experiment.py'])
      break

    case 'exec-grants':
      runCommand('bash', ['deploy/run_all_grants.sh'])
      break

    case 'exec-genie': {
      const genieName = params.name || 'Checkin Metrics'
      runCommand('uv', ['run', 'python', 'data/init/create_genie_space.py'], { GENIE_ROOM_NAME: genieName })
      break
    }

    case 'exec-same': {
      try {
        commentOutKeys(['AGENT_MODEL_ENDPOINT', 'AGENT_MODEL_TOKEN'])
        synthetic([
          '[+] same-workspace mode selected',
          '[+] AGENT_MODEL_ENDPOINT commented out (will use DATABRICKS_HOST at runtime)',
          '[+] AGENT_MODEL_TOKEN commented out',
          '[+] ready',
        ])
      } catch (err) {
        write('line', { text: '[x] ' + err.message + '\n', stream: 'err' })
        done(false)
      }
      break
    }

    case 'save-warehouse': {
      const warehouseId = params.id
      if (!warehouseId) { done(false); break }
      runCommand('uv', ['run', 'python', '-c', SAVE_WAREHOUSE_SCRIPT(warehouseId)])
      break
    }

    case 'save-schema': {
      const { catalog, schema } = params
      if (!catalog || !schema) { done(false); break }
      runCommand('uv', ['run', 'python', '-c', SAVE_SCHEMA_SCRIPT(catalog, schema)])
      break
    }

    case 'save-genie': {
      const { id: genieId, name: genieName } = params
      if (!genieId) { done(false); break }
      runCommand('uv', ['run', 'python', '-c', SAVE_GENIE_SCRIPT(genieId, genieName || '')])
      break
    }

    default:
      write('line', { text: '[x] unknown action: ' + action + '\n', stream: 'err' })
      done(false)
  }
})

// GET /api/setup/test?step=<id> — test the live connection for a configured step
const TEST_SCRIPTS = {
  host: `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
import os, urllib.request, json, ssl
host = os.environ.get('DATABRICKS_HOST','').strip().rstrip('/')
token = os.environ.get('DATABRICKS_TOKEN','').strip()
if not host: print('[x] DATABRICKS_HOST not set'); exit(1)
ctx = ssl.create_default_context()
req = urllib.request.Request(host + '/api/2.0/preview/scim/v2/Me')
if token: req.add_header('Authorization', 'Bearer ' + token)
try:
    with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
        d = json.loads(r.read())
        print('[+] reachable — ' + d.get('userName', '?'))
except urllib.error.HTTPError as e:
    if e.code in (401, 403): print('[~] host reachable (auth required)')
    else: print('[x] HTTP ' + str(e.code)); exit(1)
except Exception as e:
    print('[x] ' + str(e)[:100]); exit(1)
`.trim(),

  auth: `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
import os, urllib.request, json, ssl
host = os.environ.get('DATABRICKS_HOST','').strip().rstrip('/')
token = os.environ.get('DATABRICKS_TOKEN','').strip()
if not host: print('[x] DATABRICKS_HOST not set'); exit(1)
if not token: print('[x] DATABRICKS_TOKEN not set'); exit(1)
ctx = ssl.create_default_context()
try:
    req = urllib.request.Request(host + '/api/2.0/preview/scim/v2/Me', headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
        d = json.loads(r.read())
        print('[+] authenticated — ' + d.get('userName', '?'))
except Exception as e:
    print('[x] ' + str(e)[:100]); exit(1)
`.trim(),

  warehouse: `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import os
wh_id = os.environ.get('DATABRICKS_WAREHOUSE_ID','').strip()
if not wh_id: print('[x] DATABRICKS_WAREHOUSE_ID not set'); exit(1)
w = WorkspaceClient()
try:
    wh = w.warehouses.get(wh_id)
    state = str(wh.state).split('.')[-1]
    print('[+] reachable — ' + wh.name + ' (' + state + ')')
except Exception as e:
    print('[x] ' + str(e)[:100]); exit(1)
`.trim(),

  schema: `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import os
spec = os.environ.get('PROJECT_UNITY_CATALOG_SCHEMA','').strip()
if not spec: print('[x] PROJECT_UNITY_CATALOG_SCHEMA not set'); exit(1)
w = WorkspaceClient()
try:
    s = w.schemas.get(full_name=spec)
    print('[+] found — ' + (s.full_name or spec))
except Exception as e:
    print('[x] ' + str(e)[:100]); exit(1)
`.trim(),

  model: `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
import os, urllib.request, json, ssl
endpoint = os.environ.get('AGENT_MODEL_ENDPOINT','').strip()
host = os.environ.get('DATABRICKS_HOST','').strip().rstrip('/')
if not endpoint: endpoint = host + '/serving-endpoints/databricks-claude-sonnet-4-6/invocations'
token = (os.environ.get('AGENT_MODEL_TOKEN','') or os.environ.get('DATABRICKS_TOKEN','')).strip()
if not token: print('[x] no token (AGENT_MODEL_TOKEN or DATABRICKS_TOKEN)'); exit(1)
payload = json.dumps({'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 5}).encode()
ctx = ssl.create_default_context()
try:
    req = urllib.request.Request(endpoint, data=payload, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        d = json.loads(r.read())
        print('[+] responding — ' + d.get('model','?'))
except urllib.error.HTTPError as e:
    body = e.read().decode()[:120]
    print('[x] HTTP ' + str(e.code) + ' ' + body); exit(1)
except Exception as e:
    print('[x] ' + str(e)[:100]); exit(1)
`.trim(),

  genie: `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import os
sid = os.environ.get('PROJECT_GENIE_CHECKIN','').strip()
if not sid: print('[x] PROJECT_GENIE_CHECKIN not set'); exit(1)
w = WorkspaceClient()
try:
    sp = w.genie.get_space(space_id=sid)
    print('[+] found — ' + getattr(sp, 'title', sid))
except Exception as e:
    print('[x] ' + str(e)[:100]); exit(1)
`.trim(),

  ka: `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import os
ka_name = os.environ.get('PROJECT_KA_PASSENGERS','').strip()
if not ka_name: print('[x] PROJECT_KA_PASSENGERS not set'); exit(1)
w = WorkspaceClient()
try:
    ep = w.serving_endpoints.get(name=ka_name)
    state = str(ep.state.ready).split('.')[-1] if ep.state else '?'
    print('[+] active — ' + ep.name + ' (' + state + ')')
except Exception as e:
    print('[x] ' + str(e)[:100]); exit(1)
`.trim(),

  mlflow: `
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import os
eid = os.environ.get('MLFLOW_EXPERIMENT_ID','').strip()
if not eid: print('[x] MLFLOW_EXPERIMENT_ID not set'); exit(1)
w = WorkspaceClient()
try:
    exp = w.experiments.get_experiment(experiment_id=eid)
    print('[+] found — ' + getattr(exp, 'name', eid))
except Exception as e:
    print('[x] ' + str(e)[:100]); exit(1)
`.trim(),
}

app.get('/api/setup/test', (req, res) => {
  const step = req.query.step
  const script = TEST_SCRIPTS[step]
  if (!script) return res.json({ ok: false, message: 'no test for step: ' + step })

  execFile('uv', ['run', 'python', '-c', script], {
    cwd: PROJECT_ROOT,
    timeout: 25000,
  }, (err, stdout, stderr) => {
    const raw = (stdout || '').trim() || (stderr || '').trim()
    const ok = !err && raw.startsWith('[+]')
    const message = raw.replace(/^\[.\] /, '')
    res.json({ ok, message: message || (err ? String(err) : 'no output') })
  })
})

app.listen(PORT, () => {
  console.log(`[visual-backend] listening on http://localhost:${PORT}`)
})
