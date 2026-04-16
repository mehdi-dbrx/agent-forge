'use strict'

require('dotenv').config({ path: require('path').resolve(__dirname, '../../.env.local') })

const express        = require('express')
const fs             = require('fs')
const path           = require('path')
const { buildGraph } = require('./lib/graph-builder')

const PORT        = process.env.VISUAL_BACKEND_PORT || 9001
const LAYOUT_FILE = path.resolve(__dirname, '../graph-layout.json')
const ENV_FILE    = path.resolve(__dirname, '../../.env.local')
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

app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*')
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

app.listen(PORT, () => {
  console.log(`[visual-backend] listening on http://localhost:${PORT}`)
})
