import { useCallback, useEffect, useRef, useState } from 'react'
import type { StepId, SetupPhase, DbxProfile, DbxWarehouse, DbxGenieSpace, ExecLine } from '../types'
import { SETUP_STEPS } from '../setupSteps'

interface SetupDrawerProps {
  activeStep: StepId
  phase: SetupPhase
  selectedChoice: number | null
  execLines: ExecLine[]
  currentValues: Record<string, string>
  onSelectChoice: (i: number) => void
  onContinue: () => void
  onBack: () => void
  onReconfigure: () => void
  onExecDone: (ok: boolean) => void
  onNext?: () => void
}

// ─── Resource hook ─────────────────────────────────────────────────────────────

function useFetchOnce<T>(url: string | null) {
  const [data, setData]       = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  useEffect(() => {
    if (!url) return
    setLoading(true)
    fetch(url)
      .then(r => r.json() as Promise<Record<string, unknown>>)
      .then(body => {
        if (body.error) setError(body.error as string)
        else setData((body.items ?? body.profiles ?? null) as T)
      })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [url])
  return { data, loading, error }
}

// ─── Resource pickers ──────────────────────────────────────────────────────────

function ProfileList({ selected, onSelect }: { selected: string; onSelect: (n: string) => void }) {
  const { data, loading, error } = useFetchOnce<DbxProfile[]>('/api/setup/profiles')
  const profiles = (data as DbxProfile[]) || []
  if (loading) return <Spinner label="loading profiles…" />
  if (error)   return <ErrMsg msg={error} />
  return (
    <>
      <Label>select cli profile</Label>
      <InfoBox>Profiles marked valid are authenticated and ready to use.</InfoBox>
      {profiles.map(p => (
        <PickRow key={p.name} active={selected === p.name} disabled={!p.valid} onClick={() => p.valid && onSelect(p.name)}>
          <Dot color={p.valid ? 'green' : 'gray'} />
          <span className="flex-1 font-mono text-[13px] text-zinc-800 dark:text-zinc-100 truncate">{p.name}</span>
          <span className="text-[11px] text-zinc-400 dark:text-zinc-500 font-mono truncate max-w-[160px]">{p.host.replace('https://', '')}</span>
          {p.valid && <Tag color="green">valid</Tag>}
        </PickRow>
      ))}
    </>
  )
}

function WarehouseList({ selected, onSelect }: { selected: string; onSelect: (id: string, name: string) => void }) {
  const { data, loading, error } = useFetchOnce<DbxWarehouse[]>('/api/setup/resources?type=warehouses')
  const warehouses = (data as DbxWarehouse[]) || []
  if (loading) return <Spinner label="loading warehouses…" />
  if (error)   return <ErrMsg msg={error} />
  return (
    <>
      <Label>available warehouses</Label>
      {warehouses.map(wh => {
        const running = wh.state?.toUpperCase().includes('RUNNING')
        return (
          <PickRow key={wh.id} active={selected === wh.id} onClick={() => onSelect(wh.id, wh.name)}>
            <Dot color={running ? 'green' : 'gray'} />
            <span className="flex-1 font-mono text-[13px] text-zinc-800 dark:text-zinc-100">{wh.name}</span>
            {running && <Tag color="green">running</Tag>}
          </PickRow>
        )
      })}
    </>
  )
}

function CatalogPicker({ catalog, schema, onCatalog, onSchema }: {
  catalog: string; schema: string; onCatalog: (c: string) => void; onSchema: (s: string) => void
}) {
  const { data, loading, error } = useFetchOnce<string[]>('/api/setup/resources?type=catalogs')
  const catalogs = (data as string[]) || []
  if (loading) return <Spinner label="loading catalogs…" />
  if (error)   return <ErrMsg msg={error} />
  return (
    <>
      <Label>available catalogs</Label>
      {catalogs.map(c => (
        <PickRow key={c} active={catalog === c} onClick={() => onCatalog(c)}>
          <Dot color="green" />
          <span className="font-mono text-[13px] text-zinc-800 dark:text-zinc-100">{c}</span>
        </PickRow>
      ))}
      <div className="mt-3">
        <Label>schema name</Label>
        <Input value={schema} onChange={onSchema} placeholder="main" />
      </div>
    </>
  )
}

function GenieList({ selected, onSelect }: { selected: string; onSelect: (id: string, name: string) => void }) {
  const { data, loading, error } = useFetchOnce<DbxGenieSpace[]>('/api/setup/resources?type=genie')
  const spaces = (data as DbxGenieSpace[]) || []
  if (loading) return <Spinner label="loading genie spaces…" />
  if (error)   return <ErrMsg msg={error} />
  if (spaces.length === 0) return <InfoBox>No genie spaces found — use "create new room" instead.</InfoBox>
  return (
    <>
      <Label>available genie spaces</Label>
      {spaces.map(s => (
        <PickRow key={s.id} active={selected === s.id} onClick={() => onSelect(s.id, s.name)}>
          <Dot color="green" />
          <span className="flex-1 font-mono text-[13px] text-zinc-800 dark:text-zinc-100">{s.name}</span>
          <span className="text-[11px] text-zinc-400 dark:text-zinc-600 font-mono">{s.id.slice(0, 8)}…</span>
        </PickRow>
      ))}
    </>
  )
}

// ─── Atoms ─────────────────────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-[15px] text-zinc-400 dark:text-zinc-500 uppercase tracking-wider mb-2 font-mono">{children}</div>
}

function InfoBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 rounded p-3 text-[16px] font-mono text-zinc-500 dark:text-zinc-400 leading-relaxed mb-3">
      {children}
    </div>
  )
}

function Spinner({ label }: { label: string }) {
  return <div className="text-[16px] text-zinc-400 dark:text-zinc-500 font-mono">{label}</div>
}

function ErrMsg({ msg }: { msg: string }) {
  return <div className="text-[16px] text-red-400 font-mono">{msg}</div>
}

function Dot({ color }: { color: 'green' | 'gray' | 'amber' | 'red' }) {
  const cls = { green: 'bg-[#1D9E75]', gray: 'bg-zinc-300 dark:bg-zinc-600', amber: 'bg-[#EF9F27]', red: 'bg-[#E24B4A]' }
  return <div className={`w-2 h-2 rounded-full flex-shrink-0 ${cls[color]}`} />
}

function Tag({ color, children }: { color: 'green' | 'purple'; children: React.ReactNode }) {
  const cls = color === 'green'
    ? 'bg-[#E1F5EE] dark:bg-[#0f2a1e] text-[#0F6E56] dark:text-[#1D9E75]'
    : 'bg-[#EEEDFE] dark:bg-[#1e1d40] text-[#534AB7] dark:text-[#9f9af5]'
  return <span className={`text-[14px] rounded px-1.5 py-0.5 font-mono ${cls}`}>{children}</span>
}

function PickRow({ active, disabled = false, onClick, children }: {
  active: boolean; disabled?: boolean; onClick: () => void; children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`
        w-full flex items-center gap-2 px-3 py-2.5 rounded border mb-1.5 text-left transition-colors
        ${active
          ? 'border-[#534AB7] dark:border-[#7b74e8] bg-[#EEEDFE] dark:bg-[#2d2960]/50'
          : disabled
            ? 'border-zinc-100 dark:border-zinc-800/50 opacity-40 cursor-not-allowed bg-white dark:bg-zinc-900'
            : 'border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 hover:border-zinc-400 dark:hover:border-zinc-600'}
      `}
    >
      {children}
    </button>
  )
}

function Input({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <input
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full text-[18px] font-mono bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded px-3 py-2 outline-none focus:border-[#534AB7] dark:focus:border-[#7b74e8] text-zinc-800 dark:text-zinc-100 placeholder:text-zinc-300 dark:placeholder:text-zinc-600"
    />
  )
}

// ─── Terminal ──────────────────────────────────────────────────────────────────

function Terminal({ lines }: { lines: ExecLine[] }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight }, [lines])

  function color(text: string, stream: string) {
    if (stream === 'err' && !text.startsWith('[+]')) return 'text-[#EF9F27]'
    if (text.startsWith('[+]') || text.startsWith('✓')) return 'text-[#1D9E75]'
    if (text.startsWith('[x]') || text.startsWith('✗')) return 'text-[#E24B4A]'
    if (text.startsWith('[~]') || text.startsWith('▸') || text.startsWith('...')) return 'text-[#EF9F27]'
    return 'text-zinc-400'
  }

  return (
    <div ref={ref} className="bg-[#0d0d10] rounded p-3 font-mono text-[16px] leading-relaxed h-[280px] overflow-y-auto border border-zinc-800/50">
      {lines.length === 0 && <div className="text-zinc-600">running…</div>}
      {lines.map((l, i) => (
        <div key={i} className={color(l.text.trim(), l.stream)}>{l.text.trimEnd()}</div>
      ))}
    </div>
  )
}

// ─── Current value helper ──────────────────────────────────────────────────────

function currentValueLabel(stepId: StepId, values: Record<string, string>): string {
  const v = values
  switch (stepId) {
    case 'host':      return v.DATABRICKS_HOST?.replace('https://', '') || ''
    case 'auth':      return v.DATABRICKS_TOKEN ? v.DATABRICKS_TOKEN.slice(0, 4) + '*'.repeat(Math.max(0, v.DATABRICKS_TOKEN.length - 4)) : ''
    case 'warehouse': return v.DATABRICKS_WAREHOUSE_ID || ''
    case 'schema':    return v.PROJECT_UNITY_CATALOG_SCHEMA || ''
    case 'model':     return v.AGENT_MODEL_ENDPOINT?.replace('https://', '') || ''
    case 'genie':     return v.PROJECT_GENIE_CHECKIN || ''
    case 'ka':        return v.PROJECT_KA_PASSENGERS || ''
    case 'mlflow':    return v.MLFLOW_EXPERIMENT_ID || ''
    default:          return ''
  }
}

// ─── Main drawer ───────────────────────────────────────────────────────────────

export function SetupDrawer({
  activeStep, phase, selectedChoice, execLines, currentValues,
  onSelectChoice, onContinue, onBack, onReconfigure, onExecDone, onNext,
}: SetupDrawerProps) {
  const step      = SETUP_STEPS.find(s => s.id === activeStep)!
  const choice    = selectedChoice !== null ? step.choices[selectedChoice] : null
  const keepLabel = currentValueLabel(activeStep, currentValues)

  const TESTABLE_STEPS: StepId[] = ['host', 'auth', 'warehouse', 'schema', 'model', 'genie', 'ka', 'mlflow']
  type TestState = { status: 'idle' | 'loading' | 'ok' | 'fail'; message: string }
  const [testState, setTestState] = useState<TestState>({ status: 'idle', message: '' })

  useEffect(() => { setTestState({ status: 'idle', message: '' }) }, [activeStep])

  const handleTest = useCallback(async () => {
    setTestState({ status: 'loading', message: '' })
    try {
      const r = await fetch(`/api/setup/test?step=${activeStep}`)
      const text = await r.text()
      let data: { ok: boolean; message: string }
      try {
        data = JSON.parse(text)
      } catch {
        data = { ok: false, message: r.status === 404 ? 'backend needs restart' : text.slice(0, 120).replace(/<[^>]+>/g, '').trim() || 'unexpected response' }
      }
      setTestState({ status: data.ok ? 'ok' : 'fail', message: data.message })
    } catch (e) {
      setTestState({ status: 'fail', message: String(e) })
    }
  }, [activeStep])

  const [selProfile, setSelProfile]     = useState('')
  const [selWhId, setSelWhId]           = useState('')
  const [selWhName, setSelWhName]       = useState('')
  const [selCatalog, setSelCatalog]     = useState('')
  const [catSchema, setCatSchema]       = useState('main')
  const [selGenieId, setSelGenieId]     = useState('')
  const [selGenieName, setSelGenieName] = useState('')
  const [manualVal, setManualVal]       = useState('')
  const [genieName, setGenieName]       = useState('')

  useEffect(() => {
    setSelProfile(''); setSelWhId(''); setSelWhName('')
    setSelCatalog(''); setCatSchema('main')
    setSelGenieId(''); setSelGenieName('')
    setManualVal(''); setGenieName('')
  }, [activeStep, selectedChoice])

  // SSE runner
  useEffect(() => {
    if (phase !== 'execute' || !choice) return
    let action = choice.action
    const params: Record<string, string> = {}

    if (action === 'cfg-warehouse' && selWhId)    { action = 'save-warehouse'; Object.assign(params, { id: selWhId, name: selWhName }) }
    if (action === 'cfg-catalog'   && selCatalog) { action = 'save-schema';    Object.assign(params, { catalog: selCatalog, schema: catSchema || 'main' }) }
    if (action === 'cfg-genie'     && selGenieId) { action = 'save-genie';     Object.assign(params, { id: selGenieId, name: selGenieName }) }
    if (action === 'exec-genie'    && genieName)  { Object.assign(params, { name: genieName }) }

    let aborted = false
    async function run() {
      try {
        const resp = await fetch('/api/setup/exec', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action, params }),
        })
        if (!resp.body) { onExecDone(false); return }
        const reader  = resp.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        while (true) {
          if (aborted) { reader.cancel(); break }
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
            const parsed = JSON.parse(evtData)
            if (evtType === 'line')      window.dispatchEvent(new CustomEvent('exec-line', { detail: parsed }))
            else if (evtType === 'done' && !aborted) onExecDone(parsed.ok)
          }
        }
      } catch (e) {
        console.error('[exec]', e)
        if (!aborted) onExecDone(false)
      }
    }
    run()
    return () => { aborted = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase])

  const PHASES = ['choose', 'configure', 'execute', 'done'] as const
  const phaseIdx = PHASES.indexOf(phase)

  // ── Choose ─────────────────────────────────────────────────────────────────
  function renderChoose() {
    return (
      <>
        <div className="flex-1 overflow-y-auto px-4 pt-3 pb-2">
          {step.choices.map((c, i) => (
            <button
              key={i}
              onClick={() => onSelectChoice(i)}
              className={`
                w-full flex items-start gap-3 px-3 py-3 rounded border mb-2 text-left transition-colors
                ${selectedChoice === i
                  ? 'border-[#534AB7] dark:border-[#7b74e8] bg-[#EEEDFE] dark:bg-[#2d2960]/50'
                  : 'border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 hover:border-zinc-300 dark:hover:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-800/50'}
              `}
            >
              <span className={`text-[12px] font-mono mt-0.5 min-w-[18px] ${selectedChoice === i ? 'text-[#534AB7] dark:text-[#9f9af5]' : 'text-zinc-400 dark:text-zinc-500'}`}>
                {i + 1}
              </span>
              <div>
                <div className="text-[13px] font-medium text-zinc-800 dark:text-zinc-100 leading-tight">{c.title}</div>
                <div className="text-[12px] text-zinc-400 dark:text-zinc-500 leading-snug mt-0.5">{c.desc}</div>
              </div>
            </button>
          ))}
        </div>
        <div className="px-4 py-3 border-t border-zinc-100 dark:border-zinc-800">
          <button
            onClick={onContinue}
            disabled={selectedChoice === null}
            className={`
              w-full text-[18px] py-2.5 rounded border font-mono transition-colors
              ${selectedChoice !== null
                ? 'border-[#534AB7] dark:border-[#7b74e8] text-[#534AB7] dark:text-[#9f9af5] hover:bg-[#EEEDFE] dark:hover:bg-[#2d2960]/50'
                : 'border-zinc-200 dark:border-zinc-800 text-zinc-300 dark:text-zinc-600 cursor-not-allowed'}
            `}
          >
            continue →
          </button>
        </div>
      </>
    )
  }

  // ── Configure ──────────────────────────────────────────────────────────────
  function renderConfigure() {
    if (!choice) return null
    const action = choice.action

    function canRun() {
      if (action === 'cfg-profile')   return !!selProfile
      if (action === 'cfg-warehouse') return !!selWhId
      if (action === 'cfg-catalog')   return !!selCatalog && !!catSchema
      if (action === 'cfg-genie')     return !!selGenieId
      if (action === 'exec-genie')    return !!genieName
      if (action === 'manual')        return !!manualVal.trim()
      return true
    }

    let body: React.ReactNode
    if (action === 'cfg-profile')
      body = <ProfileList selected={selProfile} onSelect={setSelProfile} />
    else if (action === 'cfg-warehouse')
      body = <WarehouseList selected={selWhId} onSelect={(id, name) => { setSelWhId(id); setSelWhName(name) }} />
    else if (action === 'cfg-catalog')
      body = <CatalogPicker catalog={selCatalog} schema={catSchema} onCatalog={setSelCatalog} onSchema={setCatSchema} />
    else if (action === 'cfg-genie')
      body = <GenieList selected={selGenieId} onSelect={(id, name) => { setSelGenieId(id); setSelGenieName(name) }} />
    else if (action === 'exec-genie')
      body = (<><Label>genie room name</Label><Input value={genieName} onChange={setGenieName} placeholder="Checkin Metrics" /></>)
    else if (action === 'manual')
      body = (<><Label>value</Label><Input value={manualVal} onChange={setManualVal} placeholder="paste value…" /><div className="text-[15px] text-zinc-400 dark:text-zinc-500 mt-2 font-mono">writes directly to .env.local</div></>)
    else if (action === 'cfg-grants')
      body = <InfoBox>Run the grant script to apply UC table, routine, and warehouse permissions to the app service principal.</InfoBox>
    else
      body = <InfoBox>Run `! databricks auth login --host &lt;url&gt;` in your terminal, then come back.</InfoBox>

    return (
      <>
        <div className="flex-1 overflow-y-auto px-4 pt-3 pb-2">{body}</div>
        <div className="px-4 py-3 border-t border-zinc-100 dark:border-zinc-800 flex flex-col gap-1.5">
          <button
            onClick={onContinue}
            disabled={!canRun()}
            className={`
              w-full text-[18px] py-2.5 rounded border font-mono transition-colors
              ${canRun()
                ? 'border-[#534AB7] dark:border-[#7b74e8] text-[#534AB7] dark:text-[#9f9af5] hover:bg-[#EEEDFE] dark:hover:bg-[#2d2960]/50'
                : 'border-zinc-200 dark:border-zinc-800 text-zinc-300 dark:text-zinc-600 cursor-not-allowed'}
            `}
          >
            run →
          </button>
          <button
            onClick={onBack}
            className="w-full text-[17px] py-2 rounded border border-zinc-200 dark:border-zinc-800 text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300 hover:border-zinc-300 dark:hover:border-zinc-700 font-mono transition-colors"
          >
            back
          </button>
        </div>
      </>
    )
  }

  // ── Execute ────────────────────────────────────────────────────────────────
  function renderExecute() {
    return (
      <>
        <div className="flex-1 overflow-y-auto px-4 pt-3 pb-2">
          <Terminal lines={execLines} />
        </div>
        <div className="px-4 py-3 border-t border-zinc-100 dark:border-zinc-800">
          <button disabled className="w-full text-[18px] py-2.5 rounded border border-zinc-200 dark:border-zinc-800 text-zinc-300 dark:text-zinc-600 cursor-not-allowed font-mono">
            running…
          </button>
        </div>
      </>
    )
  }

  // ── Done ───────────────────────────────────────────────────────────────────
  function renderDone() {
    return (
      <>
        <div className="flex-1 flex flex-col items-center justify-center px-4 pt-4 pb-2">
          <div className="text-[60px] text-[#1D9E75] mb-2 leading-none">✓</div>
          <div className="text-[20px] font-medium text-zinc-800 dark:text-zinc-100 mb-1">configured</div>
          <div className="text-[17px] text-zinc-400 dark:text-zinc-500 font-mono">{step.title}</div>
        </div>
        <div className="px-4 py-3 border-t border-zinc-100 dark:border-zinc-800 flex flex-col gap-2">
          {onNext && (
            <button
              onClick={onNext}
              className="w-full text-[18px] py-2.5 rounded border border-[#1D9E75] text-[#1D9E75] hover:bg-[#E1F5EE] dark:hover:bg-[#0f2a1e] font-mono transition-colors"
            >
              next →
            </button>
          )}
          <button
            onClick={onReconfigure}
            className="w-full text-[18px] py-2.5 rounded border border-[#534AB7] dark:border-[#7b74e8] text-[#534AB7] dark:text-[#9f9af5] hover:bg-[#EEEDFE] dark:hover:bg-[#2d2960]/50 font-mono transition-colors"
          >
            reconfigure
          </button>
        </div>
      </>
    )
  }

  return (
    <div className="flex flex-col h-full bg-white dark:bg-zinc-900">
      {/* Header */}
      <div className="px-4 py-3 border-b border-zinc-100 dark:border-zinc-800 flex-shrink-0">
        <div className="flex items-center justify-between mb-1">
          <div className="text-[15px] text-zinc-400 dark:text-zinc-500 uppercase tracking-wider font-mono">{step.label}</div>
          {phase !== 'choose' && (
            <button
              onClick={onBack}
              className="text-[15px] text-zinc-400 dark:text-zinc-500 border border-zinc-200 dark:border-zinc-700 rounded px-2 py-0.5 hover:text-zinc-600 dark:hover:text-zinc-300 font-mono transition-colors"
            >
              ← back
            </button>
          )}
        </div>
        <div className="text-[20px] font-medium text-zinc-800 dark:text-zinc-100 font-mono">{step.title}</div>
        {keepLabel && (
          <div className="flex items-center gap-2 mt-1">
            <div className="text-[17px] font-mono text-[#1D9E75] truncate flex-1">{keepLabel}</div>
            {TESTABLE_STEPS.includes(activeStep) && (
              <button
                onClick={handleTest}
                disabled={testState.status === 'loading'}
                className="flex-shrink-0 text-[11px] font-mono px-2 py-0.5 rounded border border-[#1D9E75] text-[#1D9E75] hover:bg-[#E1F5EE] dark:hover:bg-[#0f2a1e] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {testState.status === 'loading' ? 'testing…' : 'test ↗'}
              </button>
            )}
          </div>
        )}
        {testState.status !== 'idle' && testState.status !== 'loading' && (
          <div className={`text-[11px] font-mono mt-1 truncate ${testState.status === 'ok' ? 'text-[#1D9E75]' : 'text-[#E24B4A]'}`}>
            {testState.status === 'ok' ? '[+]' : '[x]'} {testState.message}
          </div>
        )}
      </div>

      {/* Trail */}
      <div className="flex items-center px-4 py-2 border-b border-zinc-100 dark:border-zinc-800 flex-shrink-0">
        {PHASES.map((p, i) => (
          <span key={p} className="flex items-center">
            <span className={`text-[15px] font-mono ${
              i < phaseIdx ? 'text-[#1D9E75]' : p === phase ? 'text-zinc-800 dark:text-zinc-100 font-medium' : 'text-zinc-300 dark:text-zinc-600'
            }`}>
              {p}
            </span>
            {i < PHASES.length - 1 && <span className="text-[15px] text-zinc-200 dark:text-zinc-700 mx-2">›</span>}
          </span>
        ))}
      </div>

      {/* Body + footer */}
      {phase === 'choose'    && renderChoose()}
      {phase === 'configure' && renderConfigure()}
      {phase === 'execute'   && renderExecute()}
      {phase === 'done'      && renderDone()}
    </div>
  )
}
