import { useEffect, useState, useCallback } from 'react'
import { X, Eye, EyeOff, Save, RotateCcw, AlertCircle, CheckCircle2, Settings2 } from 'lucide-react'

interface EnvEntry {
  key: string
  value: string
  sensitive: boolean
}

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

interface EnvEditorProps {
  open: boolean
  onClose: () => void
}

export function EnvEditor({ open, onClose }: EnvEditorProps) {
  const [entries, setEntries]     = useState<EnvEntry[]>([])
  const [edits, setEdits]         = useState<Record<string, string>>({})
  const [revealed, setRevealed]   = useState<Set<string>>(new Set())
  const [status, setStatus]       = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg]   = useState('')
  const [loading, setLoading]     = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    fetch('/api/env')
      .then((r) => r.json() as Promise<EnvEntry[]>)
      .then((data) => {
        setEntries(data)
        setEdits({})
        setStatus('idle')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  const changed = Object.keys(edits).filter((k) => {
    const orig = entries.find((e) => e.key === k)?.value ?? ''
    return edits[k] !== orig
  })

  const handleChange = (key: string, value: string) => {
    setEdits((prev) => ({ ...prev, [key]: value }))
    setStatus('idle')
  }

  const handleReset = () => {
    setEdits({})
    setStatus('idle')
  }

  const handleSave = async () => {
    if (changed.length === 0) return
    const updates: Record<string, string> = {}
    for (const k of changed) updates[k] = edits[k]

    setStatus('saving')
    setErrorMsg('')
    try {
      const r = await fetch('/api/env', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      })
      if (!r.ok) {
        const body = await r.json() as { error?: string }
        throw new Error(body.error ?? `HTTP ${r.status}`)
      }
      // Merge saved edits back into entries
      setEntries((prev) =>
        prev.map((e) => (e.key in updates ? { ...e, value: updates[e.key] } : e))
      )
      setEdits({})
      setStatus('saved')
      setTimeout(() => setStatus('idle'), 2500)
    } catch (err) {
      setErrorMsg(String(err))
      setStatus('error')
    }
  }

  const toggleReveal = (key: string) => {
    setRevealed((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  const getValue = (e: EnvEntry) => (e.key in edits ? edits[e.key] : e.value)
  const isDirty  = (e: EnvEntry) => e.key in edits && edits[e.key] !== e.value

  return (
    <div
      className={`
        absolute top-0 right-0 h-full w-[480px] bg-white border-l border-zinc-200 shadow-xl z-30
        flex flex-col transition-transform duration-200 ease-in-out
        ${open ? 'translate-x-0' : 'translate-x-full'}
      `}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-100">
        <div className="flex items-center gap-2">
          <Settings2 className="h-4 w-4 text-zinc-500" />
          <span className="text-sm font-semibold text-zinc-800">.env.local</span>
          {changed.length > 0 && (
            <span className="text-[10px] font-medium bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
              {changed.length} unsaved
            </span>
          )}
        </div>
        <button onClick={onClose} className="p-1 rounded hover:bg-zinc-100 text-zinc-400 hover:text-zinc-600">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Entries */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-sm text-zinc-400">Loading…</div>
        ) : (
          <table className="w-full text-xs">
            <tbody>
              {entries.map((e) => {
                const val = getValue(e)
                const dirty = isDirty(e)
                const shown = revealed.has(e.key)
                return (
                  <tr
                    key={e.key}
                    className={`border-b border-zinc-100 ${dirty ? 'bg-amber-50' : ''}`}
                  >
                    <td className="pl-4 pr-2 py-2.5 text-zinc-500 font-mono whitespace-nowrap align-middle w-1/2">
                      {dirty && <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 mr-1.5 align-middle" />}
                      {e.key}
                    </td>
                    <td className="pr-3 py-1.5 align-middle">
                      <div className="flex items-center gap-1">
                        <input
                          type={e.sensitive && !shown ? 'password' : 'text'}
                          value={val}
                          onChange={(ev) => handleChange(e.key, ev.target.value)}
                          className={`
                            w-full font-mono text-[11px] bg-transparent border rounded px-2 py-1 outline-none
                            ${dirty
                              ? 'border-amber-300 focus:border-amber-400'
                              : 'border-transparent focus:border-zinc-300'}
                          `}
                          spellCheck={false}
                        />
                        {e.sensitive && (
                          <button
                            onClick={() => toggleReveal(e.key)}
                            className="shrink-0 text-zinc-300 hover:text-zinc-500"
                            title={shown ? 'Hide' : 'Reveal'}
                          >
                            {shown ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-zinc-100 flex items-center justify-between gap-3">
        {/* Status */}
        <div className="flex items-center gap-1.5 text-xs min-w-0">
          {status === 'saved' && (
            <>
              <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
              <span className="text-green-600">Saved</span>
            </>
          )}
          {status === 'error' && (
            <>
              <AlertCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
              <span className="text-red-600 truncate">{errorMsg}</span>
            </>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {changed.length > 0 && (
            <button
              onClick={handleReset}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100 rounded"
            >
              <RotateCcw className="h-3 w-3" />
              Reset
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={changed.length === 0 || status === 'saving'}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 text-xs rounded font-medium
              ${changed.length === 0 || status === 'saving'
                ? 'bg-zinc-100 text-zinc-400 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'}
            `}
          >
            <Save className="h-3 w-3" />
            {status === 'saving' ? 'Saving…' : `Save${changed.length > 0 ? ` (${changed.length})` : ''}`}
          </button>
        </div>
      </div>
    </div>
  )
}
