import { useEffect, useRef, useState, useCallback } from 'react'
import { Wand2, RotateCcw } from 'lucide-react'
import { ProgressStepper } from './ProgressStepper'

// ── Types ───────────────────────────────────────────────────────────────────

type MageMode = 'magic' | 'author'

const MAGE_BUILD_STAGES = [
  'Connecting workspace',
  'Setting up data home',
  'Building knowledge base',
  'Teaching new tricks',
  'Writing personality',
  'Powering up questions',
  'Launching into orbit',
]

interface ChoiceOption {
  id: string
  label: string
  description?: string
}

interface MageMessage {
  role: 'user' | 'assistant' | 'progress' | 'error' | 'tool' | 'stepper' | 'choice'
  text: string
  choices?: ChoiceOption[]
  toolName?: string
  toolArgs?: Record<string, unknown>
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function colorize(text: string): string {
  return text
    .replace(/\x1b\[[0-9;]*m/g, '')
    .replace(/\[x\]/g, '<span class="text-red-400">[x]</span>')
    .replace(/\[\+\]/g, '<span class="text-emerald-400">[+]</span>')
    .replace(/\[~\]/g, '<span class="text-amber-400">[~]</span>')
    .replace(/\[\?\]/g, '<span class="text-dbx-gray-400">[?]</span>')
}

// ── Component ───────────────────────────────────────────────────────────────

export function MageView() {
  const [messages, setMessages] = useState<MageMessage[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [mode, setMode] = useState<MageMode>('magic')
  const [phase, setPhase] = useState<string>('startup')
  const [buildStage, setBuildStage] = useState(-1)
  const [buildActive, setBuildActive] = useState(false)
  const [prereqs, setPrereqs] = useState<{ workspace: boolean; model: boolean; host?: string; modelName?: string } | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const streamingRef = useRef(false)

  // Load status + prerequisites on mount and on window focus
  const loadStatus = useCallback(() => {
    fetch('/api/mage/status')
      .then(r => r.json())
      .then(data => {
        setPhase(data.phase || 'startup')
        if (data.mode) setMode(data.mode)
        if (data.prereqs) setPrereqs(data.prereqs)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadStatus()
    const onFocus = () => loadStatus()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [loadStatus])

  // Resume: if backend says "ready" but we have no messages, show welcome-back
  useEffect(() => {
    if (phase === 'ready' && messages.length === 0) {
      appendMessage({ role: 'assistant', text: 'Session resumed. What would you like to do?' })
    }
  }, [phase])

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, thinking])

  const appendMessage = useCallback((msg: MageMessage) => {
    setMessages(prev => [...prev, msg])
  }, [])

  // Update last progress block instead of creating new ones
  const appendProgress = useCallback((line: string) => {
    setMessages(prev => {
      const last = prev[prev.length - 1]
      if (last && last.role === 'progress') {
        return [...prev.slice(0, -1), { ...last, text: last.text + line }]
      }
      return [...prev, { role: 'progress', text: line }]
    })
  }, [])

  const sendMessage = useCallback(async (text?: string, extraFields?: Record<string, unknown>) => {
    const msg = text ?? input.trim()
    if (!msg || streamingRef.current) return
    streamingRef.current = true
    setInput('')
    setIsStreaming(true)
    appendMessage({ role: 'user', text: msg })

    try {
      const resp = await fetch('/api/mage/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'text', content: msg, ...extraFields }),
      })
      if (!resp.body) { setIsStreaming(false); return }

      const reader = resp.body.getReader()
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

            switch (evtType) {
              case 'message':
                appendMessage({ role: 'assistant', text: parsed.text || '' })
                break
              case 'progress':
                appendProgress(parsed.line || parsed.text || '')
                break
              case 'error':
                appendMessage({ role: 'error', text: parsed.message || parsed.suggestion || 'An error occurred' })
                break
              case 'choice':
                appendMessage({
                  role: 'choice',
                  text: parsed.prompt || 'Choose an option:',
                  choices: (parsed.options || []).map((o: { id?: string; name?: string; label?: string; description?: string }, i: number) => ({
                    id: o.id || o.name || String(i),
                    label: o.label || o.name || o.id || `Option ${i + 1}`,
                    description: o.description,
                  })),
                })
                break
              case 'tool_call':
                if (mode === 'author') {
                  appendMessage({ role: 'tool', text: `${parsed.tool}`, toolName: parsed.tool, toolArgs: parsed.args })
                }
                break
              case 'thinking':
                setThinking(parsed.active)
                break
              case 'step':
                setBuildActive(true)
                if (parsed.status === 'done') setBuildStage(parsed.index + 1)
                else if (parsed.status === 'running') setBuildStage(parsed.index)
                else if (parsed.status === 'error') setBuildStage(parsed.index)
                break
              case 'done':
                setPhase(parsed.ok ? 'ready' : phase)
                setBuildActive(false)
                break
            }
          } catch {
            // ignore malformed events
          }
        }
      }
    } catch (e) {
      appendMessage({ role: 'error', text: `Connection error: ${e}` })
    } finally {
      streamingRef.current = false
      setIsStreaming(false)
      inputRef.current?.focus()
    }
  }, [input, isStreaming, mode, phase, appendMessage, appendProgress])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }, [sendMessage])

  const handleReset = useCallback(async () => {
    await fetch('/api/mage/reset', { method: 'POST' })
    setMessages([])
    setPhase('startup')
    setMode('magic')
  }, [])

  const goToSetup = useCallback(() => {
    window.dispatchEvent(new CustomEvent('switch-view', { detail: 'setup' }))
  }, [])

  const ready = prereqs?.workspace && prereqs?.model

  // ── Hero screen (no conversation yet) ──────────────────────────────────

  if (messages.length === 0 && phase === 'startup') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-6 p-8">
        <div className="flex items-center gap-3">
          <Wand2 className="w-8 h-8 text-dbx-orange" />
          <h1 className="text-2xl font-semibold text-dbx-gray-900 dark:text-dbx-gray-100">Mage</h1>
        </div>
        <p className="text-dbx-gray-500 dark:text-dbx-gray-400 text-center max-w-md">
          Describe what you want. I'll build it.
        </p>

        {prereqs && (
          <div className="flex flex-col gap-1.5 text-xs">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${prereqs.workspace ? 'bg-emerald-500' : 'bg-red-400'}`} />
              {prereqs.workspace
                ? <span className="text-dbx-gray-400">{prereqs.host}</span>
                : <span className="text-red-400">Workspace not connected. <button onClick={goToSetup} className="underline hover:text-dbx-orange">Set up workspace</button></span>
              }
            </div>
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${prereqs.model ? 'bg-emerald-500' : 'bg-red-400'}`} />
              {prereqs.model
                ? <span className="text-dbx-gray-400">{prereqs.modelName || 'AI model ready'}</span>
                : <span className="text-red-400">No AI model available. <button onClick={goToSetup} className="underline hover:text-dbx-orange">Set up model</button></span>
              }
            </div>
          </div>
        )}

        {/* Mode toggle */}
        <div className="flex gap-2 bg-dbx-gray-100 dark:bg-dbx-gray-800 rounded-lg p-1">
          <button
            onClick={() => setMode('magic')}
            className={`px-4 py-1.5 rounded-md text-xs font-medium transition-all ${
              mode === 'magic'
                ? 'bg-white dark:bg-dbx-gray-700 text-dbx-gray-900 dark:text-dbx-gray-100 shadow-sm'
                : 'text-dbx-gray-400 dark:text-dbx-gray-500'
            }`}
          >
            Magic
          </button>
          <button
            onClick={() => setMode('author')}
            className={`px-4 py-1.5 rounded-md text-xs font-medium transition-all ${
              mode === 'author'
                ? 'bg-white dark:bg-dbx-gray-700 text-dbx-gray-900 dark:text-dbx-gray-100 shadow-sm'
                : 'text-dbx-gray-400 dark:text-dbx-gray-500'
            }`}
          >
            Author
          </button>
        </div>

        {/* Input - disabled until prerequisites met */}
        <div className="w-full max-w-lg">
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && ready) {
                e.preventDefault()
                sendMessage(undefined, { mode })
              }
            }}
            disabled={!ready}
            placeholder={ready ? "e.g. Space pizza delivery service for sci-fi travelers" : "Connect workspace first..."}
            className={`w-full px-4 py-3 rounded-xl border text-sm focus:outline-none focus:ring-2 focus:ring-dbx-orange/50 ${
              ready
                ? 'border-dbx-gray-200 dark:border-dbx-gray-700 bg-white dark:bg-dbx-gray-900 text-dbx-gray-900 dark:text-dbx-gray-100 placeholder-dbx-gray-400'
                : 'border-dbx-gray-200 dark:border-dbx-gray-800 bg-dbx-gray-50 dark:bg-dbx-gray-900/50 text-dbx-gray-400 cursor-not-allowed'
            }`}
            autoFocus={!!ready}
          />
        </div>
      </div>
    )
  }

  // ── Chat view ──────────────────────────────────────────────────────────

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-dbx-gray-200 dark:border-dbx-gray-800">
        <div className="flex items-center gap-2">
          <Wand2 className="w-4 h-4 text-dbx-orange" />
          <span className="text-xs font-medium text-dbx-gray-600 dark:text-dbx-gray-400">Mage</span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
            mode === 'magic'
              ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400'
              : 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
          }`}>
            {mode}
          </span>
        </div>
        <button
          onClick={handleReset}
          className="text-dbx-gray-400 hover:text-dbx-gray-600 dark:hover:text-dbx-gray-300 transition-colors"
          title="Reset conversation"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3 scrollbar-thin">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'user' ? (
              <div className="max-w-[80%] px-3 py-2 rounded-2xl rounded-br-sm bg-dbx-orange/10 text-dbx-gray-900 dark:text-dbx-gray-100 text-sm">
                {msg.text}
              </div>
            ) : msg.role === 'assistant' ? (
              <div className="max-w-[85%] px-3 py-2 rounded-2xl rounded-bl-sm bg-dbx-gray-100 dark:bg-dbx-gray-800 text-dbx-gray-900 dark:text-dbx-gray-100 text-sm prose prose-sm dark:prose-invert max-w-none"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.text) }}
              />
            ) : msg.role === 'progress' ? (
              <div className="w-full rounded-lg border border-dbx-gray-200 dark:border-dbx-gray-800 bg-dbx-gray-950 dark:bg-black overflow-hidden">
                <div className="p-2 max-h-32 overflow-y-auto font-mono text-[10px] leading-relaxed text-dbx-gray-400 scrollbar-thin">
                  {msg.text.split('\n').filter(Boolean).map((line, j) => (
                    <div key={j} dangerouslySetInnerHTML={{ __html: colorize(line) }} />
                  ))}
                </div>
              </div>
            ) : msg.role === 'error' ? (
              <div className="max-w-[85%] px-3 py-2 rounded-2xl rounded-bl-sm bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 text-sm">
                {msg.text}
              </div>
            ) : msg.role === 'tool' ? (
              <div className="px-2 py-1 rounded-md bg-dbx-gray-50 dark:bg-dbx-gray-900 border border-dbx-gray-200 dark:border-dbx-gray-800 text-[10px] font-mono text-dbx-gray-400">
                {msg.toolName}({JSON.stringify(msg.toolArgs || {}).slice(0, 80)})
              </div>
            ) : msg.role === 'choice' ? (
              <div className="max-w-[85%] space-y-2">
                <div className="px-3 py-2 rounded-2xl rounded-bl-sm bg-dbx-gray-100 dark:bg-dbx-gray-800 text-sm text-dbx-gray-900 dark:text-dbx-gray-100">
                  {msg.text}
                </div>
                <div className="flex flex-wrap gap-2">
                  {(msg.choices || []).map(choice => (
                    <button
                      key={choice.id}
                      onClick={() => sendMessage(choice.label, { type: 'choice', choice_id: choice.id })}
                      disabled={isStreaming}
                      className="px-3 py-1.5 rounded-lg border border-dbx-gray-200 dark:border-dbx-gray-700 bg-white dark:bg-dbx-gray-900 text-xs text-dbx-gray-700 dark:text-dbx-gray-300 hover:border-dbx-orange hover:text-dbx-orange transition-colors disabled:opacity-40"
                    >
                      {choice.label}
                      {choice.description && (
                        <span className="block text-[10px] text-dbx-gray-400 mt-0.5">{choice.description}</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ))}

        {/* Build progress stepper */}
        {buildActive && (
          <div className="flex justify-start">
            <div className="px-3 py-3 rounded-2xl rounded-bl-sm bg-dbx-gray-100 dark:bg-dbx-gray-800">
              <ProgressStepper stages={MAGE_BUILD_STAGES} currentStage={buildStage} />
            </div>
          </div>
        )}

        {/* Thinking indicator */}
        {thinking && (
          <div className="flex justify-start">
            <div className="px-3 py-2 rounded-2xl rounded-bl-sm bg-dbx-gray-100 dark:bg-dbx-gray-800">
              <div className="flex gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-dbx-gray-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-1.5 h-1.5 rounded-full bg-dbx-gray-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-1.5 h-1.5 rounded-full bg-dbx-gray-400 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t border-dbx-gray-200 dark:border-dbx-gray-800">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isStreaming ? 'Mage is working...' : 'Type a message...'}
            disabled={isStreaming}
            className="flex-1 px-3 py-2 rounded-lg border border-dbx-gray-200 dark:border-dbx-gray-700 bg-white dark:bg-dbx-gray-900 text-sm text-dbx-gray-900 dark:text-dbx-gray-100 placeholder-dbx-gray-400 focus:outline-none focus:ring-2 focus:ring-dbx-orange/50 disabled:opacity-50"
            autoFocus
          />
          <button
            onClick={() => sendMessage()}
            disabled={isStreaming || !input.trim()}
            className="px-4 py-2 rounded-lg bg-dbx-orange text-white text-sm font-medium hover:bg-dbx-orange/90 disabled:opacity-40 transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Minimal markdown renderer ───────────────────────────────────────────────

function renderMarkdown(text: string): string {
  return text
    // Headers
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-3 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-3 mb-1">$1</h2>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 rounded bg-dbx-gray-200 dark:bg-dbx-gray-700 text-[11px]">$1</code>')
    // Unordered lists
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    // Tables (basic)
    .replace(/\|(.+)\|/g, (match) => {
      if (match.includes('---')) return ''
      const cells = match.split('|').filter(Boolean).map(c => c.trim())
      return '<tr>' + cells.map(c => `<td class="px-2 py-1 border border-dbx-gray-200 dark:border-dbx-gray-700 text-xs">${c}</td>`).join('') + '</tr>'
    })
    // Line breaks
    .replace(/\n\n/g, '<br/><br/>')
    .replace(/\n/g, '<br/>')
    // Colorize [+]/[x]/[~]
    .replace(/\[x\]/g, '<span class="text-red-400">[x]</span>')
    .replace(/\[\+\]/g, '<span class="text-emerald-400">[+]</span>')
    .replace(/\[~\]/g, '<span class="text-amber-400">[~]</span>')
}
