import { useCallback, useEffect, useState, useRef } from 'react'
import { RefreshCw, Hammer, FileText, Database, Code2, Cog } from 'lucide-react'
import { ProgressStepper } from './ProgressStepper'

interface AssetFile {
  name: string
  size: number
}

interface AssetsResponse {
  assets: {
    prompts: AssetFile[]
    tables: AssetFile[]
    csv: AssetFile[]
    functions: AssetFile[]
    procedures: AssetFile[]
    demo: AssetFile[]
    manifests: AssetFile[]
  }
  total: number
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  return `${(bytes / 1024).toFixed(1)}KB`
}

// ── Build stepper ──────────────────────────────────────────────────────────

const BUILD_STAGES = [
  { match: 'schema', label: 'Schema' },
  { match: 'tables', label: 'Tables' },
  { match: 'functions', label: 'Functions' },
  { match: 'procedures', label: 'Procedures' },
  { match: 'genie', label: 'Genie' },
  { match: 'mlflow', label: 'MLflow' },
]

function colorize(text: string): string {
  return text
    .replace(/\x1b\[[0-9;]*m/g, '')  // strip ANSI escape codes
    .replace(/\[x\]/g, '<span class="text-red-400">[x]</span>')
    .replace(/\[\+\]/g, '<span class="text-emerald-400">[+]</span>')
    .replace(/\[~\]/g, '<span class="text-amber-400">[~]</span>')
}

// ── Asset group component ──────────────────────────────────────────────────

function AssetGroup({ label, icon: Icon, files }: { label: string; icon: typeof FileText; files: AssetFile[] }) {
  if (files.length === 0) return null
  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="h-3.5 w-3.5 text-dbx-gray-400 dark:text-dbx-gray-500" />
        <span className="text-[10px] font-semibold text-dbx-gray-400 dark:text-dbx-gray-500 uppercase tracking-wider">
          {label} ({files.length})
        </span>
      </div>
      <div className="rounded-lg border border-dbx-gray-200 dark:border-dbx-gray-800 bg-white dark:bg-dbx-gray-900 overflow-hidden">
        {files.map((f, i) => (
          <div key={f.name} className={`flex items-center justify-between px-3 py-1.5 font-mono text-xs ${
            i < files.length - 1 ? 'border-b border-dbx-gray-50 dark:border-dbx-gray-800/50' : ''
          }`}>
            <span className="text-dbx-gray-700 dark:text-dbx-gray-200 truncate">{f.name}</span>
            <span className="text-dbx-gray-400 dark:text-dbx-gray-600 text-[10px] ml-2 flex-shrink-0">{formatSize(f.size)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export function StashHealthView() {
  const [assets, setAssets] = useState<AssetsResponse['assets'] | null>(null)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [connected, setConnected] = useState(false)
  const [prereqs, setPrereqs] = useState<{ host: boolean; warehouse: boolean; schema: boolean }>({ host: false, warehouse: false, schema: false })

  // Build state
  const [building, setBuilding] = useState(false)
  const [buildLines, setBuildLines] = useState<string[]>([])
  const [buildStage, setBuildStage] = useState(0)
  const [buildDone, setBuildDone] = useState<boolean | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Check workspace connection (re-check when tab becomes visible)
  const checkConnected = useCallback(() => {
    fetch('/api/setup/status')
      .then(r => r.json())
      .then(data => {
        const steps = data.steps || {}
        const hostOk = steps.host?.status === 'configured'
        const whOk = steps.warehouse?.status === 'configured'
        const schemaOk = steps.schema?.status === 'configured'
        setPrereqs({ host: hostOk, warehouse: whOk, schema: schemaOk })
        setConnected(hostOk && whOk && schemaOk)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    checkConnected()
    const onSwitch = () => checkConnected()
    window.addEventListener('switch-view', onSwitch)
    return () => window.removeEventListener('switch-view', onSwitch)
  }, [checkConnected])

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    fetch('/api/assets')
      .then(r => r.json() as Promise<AssetsResponse>)
      .then(body => {
        setAssets(body.assets)
        setTotal(body.total)
      })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  // Fetch last build log on mount
  useEffect(() => {
    fetch('/api/setup/exec-log?action=exec-build')
      .then(r => r.json())
      .then(data => { if (data.lines?.length) setBuildLines(data.lines) })
      .catch(() => {})
  }, [])

  // Scroll terminal to bottom
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [buildLines])

  const startBuild = useCallback(async () => {
    setBuilding(true)
    setBuildLines([])
    setBuildStage(0)
    setBuildDone(null)

    try {
      const resp = await fetch('/api/setup/exec', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'exec-build', params: {} }),
      })
      const reader = resp.body?.getReader()
      if (!reader) return
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const chunks = buf.split('\n\n')
        buf = chunks.pop() ?? ''

        for (const chunk of chunks) {
          let evtType = 'message', evtData = ''
          for (const line of chunk.split('\n')) {
            if (line.startsWith('event:')) evtType = line.slice(6).trim()
            if (line.startsWith('data:'))  evtData = line.slice(5).trim()
          }
          if (!evtData) continue
          try {
            const parsed = JSON.parse(evtData)
            if (evtType === 'line') {
              const text = parsed.text ?? ''
              if (text.trim()) setBuildLines(prev => [...prev, text])
              const lower = text.toLowerCase()
              setBuildStage(prev => {
                for (let i = prev; i < BUILD_STAGES.length; i++) {
                  if (lower.includes(BUILD_STAGES[i].match)) return i + 1
                }
                return prev
              })
            } else if (evtType === 'done') {
              setBuildDone(parsed.ok)
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch {
      setBuildDone(false)
      setBuildLines(prev => [...prev, '[x] Build failed -- connection error'])
    }
  }, [])

  return (
    <div className="flex flex-col h-full max-w-2xl">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-dbx-gray-200 dark:border-dbx-gray-800">
        <div>
          <h2 className="text-sm font-semibold text-dbx-gray-900 dark:text-dbx-gray-100">Assets</h2>
          <p className="text-[11px] text-dbx-gray-500 dark:text-dbx-gray-400 mt-0.5">
            {total > 0 ? `${total} files in current project` : 'No assets in current project'}
          </p>
          {total > 0 && (
            <div className="mt-1 space-y-0.5">
              {[
                { ok: prereqs.host, label: 'workspace', step: 'host' },
                { ok: prereqs.warehouse, label: 'warehouse', step: 'warehouse' },
                { ok: prereqs.schema, label: 'catalog/schema', step: 'schema' },
              ].map(p => (
                <div key={p.step} className="flex items-center gap-1.5">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${p.ok ? 'bg-dbx-green' : 'bg-dbx-red'}`} />
                  <button
                    onClick={() => {
                      window.dispatchEvent(new CustomEvent('switch-view', { detail: 'setup' }))
                      setTimeout(() => window.dispatchEvent(new CustomEvent('activate-step', { detail: p.step })), 100)
                    }}
                    className={`text-[11px] font-mono ${p.ok ? 'text-dbx-gray-400' : 'text-dbx-red dark:text-[#FF6B5A] hover:underline'}`}
                    disabled={p.ok}
                  >
                    {p.label}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={startBuild}
            disabled={!connected || building || total === 0}
            title={!connected ? 'Connect workspace and set schema in Setup first' : total === 0 ? 'No assets to build' : 'Build all assets on workspace'}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium font-mono rounded-md
              bg-dbx-red text-white hover:bg-dbx-red/90 transition-colors
              disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Hammer className="h-3 w-3" />
            Build
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md
              bg-dbx-gray-100 dark:bg-dbx-gray-800 text-dbx-gray-600 dark:text-dbx-gray-300
              hover:bg-dbx-gray-200 dark:hover:bg-dbx-gray-700 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {error && (
          <div className="rounded-lg border border-dbx-red-lt bg-dbx-red-bg dark:bg-dbx-red-bg-dk dark:border-dbx-gray-800 px-4 py-3 text-sm text-dbx-red dark:text-[#FF6B5A] mb-4">
            {error}
          </div>
        )}

        {loading && !assets && (
          <div className="text-sm text-dbx-gray-400 animate-pulse">Loading assets...</div>
        )}

        {!loading && total === 0 && !error && (
          <div className="text-center py-16">
            <div className="text-dbx-gray-300 dark:text-dbx-gray-600 mb-3">
              <Database className="w-8 h-8 mx-auto" />
            </div>
            <div className="text-[13px] font-mono text-dbx-gray-500 dark:text-dbx-gray-400 mb-1">No assets yet</div>
            <p className="text-[12px] font-mono text-dbx-gray-400 dark:text-dbx-gray-500">
              Import a .forge.zip bundle or generate data in the Data tab
            </p>
          </div>
        )}

        {assets && (
          <>
            <AssetGroup label="Prompts" icon={FileText} files={assets.prompts} />
            <AssetGroup label="Table SQL" icon={Database} files={assets.tables} />
            <AssetGroup label="CSV Data" icon={Database} files={assets.csv} />
            <AssetGroup label="Functions" icon={Code2} files={assets.functions} />
            <AssetGroup label="Procedures" icon={Code2} files={assets.procedures} />
            <AssetGroup label="Demo Data" icon={Database} files={assets.demo} />
            <AssetGroup label="Manifests" icon={Cog} files={assets.manifests} />
          </>
        )}
      </div>

      {/* Build modal */}
      {building && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40 dark:bg-black/60 backdrop-blur-[2px]" />
          <div className="relative w-[520px] max-h-[80vh] bg-white dark:bg-dbx-gray-900 border border-dbx-gray-200 dark:border-dbx-gray-700 rounded-xl shadow-2xl flex flex-col">
            <div className="px-5 py-4 border-b border-dbx-gray-100 dark:border-dbx-gray-800">
              <h3 className="text-[14px] font-semibold text-dbx-gray-900 dark:text-dbx-gray-100 font-mono">
                Building project assets
              </h3>
            </div>

            <div className="flex px-5 py-3 gap-4">
              {/* Stepper */}
              <div className="flex-shrink-0">
                <ProgressStepper
                  stages={BUILD_STAGES.map(s => s.label)}
                  currentStage={buildStage}
                />
              </div>

              {/* Terminal */}
              <div
                ref={scrollRef}
                className="flex-1 bg-dbx-gray-950 rounded-lg p-3 font-mono text-[11px] text-dbx-gray-300 overflow-y-auto max-h-[50vh] min-h-[200px]"
              >
                {buildLines.map((line, i) => (
                  <div key={i} dangerouslySetInnerHTML={{ __html: colorize(line) }} />
                ))}
                {buildDone === null && buildLines.length > 0 && (
                  <div className="text-dbx-amber animate-pulse mt-1">...</div>
                )}
              </div>
            </div>

            <div className="px-5 py-3 border-t border-dbx-gray-100 dark:border-dbx-gray-800 flex justify-end">
              {buildDone !== null ? (
                <button
                  onClick={() => { setBuilding(false); setBuildDone(null); setBuildLines([]); setBuildStage(0) }}
                  className="px-4 py-1.5 text-[12px] font-mono rounded-lg border border-dbx-gray-200 dark:border-dbx-gray-700 text-dbx-gray-600 dark:text-dbx-gray-400 hover:bg-dbx-gray-50 dark:hover:bg-dbx-gray-800"
                >
                  Close
                </button>
              ) : (
                <span className="text-[11px] font-mono text-dbx-gray-400 animate-pulse">Building...</span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
