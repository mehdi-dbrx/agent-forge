import { useEffect, useState, useCallback, useRef } from 'react'
import { ReactFlowProvider, type Node, type NodeMouseHandler } from '@xyflow/react'
import { Settings2, Moon, Sun, RefreshCw, FolderOpen, Plus, Trash2, Pencil, Package, Upload, Info } from 'lucide-react'
import { ArchCanvas } from './components/ArchCanvas'
import { Legend } from './components/Legend'
import { NodeDetailPanel } from './components/NodeDetailPanel'
import { EnvEditor } from './components/EnvEditor'
import { SetupView } from './components/SetupView'
import { DataView } from './components/DataView'
import { CleanupView } from './components/CleanupView'
import { KaDocsView } from './components/KaDocsView'
import { StashHealthView } from './components/StashHealthView'
import { MageView } from './components/MageView'
import type { GraphResponse, ArchNode, ArchNodeData } from './types'

type View = 'mage' | 'arch' | 'setup' | 'data' | 'ka' | 'stash' | 'cleanup'

interface Project {
  name: string
  source: string
  path?: string
  size: number
}

function ProjectMenuItem({
  project,
  isCurrentProject,
  onLoad,
  onRename,
  onDelete,
}: {
  project: Project
  isCurrentProject: boolean
  onLoad: () => void
  onRename: (newName: string) => void
  onDelete: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState(project.name)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleteInput, setDeleteInput] = useState('')

  const doRename = () => {
    const trimmed = editName.trim()
    if (!trimmed || trimmed === project.name) { setEditing(false); return }
    onRename(trimmed)
    setEditing(false)
  }

  return (
    <div className="flex items-center justify-between px-3 py-1.5 hover:bg-dbx-gray-50 dark:hover:bg-dbx-gray-800 group" onClick={e => e.stopPropagation()}>
      {editing ? (
        <input
          value={editName} onChange={e => setEditName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') doRename(); if (e.key === 'Escape') setEditing(false) }}
          autoFocus
          className="text-xs font-mono flex-1 bg-transparent border-b border-dbx-blue dark:border-dbx-green text-dbx-gray-800 dark:text-dbx-gray-100 outline-none mr-2"
        />
      ) : (
        <button
          onClick={onLoad}
          className={`text-xs font-mono truncate flex-1 text-left ${
            isCurrentProject
              ? 'text-dbx-blue dark:text-dbx-green font-semibold'
              : 'text-dbx-gray-700 dark:text-dbx-gray-300'
          }`}
        >
          {isCurrentProject ? '> ' : '  '}{project.name}
        </button>
      )}
      <span className="text-[10px] text-dbx-gray-400 dark:text-dbx-gray-600 mr-2">
        {project.source === 'volume' ? '☁' : ''} {(project.size / 1024).toFixed(0)}KB
      </span>
      {!editing && (
        <>
          <a
            href={`/api/projects/${encodeURIComponent(project.name)}/export`}
            download={`${project.name}.forge.zip`}
            onClick={e => e.stopPropagation()}
            className="opacity-0 group-hover:opacity-100 text-dbx-gray-400 hover:text-dbx-blue transition-all mr-1"
            title="Export project bundle"
          >
            <Package className="h-3 w-3" />
          </a>
          <button
            onClick={(e) => { e.stopPropagation(); setEditName(project.name); setEditing(true) }}
            className="opacity-0 group-hover:opacity-100 text-dbx-gray-400 hover:text-dbx-blue transition-all mr-1"
            title="Rename project"
          >
            <Pencil className="h-3 w-3" />
          </button>
        </>
      )}
      <button
        onClick={(e) => { e.stopPropagation(); setConfirmDelete(true) }}
        className="opacity-0 group-hover:opacity-100 text-dbx-gray-400 hover:text-dbx-red transition-all"
        title="Delete project"
      >
        <Trash2 className="h-3 w-3" />
      </button>
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={() => { setConfirmDelete(false); setDeleteInput('') }}>
          <div className="absolute inset-0 bg-black/40 dark:bg-black/60 backdrop-blur-[2px]" />
          <div onClick={e => e.stopPropagation()} className="relative w-[340px] bg-white dark:bg-dbx-gray-900 border border-dbx-gray-200 dark:border-dbx-gray-700 rounded-xl shadow-2xl p-5">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-7 h-7 rounded-lg bg-dbx-error/10 dark:bg-dbx-error/20 flex items-center justify-center">
                <Trash2 className="w-3.5 h-3.5 text-dbx-error" />
              </div>
              <h3 className="text-[14px] font-semibold text-dbx-gray-900 dark:text-dbx-gray-100 font-mono">Delete {project.name}?</h3>
            </div>
            <p className="text-[12px] text-dbx-gray-500 dark:text-dbx-gray-400 ml-9 mb-3">This cannot be undone. The project config will be permanently deleted.</p>
            <div className="ml-9 mb-4">
              <p className="text-[11px] font-mono text-dbx-gray-400 dark:text-dbx-gray-500 mb-1.5">Type <span className="text-dbx-error font-semibold">{project.name}</span> to confirm:</p>
              <input
                value={deleteInput}
                onChange={e => setDeleteInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && deleteInput === project.name) { setConfirmDelete(false); setDeleteInput(''); onDelete() } }}
                autoFocus
                className="w-full px-2.5 py-1.5 text-[12px] font-mono rounded-md border border-dbx-gray-200 dark:border-dbx-gray-700 bg-white dark:bg-dbx-gray-800 text-dbx-gray-800 dark:text-dbx-gray-100 outline-none focus:border-dbx-error"
                placeholder={project.name}
              />
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => { setConfirmDelete(false); setDeleteInput('') }} className="px-3.5 py-1.5 text-[12px] font-mono rounded-lg border border-dbx-gray-200 dark:border-dbx-gray-700 text-dbx-gray-600 dark:text-dbx-gray-400 hover:bg-dbx-gray-50 dark:hover:bg-dbx-gray-800">cancel</button>
              <button
                disabled={deleteInput !== project.name}
                onClick={() => { setConfirmDelete(false); setDeleteInput(''); onDelete() }}
                className="px-3.5 py-1.5 text-[12px] font-mono rounded-lg text-white bg-dbx-error hover:bg-dbx-error/90 disabled:opacity-30 disabled:cursor-not-allowed transition-opacity"
              >delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [view, setView]         = useState<View>('setup')
  const [dark, setDark]         = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches)
  const [graph, setGraph]       = useState<GraphResponse | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const [selected, setSelected] = useState<ArchNode | null>(null)
  const [envOpen, setEnvOpen]   = useState(false)
  const graphLoaded = useRef(false)

  // Project management
  const [projects, setProjects] = useState<{name: string; source: string; path?: string; size: number}[]>([])
  const [currentProject, setCurrentProject] = useState<string | null>(null)
  const [projectMenuOpen, setProjectMenuOpen] = useState(false)
  const [newProjectName, setNewProjectName] = useState('')
  const [showNewProject, setShowNewProject] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importLoading, setImportLoading] = useState(false)
  const [importError, setImportError] = useState('')
  const importInputRef = useRef<HTMLInputElement>(null)

  const refreshProjects = useCallback(() => {
    fetch('/api/projects')
      .then(r => r.json())
      .then((d: { projects: {name: string; source: string; path?: string; size: number}[]; current: string | null }) => {
        setProjects(d.projects || [])
        setCurrentProject(d.current)
        // First launch: no projects exist -- auto-create "my-project"
        if ((d.projects || []).length === 0 && !d.current) {
          fetch('/api/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'my-project' }),
          })
            .then(r2 => r2.json())
            .then(d2 => {
              if (d2.ok) {
                setCurrentProject(d2.name)
                // Re-fetch to get updated list
                fetch('/api/projects').then(r3 => r3.json()).then((d3: { projects: {name: string; source: string; path?: string; size: number}[]; current: string | null }) => {
                  setProjects(d3.projects || [])
                  setCurrentProject(d3.current)
                }).catch(() => {})
              }
            })
            .catch(() => {})
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => { refreshProjects() }, [refreshProjects])

  // Close project menu on outside click
  useEffect(() => {
    if (!projectMenuOpen) return
    const handler = () => setProjectMenuOpen(false)
    const timer = setTimeout(() => document.addEventListener('click', handler), 0)
    return () => { clearTimeout(timer); document.removeEventListener('click', handler) }
  }, [projectMenuOpen])

  const loadProject = useCallback((name: string) => {
    fetch(`/api/projects/${name}`)
      .then(r => r.json())
      .then(() => { window.location.reload() })
      .catch(() => {})
  }, [])

  const createProject = useCallback(() => {
    if (!newProjectName.trim()) return
    fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newProjectName.trim() }),
    })
      .then(async r => {
        const data = await r.json()
        if (!r.ok) { alert(data.error || 'Failed to create project'); return }
        window.location.reload()
      })
      .catch(e => alert(`Error: ${e.message}`))
  }, [newProjectName, refreshProjects])

  const deleteProject = useCallback((name: string) => {
    fetch(`/api/projects/${name}`, { method: 'DELETE' })
      .then(() => refreshProjects())
      .catch(() => {})
  }, [refreshProjects])

  const doImport = useCallback((mode: 'load' | 'new') => {
    if (!importFile) return
    setImportLoading(true)
    setImportError('')
    const form = new FormData()
    form.append('file', importFile)
    fetch(`/api/projects/import?mode=${mode}`, { method: 'POST', body: form })
      .then(async r => {
        const data = await r.json()
        if (!r.ok) { setImportError(data.error || 'Import failed'); setImportLoading(false); return }
        window.location.reload()
      })
      .catch(() => { setImportError('Import failed'); setImportLoading(false) })
  }, [importFile])

  // Apply dark class on <html> so all dark: utilities work everywhere
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  const loadGraph = useCallback((force = false) => {
    if (graphLoading) return
    if (!force && graphLoaded.current) return
    setGraphLoading(true)
    setError(null)
    fetch('/api/graph')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<GraphResponse>
      })
      .then((g) => { setGraph(g); graphLoaded.current = true })
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setGraphLoading(false))
  }, [graphLoading])

  // Load graph lazily when switching to arch tab
  useEffect(() => {
    if (view === 'arch') loadGraph()
  }, [view, loadGraph])

  const onNodeClick: NodeMouseHandler<Node<ArchNodeData>> = useCallback((_event, node) => {
    setEnvOpen(false)
    setSelected(node as ArchNode)
  }, [])

  const closePanel = useCallback(() => setSelected(null), [])
  const openEnv    = useCallback(() => { setSelected(null); setEnvOpen(true) }, [])
  const closeEnv   = useCallback(() => setEnvOpen(false), [])
  const switchView = useCallback((v: View) => { setView(v); setSelected(null); setEnvOpen(false) }, [])

  // Listen for switch-view events dispatched from child components (e.g. SetupDrawer)
  useEffect(() => {
    const handler = (e: Event) => switchView((e as CustomEvent<View>).detail)
    window.addEventListener('switch-view', handler)
    return () => window.removeEventListener('switch-view', handler)
  }, [switchView])

  // Bridge auth: detect #bridge/... or #bridge-success in URL fragment
  const [bridgeResult, setBridgeResult] = useState<{ ok: boolean; message: string } | null>(null)
  useEffect(() => {
    const hash = window.location.hash

    // Inline bridge auth success (no token in URL -- already captured in-process)
    if (hash === '#bridge-success') {
      window.history.replaceState(null, '', window.location.pathname)
      setBridgeResult({ ok: true, message: 'Authentication successful' })
      return
    }

    if (!hash.startsWith('#bridge/')) return

    // Parse fragment: #bridge/NONCE_ID/ENCRYPTED/HOST/USER
    const parts = hash.slice('#bridge/'.length).split('/')
    if (parts.length < 2) return

    const [nonceId, encrypted, host, user] = parts.map(p => decodeURIComponent(p))

    // Clear the hash immediately (remove token from address bar + history)
    window.history.replaceState(null, '', window.location.pathname)

    // POST to backend (browser sends SSO cookie automatically)
    fetch('/api/auth/bridge-receive', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ciphertext: encrypted,
        nonce_id: nonceId,
        host: host || '',
        user: user || '',
      }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          setBridgeResult({ ok: true, message: `Connected to ${host || 'workspace'}` })
          // Refresh all step states
          refreshProjects()
        } else {
          setBridgeResult({ ok: false, message: data.error || 'Failed to deliver token' })
        }
      })
      .catch(e => {
        setBridgeResult({ ok: false, message: String(e) })
      })
  }, [refreshProjects])

  // Show bridge auth result if this tab was opened by the bridge script
  if (bridgeResult) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-dbx-gray-950">
        {/* Logo bar */}
        <div className="flex items-center gap-4 mb-10">
          <svg className="h-12 w-12" viewBox="0 0 32 32" fill="none">
            <path d="M16 3L29 10.5V21.5L16 29L3 21.5V10.5L16 3Z" fill="#FF3522" opacity="0.12"/>
            <path d="M16 3L29 10.5V21.5L16 29L3 21.5V10.5L16 3Z" stroke="#FF3522" strokeWidth="1.5"/>
            <path d="M16 8L24 12.5V19.5L16 24L8 19.5V12.5L16 8Z" fill="#FF3522" opacity="0.35"/>
            <path d="M16 12L21 14.75V19.25L16 22L11 19.25V14.75L16 12Z" fill="#FF3522"/>
          </svg>
          <span className="text-[32px] font-semibold text-dbx-gray-100 tracking-tight">Brick<span className="text-dbx-red">Forge</span></span>
          <span className="text-dbx-gray-700 text-[28px] mx-1">|</span>
          <img src="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTMyIiBoZWlnaHQ9IjIyIiB2aWV3Qm94PSIwIDAgMTMyIDIyIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxwYXRoIGQ9Im0xOC4zMTggOS4yNzUtOC42MzEgNC44NTlMLjQ0NSA4Ljk0MiAwIDkuMTgydjMuNzdsOS42ODcgNS40MzEgOC42My00Ljg0djEuOTk1bC04LjYzIDQuODYtOS4yNDItNS4xOTItLjQ0NS4yNHYuNjQ2bDkuNjg3IDUuNDMyIDkuNjY4LTUuNDMydi0zLjc2OWwtLjQ0NS0uMjQtOS4yMjMgNS4xNzMtOC42NS00Ljg0VjEwLjQybDguNjUgNC44NCA5LjY2OC01LjQzVjYuMTE0bC0uNDgyLS4yNzctOS4xODYgNS4xNTVMMS40ODIgNi40MWw4LjIwNS00LjYgNi43NDEgMy43ODcuNTkzLS4zMzJ2LS40NjJMOS42ODcuNjg0IDAgNi4xMTV2LjU5Mmw5LjY4NyA1LjQzMiA4LjYzLTQuODZ6IiBmaWxsPSIjRUUzRDJDIi8+PHBhdGggZD0iTTM3LjQ0OSAxOC40NDNWMS44NTJoLTIuNTU2djYuMjA3YzAgLjA5My0uMDU2LjE2Ny0uMTQ4LjIwNGEuMjMuMjMgMCAwIDEtLjI0LS4wNTZjLS44NzEtMS4wMTYtMi4yMjMtMS41ODktMy43MDUtMS41ODktMy4xNjcgMC01LjY1IDIuNjYtNS42NSA2LjA2IDAgMS42NjMuNTc1IDMuMTk3IDEuNjMgNC4zMjRhNS40NCA1LjQ0IDAgMCAwIDQuMDIgMS43MzZjMS40NjMgMCAyLjgxNS0uNjEgMy43MDQtMS42NjIuMDU2LS4wNzQuMTY3LS4wOTMuMjQtLjA3NC4wOTMuMDM3LjE1LjExLjE1LjIwM3YxLjIzOHptLTYuMDkzLTIuMDE0Yy0yLjAzOCAwLTMuNjMtMS42NDQtMy42My0zLjc1IDAtMi4xMDcgMS41OTItMy43NTEgMy42My0zLjc1MXMzLjYzIDEuNjQ0IDMuNjMgMy43NS0xLjU5MyAzLjc1LTMuNjMgMy43NW0xOS43NjIgMi4wMTZWNi44OTZoLTIuNTM3VjguMDZjMCAuMDkzLS4wNTYuMTY2LS4xNDkuMjAzYS4yLjIgMCAwIDEtLjI0LS4wNzNjLS44NTItMS4wMTctMi4xODYtMS41OS0zLjcwNS0xLjU5LTMuMTY3IDAtNS42NDkgMi42NjEtNS42NDkgNi4wNiAwIDMuNCAyLjQ4MiA2LjA2IDUuNjUgNi4wNiAxLjQ2MyAwIDIuODE1LS42MSAzLjcwNC0xLjY4LjA1NS0uMDc1LjE2Ni0uMDkzLjI0LS4wNzUuMDkzLjAzNy4xNDkuMTExLjE0OS4yMDR2MS4yNTZoMi41Mzd6bS02LjA1Ni0yLjAxNGMtMi4wMzggMC0zLjYzLTEuNjQ1LTMuNjMtMy43NSAwLTIuMTA3IDEuNTkyLTMuNzUxIDMuNjMtMy43NTFzMy42MyAxLjY0NCAzLjYzIDMuNzUtMS41OTMgMy43NS0zLjYzIDMuNzVtMjcuNzgxIDIuMDE1VjYuODk2aC0yLjUzOFY4LjA2YzAgLjA5My0uMDU1LjE2Ni0uMTQ4LjIwM3MtLjE4NSAwLS4yNC0uMDczYy0uODUzLTEuMDE3LTIuMTg2LTEuNTktMy43MDUtMS41OS0zLjE4NiAwLTUuNjQ5IDIuNjYxLTUuNjQ5IDYuMDggMCAzLjQxNyAyLjQ4MiA2LjA2IDUuNjQ5IDYuMDYgMS40NjMgMCAyLjgxNS0uNjEgMy43MDQtMS42ODIuMDU2LS4wNzQuMTY3LS4wOTMuMjQxLS4wNzQuMDkzLjAzNy4xNDguMTEuMTQ4LjIwM3YxLjI1NnptLTYuMDU3LTIuMDE0Yy0yLjAzNyAwLTMuNjMtMS42NDUtMy42My0zLjc1IDAtMi4xMDcgMS41OTMtMy43NTEgMy42My0zLjc1MXMzLjYzIDEuNjQ0IDMuNjMgMy43NS0xLjU5MyAzLjc1LTMuNjMgMy43NW0xMC43MDYuNjQ3Yy4wMTkgMCAuMDU2LS4wMTkuMDc0LS4wMTkuMDU2IDAgLjEzLjAzNy4xNjcuMDc0Ljg3IDEuMDE2IDIuMjIyIDEuNTg5IDMuNzA0IDEuNTg5IDMuMTY3IDAgNS42NS0yLjY2IDUuNjUtNi4wNiAwLTEuNjYzLS41NzUtMy4xOTYtMS42My00LjMyM2E1LjQ0IDUuNDQgMCAwIDAtNC4wMi0xLjczN2MtMS40NjMgMC0yLjgxNS42MS0zLjcwNCAxLjY2My0uMDU2LjA3NC0uMTQ4LjA5Mi0uMjQuMDc0LS4wOTMtLjAzNy0uMTQ5LS4xMTEtLjE0OS0uMjA0VjEuODUyaC0yLjU1NnYxNi41OWgyLjU1NlYxNy4yOGMwLS4wOTMuMDU2LS4xNjYuMTQ4LS4yMDNtLS4yNi00LjM5OGMwLTIuMTA2IDEuNTk0LTMuNzUgMy42MzEtMy43NXMzLjYzIDEuNjQ0IDMuNjMgMy43NS0xLjU5MyAzLjc1LTMuNjMgMy43NS0zLjYzLTEuNjYyLTMuNjMtMy43NW0xNy4yNDQtMy40MTZjLjI0IDAgLjQ2My4wMTkuNjEuMDU2VjYuNjk1YTIuNCAyLjQgMCAwIDAtLjQyNS0uMDM3Yy0xLjMzNCAwLTIuNTU2LjY4NC0zLjIwNCAxLjc3NC0uMDU2LjA5Mi0uMTQ5LjEzLS4yNDEuMDkyYS4yMi4yMiAwIDAgMS0uMTY3LS4yMDNWNi44OThoLTIuNTM3djExLjU2NmgyLjU1NnYtNS4xYzAtMi41MyAxLjI5Ni00LjEgMy40MDgtNC4xbTQuODE1LTIuMzY3aC0yLjU5M3YxMS41NjZoMi41OTN6TTk3Ljk1OCAxLjg3YTEuNTcxIDEuNTcxIDAgMSAwIDAgMy4xNDEgMS41NzEgMS41NzEgMCAxIDAgMC0zLjE0bTguOTI4IDQuNzI5Yy0zLjU1NiAwLTYuMTMxIDIuNTUtNi4xMzEgNi4wOCAwIDEuNzE3LjYxMiAzLjI1IDEuNzA0IDQuMzYgMS4xMTIgMS4xMDggMi42NjcgMS43MTggNC40MDggMS43MTggMS40NDUgMCAyLjU1Ni0uMjc3IDQuNjY4LTEuODNsLTEuNDYzLTEuNTMzYy0xLjAzOC42ODQtMi4wMDEgMS4wMTYtMi45NDUgMS4wMTYtMi4xNDkgMC0zLjc2LTEuNjA3LTMuNzYtMy43MzJzMS42MTEtMy43MzIgMy43Ni0zLjczMmMxLjAxOCAwIDEuOTYzLjMzMyAyLjkwOCAxLjAxNmwxLjYyOS0xLjUzM2MtMS45MDctMS42MjYtMy42My0xLjgzLTQuNzc4LTEuODNtOS4xNDkgNi43NjJhLjIuMiAwIDAgMSAuMTQ5LS4wNTVoLjAxOGMuMDU2IDAgLjExMS4wMzcuMTY3LjA3M2w0LjA5MyA1LjA2M2gzLjE0OWwtNS4yOTctNi4zOTNjLS4wNzUtLjA5Mi0uMDc1LS4yMjIuMDE4LS4yOTVsNC44NzEtNC44NmgtMy4xM2wtNC4yMDQgNC4yMTNjLS4wNTYuMDU1LS4xNDguMDc0LS4yNDEuMDU1YS4yMy4yMyAwIDAgMS0uMTMtLjIwM1YxLjg3aC0yLjU3NHYxNi41OTFoMi41NTZ2LTQuNTA4YzAtLjA1NS4wMTgtLjEzLjA3NC0uMTY2eiIgZmlsbD0iI2ZmZiIvPjxwYXRoIGQ9Ik0xMjcuNzc2IDE4LjczOWMyLjA5MyAwIDQuMjIzLTEuMjc1IDQuMjIzLTMuNjk1IDAtMS41ODktMS0yLjY4LTMuMDM3LTMuMzQ0bC0xLjM5LS40NjJjLS45NDQtLjMxNC0xLjM4OS0uNzU4LTEuMzg5LTEuMzY3IDAtLjcwMi42My0xLjE4MyAxLjUxOS0xLjE4My44NTIgMCAxLjYxMS41NTUgMi4wOTMgMS41MTVsMi4wNTYtMS4xMDhjLS43NTktMS41NTItMi4zMzQtMi41MTMtNC4xNDktMi41MTMtMi4yOTcgMC0zLjk2MyAxLjQ3OC0zLjk2MyAzLjQ5MiAwIDEuNjA3Ljk2MyAyLjY3OSAyLjk0NCAzLjMwN2wxLjQyNy40NjJjMSAuMzE0IDEuNDI2LjcyIDEuNDI2IDEuMzY3IDAgLjk4LS45MDggMS4zMy0xLjY4NiAxLjMzLTEuMDM3IDAtMS45NjMtLjY2NS0yLjQwNy0xLjc1NWwtMi4wOTMgMS4xMDljLjY4NSAxLjc1NSAyLjM3IDIuODQ1IDQuNDI2IDIuODQ1bS02OS41NDYtLjExMWMuODE1IDAgMS41MzgtLjA3NCAxLjk0NS0uMTN2LTIuMjE2YTE0IDE0IDAgMCAxLTEuMjc4LjA3M2MtMS4wMzcgMC0xLjgzMy0uMTg0LTEuODMzLTIuNDJWOS4xODdjMC0uMTMuMDkyLS4yMjIuMjIyLS4yMjJoMi41VjYuODc3aC0yLjVhLjIxNC4yMTQgMCAwIDEtLjIyMi0uMjIxVjMuMzNoLTIuNTU2djMuMzQ0YzAgLjEzLS4wOTMuMjIyLS4yMjMuMjIyaC0xLjc3OHYyLjA4OGgxLjc3OGMuMTMgMCAuMjIzLjA5Mi4yMjMuMjIxdjUuMzc3YzAgNC4wNDYgMi43MDQgNC4wNDYgMy43MjIgNC4wNDYiIGZpbGw9IiNmZmYiLz48L3N2Zz4=" alt="Databricks" className="h-6" />
        </div>

        {/* Result card */}
        <div className={`animate-fade-in rounded-xl border px-10 py-8 text-center shadow-dbx max-w-md ${
          bridgeResult.ok
            ? 'border-dbx-green/20 bg-dbx-gray-900/80'
            : 'border-dbx-red/20 bg-dbx-gray-900/80'
        }`}>
          {bridgeResult.ok ? (
            <svg className="mx-auto mb-4 h-14 w-14 text-dbx-green" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" opacity="0.15" fill="currentColor" stroke="none"/>
              <circle cx="12" cy="12" r="10"/>
              <path d="M8 12l2.5 2.5L16 9"/>
            </svg>
          ) : (
            <svg className="mx-auto mb-4 h-14 w-14 text-dbx-red" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" opacity="0.15" fill="currentColor" stroke="none"/>
              <circle cx="12" cy="12" r="10"/>
              <path d="M15 9l-6 6M9 9l6 6"/>
            </svg>
          )}
          <div className={`text-xl font-bold mb-3 ${bridgeResult.ok ? 'text-dbx-green' : 'text-dbx-red'}`}>
            {bridgeResult.ok ? 'Connected' : 'Connection Failed'}
          </div>
          <div className="text-sm text-dbx-gray-400 font-mono">
            {bridgeResult.message}
          </div>
          {bridgeResult.ok && (
            <div className="text-xs text-dbx-gray-600 mt-4">
              You can close this tab. The Setup App will update automatically.
            </div>
          )}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center bg-dbx-menu dark:bg-dbx-gray-950">
        <div className="animate-fade-in rounded-lg border border-dbx-red-lt bg-dbx-red-bg dark:bg-dbx-red-bg-dk dark:border-dbx-gray-800 px-6 py-4 text-sm text-dbx-red dark:text-[#FF6B5A] shadow-dbx">
          Failed to load architecture graph: {error}
        </div>
      </div>
    )
  }

  return (
    <div className="relative h-full w-full overflow-hidden bg-dbx-menu dark:bg-dbx-gray-950">
      {/* Title bar */}
      <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-4 py-2
        bg-white/95 dark:bg-dbx-gray-950/95 backdrop-blur-md border-b border-dbx-gray-200 dark:border-dbx-gray-800">
        <div className="flex items-center gap-3">
          <svg className="h-5 w-5 flex-shrink-0" viewBox="0 0 32 32" fill="none">
            <path d="M16 3L29 10.5V21.5L16 29L3 21.5V10.5L16 3Z" fill="#FF3522" opacity="0.12"/>
            <path d="M16 3L29 10.5V21.5L16 29L3 21.5V10.5L16 3Z" stroke="#FF3522" strokeWidth="1.5"/>
            <path d="M16 8L24 12.5V19.5L16 24L8 19.5V12.5L16 8Z" fill="#FF3522" opacity="0.35"/>
            <path d="M16 12L21 14.75V19.25L16 22L11 19.25V14.75L16 12Z" fill="#FF3522"/>
          </svg>
          <span className="text-[16px] font-semibold text-dbx-gray-900 dark:text-dbx-gray-100 tracking-tight">Brick<span className="text-dbx-red">Forge</span></span>
          <span className="text-dbx-gray-200 dark:text-dbx-gray-700">|</span>
          <img src="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTMyIiBoZWlnaHQ9IjIyIiB2aWV3Qm94PSIwIDAgMTMyIDIyIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxwYXRoIGQ9Im0xOC4zMTggOS4yNzUtOC42MzEgNC44NTlMLjQ0NSA4Ljk0MiAwIDkuMTgydjMuNzdsOS42ODcgNS40MzEgOC42My00Ljg0djEuOTk1bC04LjYzIDQuODYtOS4yNDItNS4xOTItLjQ0NS4yNHYuNjQ2bDkuNjg3IDUuNDMyIDkuNjY4LTUuNDMydi0zLjc2OWwtLjQ0NS0uMjQtOS4yMjMgNS4xNzMtOC42NS00Ljg0VjEwLjQybDguNjUgNC44NCA5LjY2OC01LjQzVjYuMTE0bC0uNDgyLS4yNzctOS4xODYgNS4xNTVMMS40ODIgNi40MWw4LjIwNS00LjYgNi43NDEgMy43ODcuNTkzLS4zMzJ2LS40NjJMOS42ODcuNjg0IDAgNi4xMTV2LjU5Mmw5LjY4NyA1LjQzMiA4LjYzLTQuODZ6IiBmaWxsPSIjRUUzRDJDIi8+PHBhdGggZD0iTTM3LjQ0OSAxOC40NDNWMS44NTJoLTIuNTU2djYuMjA3YzAgLjA5My0uMDU2LjE2Ny0uMTQ4LjIwNGEuMjMuMjMgMCAwIDEtLjI0LS4wNTZjLS44NzEtMS4wMTYtMi4yMjMtMS41ODktMy43MDUtMS41ODktMy4xNjcgMC01LjY1IDIuNjYtNS42NSA2LjA2IDAgMS42NjMuNTc1IDMuMTk3IDEuNjMgNC4zMjRhNS40NCA1LjQ0IDAgMCAwIDQuMDIgMS43MzZjMS40NjMgMCAyLjgxNS0uNjEgMy43MDQtMS42NjIuMDU2LS4wNzQuMTY3LS4wOTMuMjQtLjA3NC4wOTMuMDM3LjE1LjExLjE1LjIwM3YxLjIzOHptLTYuMDkzLTIuMDE0Yy0yLjAzOCAwLTMuNjMtMS42NDQtMy42My0zLjc1IDAtMi4xMDcgMS41OTItMy43NTEgMy42My0zLjc1MXMzLjYzIDEuNjQ0IDMuNjMgMy43NS0xLjU5MyAzLjc1LTMuNjMgMy43NW0xOS43NjIgMi4wMTZWNi44OTZoLTIuNTM3VjguMDZjMCAuMDkzLS4wNTYuMTY2LS4xNDkuMjAzYS4yLjIgMCAwIDEtLjI0LS4wNzNjLS44NTItMS4wMTctMi4xODYtMS41OS0zLjcwNS0xLjU5LTMuMTY3IDAtNS42NDkgMi42NjEtNS42NDkgNi4wNiAwIDMuNCAyLjQ4MiA2LjA2IDUuNjUgNi4wNiAxLjQ2MyAwIDIuODE1LS42MSAzLjcwNC0xLjY4LjA1NS0uMDc1LjE2Ni0uMDkzLjI0LS4wNzUuMDkzLjAzNy4xNDkuMTExLjE0OS4yMDR2MS4yNTZoMi41Mzd6bS02LjA1Ni0yLjAxNGMtMi4wMzggMC0zLjYzLTEuNjQ1LTMuNjMtMy43NSAwLTIuMTA3IDEuNTkyLTMuNzUxIDMuNjMtMy43NTFzMy42MyAxLjY0NCAzLjYzIDMuNzUtMS41OTMgMy43NS0zLjYzIDMuNzVtMjcuNzgxIDIuMDE1VjYuODk2aC0yLjUzOFY4LjA2YzAgLjA5My0uMDU1LjE2Ni0uMTQ4LjIwM3MtLjE4NSAwLS4yNC0uMDczYy0uODUzLTEuMDE3LTIuMTg2LTEuNTktMy43MDUtMS41OS0zLjE4NiAwLTUuNjQ5IDIuNjYxLTUuNjQ5IDYuMDggMCAzLjQxNyAyLjQ4MiA2LjA2IDUuNjQ5IDYuMDYgMS40NjMgMCAyLjgxNS0uNjEgMy43MDQtMS42ODIuMDU2LS4wNzQuMTY3LS4wOTMuMjQxLS4wNzQuMDkzLjAzNy4xNDguMTEuMTQ4LjIwM3YxLjI1NnptLTYuMDU3LTIuMDE0Yy0yLjAzNyAwLTMuNjMtMS42NDUtMy42My0zLjc1IDAtMi4xMDcgMS41OTMtMy43NTEgMy42My0zLjc1MXMzLjYzIDEuNjQ0IDMuNjMgMy43NS0xLjU5MyAzLjc1LTMuNjMgMy43NW0xMC43MDYuNjQ3Yy4wMTkgMCAuMDU2LS4wMTkuMDc0LS4wMTkuMDU2IDAgLjEzLjAzNy4xNjcuMDc0Ljg3IDEuMDE2IDIuMjIyIDEuNTg5IDMuNzA0IDEuNTg5IDMuMTY3IDAgNS42NS0yLjY2IDUuNjUtNi4wNiAwLTEuNjYzLS41NzUtMy4xOTYtMS42My00LjMyM2E1LjQ0IDUuNDQgMCAwIDAtNC4wMi0xLjczN2MtMS40NjMgMC0yLjgxNS42MS0zLjcwNCAxLjY2My0uMDU2LjA3NC0uMTQ4LjA5Mi0uMjQuMDc0LS4wOTMtLjAzNy0uMTQ5LS4xMTEtLjE0OS0uMjA0VjEuODUyaC0yLjU1NnYxNi41OWgyLjU1NlYxNy4yOGMwLS4wOTMuMDU2LS4xNjYuMTQ4LS4yMDNtLS4yNi00LjM5OGMwLTIuMTA2IDEuNTk0LTMuNzUgMy42MzEtMy43NXMzLjYzIDEuNjQ0IDMuNjMgMy43NS0xLjU5MyAzLjc1LTMuNjMgMy43NS0zLjYzLTEuNjYyLTMuNjMtMy43NW0xNy4yNDQtMy40MTZjLjI0IDAgLjQ2My4wMTkuNjEuMDU2VjYuNjk1YTIuNCAyLjQgMCAwIDAtLjQyNS0uMDM3Yy0xLjMzNCAwLTIuNTU2LjY4NC0zLjIwNCAxLjc3NC0uMDU2LjA5Mi0uMTQ5LjEzLS4yNDEuMDkyYS4yMi4yMiAwIDAgMS0uMTY3LS4yMDNWNi44OThoLTIuNTM3djExLjU2NmgyLjU1NnYtNS4xYzAtMi41MyAxLjI5Ni00LjEgMy40MDgtNC4xbTQuODE1LTIuMzY3aC0yLjU5M3YxMS41NjZoMi41OTN6TTk3Ljk1OCAxLjg3YTEuNTcxIDEuNTcxIDAgMSAwIDAgMy4xNDEgMS41NzEgMS41NzEgMCAxIDAgMC0zLjE0bTguOTI4IDQuNzI5Yy0zLjU1NiAwLTYuMTMxIDIuNTUtNi4xMzEgNi4wOCAwIDEuNzE3LjYxMiAzLjI1IDEuNzA0IDQuMzYgMS4xMTIgMS4xMDggMi42NjcgMS43MTggNC40MDggMS43MTggMS40NDUgMCAyLjU1Ni0uMjc3IDQuNjY4LTEuODNsLTEuNDYzLTEuNTMzYy0xLjAzOC42ODQtMi4wMDEgMS4wMTYtMi45NDUgMS4wMTYtMi4xNDkgMC0zLjc2LTEuNjA3LTMuNzYtMy43MzJzMS42MTEtMy43MzIgMy43Ni0zLjczMmMxLjAxOCAwIDEuOTYzLjMzMyAyLjkwOCAxLjAxNmwxLjYyOS0xLjUzM2MtMS45MDctMS42MjYtMy42My0xLjgzLTQuNzc4LTEuODNtOS4xNDkgNi43NjJhLjIuMiAwIDAgMSAuMTQ5LS4wNTVoLjAxOGMuMDU2IDAgLjExMS4wMzcuMTY3LjA3M2w0LjA5MyA1LjA2M2gzLjE0OWwtNS4yOTctNi4zOTNjLS4wNzUtLjA5Mi0uMDc1LS4yMjIuMDE4LS4yOTVsNC44NzEtNC44NmgtMy4xM2wtNC4yMDQgNC4yMTNjLS4wNTYuMDU1LS4xNDguMDc0LS4yNDEuMDU1YS4yMy4yMyAwIDAgMS0uMTMtLjIwM1YxLjg3aC0yLjU3NHYxNi41OTFoMi41NTZ2LTQuNTA4YzAtLjA1NS4wMTgtLjEzLjA3NC0uMTY2eiIgZmlsbD0iIzAwMCIvPjxwYXRoIGQ9Ik0xMjcuNzc2IDE4LjczOWMyLjA5MyAwIDQuMjIzLTEuMjc1IDQuMjIzLTMuNjk1IDAtMS41ODktMS0yLjY4LTMuMDM3LTMuMzQ0bC0xLjM5LS40NjJjLS45NDQtLjMxNC0xLjM4OS0uNzU4LTEuMzg5LTEuMzY3IDAtLjcwMi42My0xLjE4MyAxLjUxOS0xLjE4My44NTIgMCAxLjYxMS41NTUgMi4wOTMgMS41MTVsMi4wNTYtMS4xMDhjLS43NTktMS41NTItMi4zMzQtMi41MTMtNC4xNDktMi41MTMtMi4yOTcgMC0zLjk2MyAxLjQ3OC0zLjk2MyAzLjQ5MiAwIDEuNjA3Ljk2MyAyLjY3OSAyLjk0NCAzLjMwN2wxLjQyNy40NjJjMSAuMzE0IDEuNDI2LjcyIDEuNDI2IDEuMzY3IDAgLjk4LS45MDggMS4zMy0xLjY4NiAxLjMzLTEuMDM3IDAtMS45NjMtLjY2NS0yLjQwNy0xLjc1NWwtMi4wOTMgMS4xMDljLjY4NSAxLjc1NSAyLjM3IDIuODQ1IDQuNDI2IDIuODQ1bS02OS41NDYtLjExMWMuODE1IDAgMS41MzgtLjA3NCAxLjk0NS0uMTN2LTIuMjE2YTE0IDE0IDAgMCAxLTEuMjc4LjA3M2MtMS4wMzcgMC0xLjgzMy0uMTg0LTEuODMzLTIuNDJWOS4xODdjMC0uMTMuMDkyLS4yMjIuMjIyLS4yMjJoMi41VjYuODc3aC0yLjVhLjIxNC4yMTQgMCAwIDEtLjIyMi0uMjIxVjMuMzNoLTIuNTU2djMuMzQ0YzAgLjEzLS4wOTMuMjIyLS4yMjMuMjIyaC0xLjc3OHYyLjA4OGgxLjc3OGMuMTMgMCAuMjIzLjA5Mi4yMjMuMjIxdjUuMzc3YzAgNC4wNDYgMi43MDQgNC4wNDYgMy43MjIgNC4wNDYiIGZpbGw9IiMwMDAiLz48L3N2Zz4=" alt="Databricks" className="h-3.5 dark:hidden" />
          <img src="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTMyIiBoZWlnaHQ9IjIyIiB2aWV3Qm94PSIwIDAgMTMyIDIyIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxwYXRoIGQ9Im0xOC4zMTggOS4yNzUtOC42MzEgNC44NTlMLjQ0NSA4Ljk0MiAwIDkuMTgydjMuNzdsOS42ODcgNS40MzEgOC42My00Ljg0djEuOTk1bC04LjYzIDQuODYtOS4yNDItNS4xOTItLjQ0NS4yNHYuNjQ2bDkuNjg3IDUuNDMyIDkuNjY4LTUuNDMydi0zLjc2OWwtLjQ0NS0uMjQtOS4yMjMgNS4xNzMtOC42NS00Ljg0VjEwLjQybDguNjUgNC44NCA5LjY2OC01LjQzVjYuMTE0bC0uNDgyLS4yNzctOS4xODYgNS4xNTVMMS40ODIgNi40MWw4LjIwNS00LjYgNi43NDEgMy43ODcuNTkzLS4zMzJ2LS40NjJMOS42ODcuNjg0IDAgNi4xMTV2LjU5Mmw5LjY4NyA1LjQzMiA4LjYzLTQuODZ6IiBmaWxsPSIjRUUzRDJDIi8+PHBhdGggZD0iTTM3LjQ0OSAxOC40NDNWMS44NTJoLTIuNTU2djYuMjA3YzAgLjA5My0uMDU2LjE2Ny0uMTQ4LjIwNGEuMjMuMjMgMCAwIDEtLjI0LS4wNTZjLS44NzEtMS4wMTYtMi4yMjMtMS41ODktMy43MDUtMS41ODktMy4xNjcgMC01LjY1IDIuNjYtNS42NSA2LjA2IDAgMS42NjMuNTc1IDMuMTk3IDEuNjMgNC4zMjRhNS40NCA1LjQ0IDAgMCAwIDQuMDIgMS43MzZjMS40NjMgMCAyLjgxNS0uNjEgMy43MDQtMS42NjIuMDU2LS4wNzQuMTY3LS4wOTMuMjQtLjA3NC4wOTMuMDM3LjE1LjExLjE1LjIwM3YxLjIzOHptLTYuMDkzLTIuMDE0Yy0yLjAzOCAwLTMuNjMtMS42NDQtMy42My0zLjc1IDAtMi4xMDcgMS41OTItMy43NTEgMy42My0zLjc1MXMzLjYzIDEuNjQ0IDMuNjMgMy43NS0xLjU5MyAzLjc1LTMuNjMgMy43NW0xOS43NjIgMi4wMTZWNi44OTZoLTIuNTM3VjguMDZjMCAuMDkzLS4wNTYuMTY2LS4xNDkuMjAzYS4yLjIgMCAwIDEtLjI0LS4wNzNjLS44NTItMS4wMTctMi4xODYtMS41OS0zLjcwNS0xLjU5LTMuMTY3IDAtNS42NDkgMi42NjEtNS42NDkgNi4wNiAwIDMuNCAyLjQ4MiA2LjA2IDUuNjUgNi4wNiAxLjQ2MyAwIDIuODE1LS42MSAzLjcwNC0xLjY4LjA1NS0uMDc1LjE2Ni0uMDkzLjI0LS4wNzUuMDkzLjAzNy4xNDkuMTExLjE0OS4yMDR2MS4yNTZoMi41Mzd6bS02LjA1Ni0yLjAxNGMtMi4wMzggMC0zLjYzLTEuNjQ1LTMuNjMtMy43NSAwLTIuMTA3IDEuNTkyLTMuNzUxIDMuNjMtMy43NTFzMy42MyAxLjY0NCAzLjYzIDMuNzUtMS41OTMgMy43NS0zLjYzIDMuNzVtMjcuNzgxIDIuMDE1VjYuODk2aC0yLjUzOFY4LjA2YzAgLjA5My0uMDU1LjE2Ni0uMTQ4LjIwM3MtLjE4NSAwLS4yNC0uMDczYy0uODUzLTEuMDE3LTIuMTg2LTEuNTktMy43MDUtMS41OS0zLjE4NiAwLTUuNjQ5IDIuNjYxLTUuNjQ5IDYuMDggMCAzLjQxNyAyLjQ4MiA2LjA2IDUuNjQ5IDYuMDYgMS40NjMgMCAyLjgxNS0uNjEgMy43MDQtMS42ODIuMDU2LS4wNzQuMTY3LS4wOTMuMjQxLS4wNzQuMDkzLjAzNy4xNDguMTEuMTQ4LjIwM3YxLjI1NnptLTYuMDU3LTIuMDE0Yy0yLjAzNyAwLTMuNjMtMS42NDUtMy42My0zLjc1IDAtMi4xMDcgMS41OTMtMy43NTEgMy42My0zLjc1MXMzLjYzIDEuNjQ0IDMuNjMgMy43NS0xLjU5MyAzLjc1LTMuNjMgMy43NW0xMC43MDYuNjQ3Yy4wMTkgMCAuMDU2LS4wMTkuMDc0LS4wMTkuMDU2IDAgLjEzLjAzNy4xNjcuMDc0Ljg3IDEuMDE2IDIuMjIyIDEuNTg5IDMuNzA0IDEuNTg5IDMuMTY3IDAgNS42NS0yLjY2IDUuNjUtNi4wNiAwLTEuNjYzLS41NzUtMy4xOTYtMS42My00LjMyM2E1LjQ0IDUuNDQgMCAwIDAtNC4wMi0xLjczN2MtMS40NjMgMC0yLjgxNS42MS0zLjcwNCAxLjY2My0uMDU2LjA3NC0uMTQ4LjA5Mi0uMjQuMDc0LS4wOTMtLjAzNy0uMTQ5LS4xMTEtLjE0OS0uMjA0VjEuODUyaC0yLjU1NnYxNi41OWgyLjU1NlYxNy4yOGMwLS4wOTMuMDU2LS4xNjYuMTQ4LS4yMDNtLS4yNi00LjM5OGMwLTIuMTA2IDEuNTk0LTMuNzUgMy42MzEtMy43NXMzLjYzIDEuNjQ0IDMuNjMgMy43NS0xLjU5MyAzLjc1LTMuNjMgMy43NS0zLjYzLTEuNjYyLTMuNjMtMy43NW0xNy4yNDQtMy40MTZjLjI0IDAgLjQ2My4wMTkuNjEuMDU2VjYuNjk1YTIuNCAyLjQgMCAwIDAtLjQyNS0uMDM3Yy0xLjMzNCAwLTIuNTU2LjY4NC0zLjIwNCAxLjc3NC0uMDU2LjA5Mi0uMTQ5LjEzLS4yNDEuMDkyYS4yMi4yMiAwIDAgMS0uMTY3LS4yMDNWNi44OThoLTIuNTM3djExLjU2NmgyLjU1NnYtNS4xYzAtMi41MyAxLjI5Ni00LjEgMy40MDgtNC4xbTQuODE1LTIuMzY3aC0yLjU5M3YxMS41NjZoMi41OTN6TTk3Ljk1OCAxLjg3YTEuNTcxIDEuNTcxIDAgMSAwIDAgMy4xNDEgMS41NzEgMS41NzEgMCAxIDAgMC0zLjE0bTguOTI4IDQuNzI5Yy0zLjU1NiAwLTYuMTMxIDIuNTUtNi4xMzEgNi4wOCAwIDEuNzE3LjYxMiAzLjI1IDEuNzA0IDQuMzYgMS4xMTIgMS4xMDggMi42NjcgMS43MTggNC40MDggMS43MTggMS40NDUgMCAyLjU1Ni0uMjc3IDQuNjY4LTEuODNsLTEuNDYzLTEuNTMzYy0xLjAzOC42ODQtMi4wMDEgMS4wMTYtMi45NDUgMS4wMTYtMi4xNDkgMC0zLjc2LTEuNjA3LTMuNzYtMy43MzJzMS42MTEtMy43MzIgMy43Ni0zLjczMmMxLjAxOCAwIDEuOTYzLjMzMyAyLjkwOCAxLjAxNmwxLjYyOS0xLjUzM2MtMS45MDctMS42MjYtMy42My0xLjgzLTQuNzc4LTEuODNtOS4xNDkgNi43NjJhLjIuMiAwIDAgMSAuMTQ5LS4wNTVoLjAxOGMuMDU2IDAgLjExMS4wMzcuMTY3LjA3M2w0LjA5MyA1LjA2M2gzLjE0OWwtNS4yOTctNi4zOTNjLS4wNzUtLjA5Mi0uMDc1LS4yMjIuMDE4LS4yOTVsNC44NzEtNC44NmgtMy4xM2wtNC4yMDQgNC4yMTNjLS4wNTYuMDU1LS4xNDguMDc0LS4yNDEuMDU1YS4yMy4yMyAwIDAgMS0uMTMtLjIwM1YxLjg3aC0yLjU3NHYxNi41OTFoMi41NTZ2LTQuNTA4YzAtLjA1NS4wMTgtLjEzLjA3NC0uMTY2eiIgZmlsbD0iI2ZmZiIvPjxwYXRoIGQ9Ik0xMjcuNzc2IDE4LjczOWMyLjA5MyAwIDQuMjIzLTEuMjc1IDQuMjIzLTMuNjk1IDAtMS41ODktMS0yLjY4LTMuMDM3LTMuMzQ0bC0xLjM5LS40NjJjLS45NDQtLjMxNC0xLjM4OS0uNzU4LTEuMzg5LTEuMzY3IDAtLjcwMi42My0xLjE4MyAxLjUxOS0xLjE4My44NTIgMCAxLjYxMS41NTUgMi4wOTMgMS41MTVsMi4wNTYtMS4xMDhjLS43NTktMS41NTItMi4zMzQtMi41MTMtNC4xNDktMi41MTMtMi4yOTcgMC0zLjk2MyAxLjQ3OC0zLjk2MyAzLjQ5MiAwIDEuNjA3Ljk2MyAyLjY3OSAyLjk0NCAzLjMwN2wxLjQyNy40NjJjMSAuMzE0IDEuNDI2LjcyIDEuNDI2IDEuMzY3IDAgLjk4LS45MDggMS4zMy0xLjY4NiAxLjMzLTEuMDM3IDAtMS45NjMtLjY2NS0yLjQwNy0xLjc1NWwtMi4wOTMgMS4xMDljLjY4NSAxLjc1NSAyLjM3IDIuODQ1IDQuNDI2IDIuODQ1bS02OS41NDYtLjExMWMuODE1IDAgMS41MzgtLjA3NCAxLjk0NS0uMTN2LTIuMjE2YTE0IDE0IDAgMCAxLTEuMjc4LjA3M2MtMS4wMzcgMC0xLjgzMy0uMTg0LTEuODMzLTIuNDJWOS4xODdjMC0uMTMuMDkyLS4yMjIuMjIyLS4yMjJoMi41VjYuODc3aC0yLjVhLjIxNC4yMTQgMCAwIDEtLjIyMi0uMjIxVjMuMzNoLTIuNTU2djMuMzQ0YzAgLjEzLS4wOTMuMjIyLS4yMjMuMjIyaC0xLjc3OHYyLjA4OGgxLjc3OGMuMTMgMCAuMjIzLjA5Mi4yMjMuMjIxdjUuMzc3YzAgNC4wNDYgMi43MDQgNC4wNDYgMy43MjIgNC4wNDYiIGZpbGw9IiNmZmYiLz48L3N2Zz4=" alt="Databricks" className="h-3.5 hidden dark:block" />
          {/* Project selector */}
          <div className="relative">
            <button
              onClick={() => setProjectMenuOpen(o => !o)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-150
                ${projectMenuOpen
                  ? 'bg-dbx-blue/10 dark:bg-dbx-blue/20 text-dbx-blue shadow-sm'
                  : 'text-dbx-gray-500 dark:text-dbx-gray-400 hover:bg-dbx-gray-100 dark:hover:bg-dbx-gray-800 hover:text-dbx-gray-700 dark:hover:text-dbx-gray-200'}`}
              title="Switch project"
            >
              <FolderOpen className="h-3.5 w-3.5" />
              {currentProject || 'projects'}
            </button>

            {projectMenuOpen && (
              <div className="absolute top-full left-0 mt-1 w-64 bg-white dark:bg-dbx-gray-900 border border-dbx-gray-200 dark:border-dbx-gray-700 rounded-lg shadow-lg z-50 py-1">
                {/* Project list */}
                {projects.length > 0 ? (
                  projects.map(p => (
                    <ProjectMenuItem
                      key={p.name}
                      project={p}
                      isCurrentProject={currentProject === p.name}
                      onLoad={() => loadProject(p.name)}
                      onRename={(newName) => {
                        fetch(`/api/projects/${p.name}`, {
                          method: 'PATCH',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ name: newName }),
                        })
                          .then(async r => {
                            const d = await r.json()
                            if (!r.ok) { alert(d.error || 'Rename failed'); return }
                            if (currentProject === p.name) setCurrentProject(d.name)
                            refreshProjects()
                          })
                          .catch(e => alert(e.message))
                      }}
                      onDelete={() => deleteProject(p.name)}
                    />
                  ))
                ) : (
                  <div className="px-3 py-2 text-[11px] text-dbx-gray-400 dark:text-dbx-gray-500">
                    No saved projects
                  </div>
                )}

                {/* Divider */}
                <div className="border-t border-dbx-gray-200 dark:border-dbx-gray-700 my-1" />

                {/* New project */}
                {showNewProject ? (
                  <div className="px-3 py-1.5 flex items-center gap-2" onClick={e => e.stopPropagation()}>
                    <input
                      type="text"
                      value={newProjectName}
                      onChange={e => setNewProjectName(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && createProject()}
                      placeholder="project name"
                      className="flex-1 text-xs font-mono px-2 py-1 rounded border border-dbx-gray-200 dark:border-dbx-gray-700 bg-white dark:bg-dbx-gray-800 text-dbx-gray-800 dark:text-dbx-gray-200 outline-none focus:border-dbx-blue"
                      autoFocus
                    />
                    <button
                      onClick={createProject}
                      className="text-xs text-dbx-blue hover:text-dbx-blue/80 font-medium"
                    >
                      Create
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={e => { e.stopPropagation(); setShowNewProject(true) }}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-dbx-gray-500 dark:text-dbx-gray-400 hover:bg-dbx-gray-50 dark:hover:bg-dbx-gray-800 hover:text-dbx-blue"
                  >
                    <Plus className="h-3 w-3" />
                    New project
                  </button>
                )}

                {/* Import bundle */}
                <label
                  onClick={e => e.stopPropagation()}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-dbx-gray-500 dark:text-dbx-gray-400 hover:bg-dbx-gray-50 dark:hover:bg-dbx-gray-800 hover:text-dbx-blue cursor-pointer"
                >
                  <Upload className="h-3 w-3" />
                  Import project
                  <input type="file" accept=".zip" className="hidden" ref={importInputRef}
                    onChange={e => {
                      const f = e.target.files?.[0];
                      if (!f) return;
                      setImportFile(f);
                      setImportError('');
                      setProjectMenuOpen(false);
                    }}
                  />
                </label>

              </div>
            )}
          </div>

          <span className="text-dbx-gray-200 dark:text-dbx-gray-700">|</span>

          {/* View tabs */}
          <div className="flex items-center gap-0.5 bg-dbx-gray-100 dark:bg-dbx-gray-800 rounded-lg p-0.5">
            {([
              ['mage', 'Mage'],
              ['setup', 'Setup'],
              ['data', 'Data'],
              ['stash', 'Assets'],
              ['ka', 'Docs'],
              ['arch', 'Architecture'],
              ['cleanup', 'Cleanup'],
            ] as [View, string][]).map(([v, label]) => (
              <button
                key={v}
                onClick={() => switchView(v)}
                className={`text-xs px-3 py-1.5 rounded-md font-medium transition-all duration-150 ${
                  view === v
                    ? 'bg-white dark:bg-dbx-gray-700 text-dbx-gray-900 dark:text-dbx-gray-100 shadow-sm'
                    : 'text-dbx-gray-400 dark:text-dbx-gray-500 hover:text-dbx-gray-700 dark:hover:text-dbx-gray-300'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {graph && (
            <span className="text-[10px] text-dbx-gray-400 dark:text-dbx-gray-500 font-mono">
              {graph.meta.projectRoot.split('/').slice(-1)[0]}
            </span>
          )}
          <button
            onClick={() => setDark(d => !d)}
            className="p-1.5 rounded-md text-dbx-gray-400 dark:text-dbx-gray-500 hover:bg-dbx-gray-100 dark:hover:bg-dbx-gray-800 hover:text-dbx-gray-600 dark:hover:text-dbx-gray-300 transition-all duration-150"
            title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={envOpen ? closeEnv : openEnv}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-150
              ${envOpen
                ? 'bg-dbx-red-bg dark:bg-dbx-red-bg-dk text-dbx-red dark:text-[#FF6B5A] shadow-dbx'
                : 'text-dbx-gray-500 dark:text-dbx-gray-400 hover:bg-dbx-gray-100 dark:hover:bg-dbx-gray-800 hover:text-dbx-gray-700 dark:hover:text-dbx-gray-200'}`}
          >
            <Settings2 className="h-3.5 w-3.5" />
            .env
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="h-full w-full pt-9">
        {view === 'arch' ? (
          <div className="relative h-full">
            {/* Refresh button */}
            <button
              onClick={() => loadGraph(true)}
              disabled={graphLoading}
              className="absolute top-2 right-3 z-20 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium
                bg-white dark:bg-dbx-gray-800 border border-dbx-gray-200 dark:border-dbx-gray-700
                text-dbx-gray-600 dark:text-dbx-gray-300
                hover:bg-dbx-gray-50 dark:hover:bg-dbx-gray-700 hover:text-dbx-gray-900 dark:hover:text-dbx-gray-100
                shadow-sm transition-all duration-150 disabled:opacity-50"
              title="Reload architecture from current config"
            >
              <RefreshCw className={`h-3 w-3 ${graphLoading ? 'animate-spin' : ''}`} />
              {graphLoading ? 'Loading…' : 'Refresh'}
            </button>
            {!graph && !graphLoading ? (
              <div className="flex h-full items-center justify-center">
                <div className="text-sm text-dbx-gray-400 dark:text-dbx-gray-500 animate-pulse">Loading architecture…</div>
              </div>
            ) : graph ? (
              <ReactFlowProvider>
                <ArchCanvas
                  nodes={graph.nodes as Node<ArchNodeData>[]}
                  edges={graph.edges}
                  onNodeClick={onNodeClick}
                />
                <Legend />
              </ReactFlowProvider>
            ) : null}
          </div>
        ) : view === 'mage' ? (
          <MageView />
        ) : view === 'setup' ? (
          <SetupView />
        ) : view === 'data' ? (
          <DataView />
        ) : view === 'ka' ? (
          <KaDocsView />
        ) : view === 'stash' ? (
          <StashHealthView />
        ) : (
          <CleanupView />
        )}
      </div>

      {view === 'arch' && <NodeDetailPanel node={selected} onClose={closePanel} />}
      <EnvEditor open={envOpen} onClose={closeEnv} />

      {/* Import modal -- at root level to avoid stacking context issues */}
      {importFile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={() => { setImportFile(null); setImportError(''); if (importInputRef.current) importInputRef.current.value = '' }}>
          <div className="absolute inset-0 bg-black/40 dark:bg-black/60 backdrop-blur-[2px]" />
          <div onClick={e => e.stopPropagation()} className="relative w-[380px] bg-white dark:bg-dbx-gray-900 border border-dbx-gray-200 dark:border-dbx-gray-700 rounded-xl shadow-2xl p-6">
            <h3 className="text-[14px] font-semibold text-dbx-gray-900 dark:text-dbx-gray-100 font-mono mb-1">Import project</h3>
            <p className="text-[12px] font-mono text-dbx-gray-500 dark:text-dbx-gray-400 mb-4">{importFile.name}</p>

            <button
              onClick={() => doImport('load')}
              disabled={importLoading}
              className="w-full text-left mb-2 p-3 rounded-lg border border-dbx-gray-200 dark:border-dbx-gray-700 hover:border-dbx-blue dark:hover:border-dbx-blue transition-colors disabled:opacity-50"
            >
              <div className="flex items-center justify-between">
                <span className="text-[13px] font-mono font-medium text-dbx-gray-800 dark:text-dbx-gray-200">Load project</span>
                <Info className="h-3.5 w-3.5 text-dbx-gray-300 dark:text-dbx-gray-600 cursor-help flex-shrink-0" title="Imports the bundle config as-is. Use this when the catalog, tables, functions and other assets referenced in this bundle already exist on your workspace." />
              </div>
              <span className="text-[11px] font-mono text-dbx-gray-400 dark:text-dbx-gray-500">Import from bundle</span>
            </button>

            <button
              onClick={() => doImport('new')}
              disabled={importLoading}
              className="w-full text-left mb-3 p-3 rounded-lg border border-dbx-gray-200 dark:border-dbx-gray-700 hover:border-dbx-blue dark:hover:border-dbx-blue transition-colors disabled:opacity-50"
            >
              <div className="flex items-center justify-between">
                <span className="text-[13px] font-mono font-medium text-dbx-gray-800 dark:text-dbx-gray-200">New project</span>
                <Info className="h-3.5 w-3.5 text-dbx-gray-300 dark:text-dbx-gray-600 cursor-help flex-shrink-0" title="Imports data, prompts and SQL from the bundle but clears workspace connections. You'll walk through setup to connect or create assets on your workspace." />
              </div>
              <span className="text-[11px] font-mono text-dbx-gray-400 dark:text-dbx-gray-500">Create from bundle</span>
            </button>

            {importError && (
              <p className="text-[11px] font-mono text-red-500 mb-3">{importError}</p>
            )}

            {importLoading ? (
              <p className="text-[11px] font-mono text-dbx-gray-400 animate-pulse text-center">Importing...</p>
            ) : (
              <button
                onClick={() => { setImportFile(null); setImportError(''); if (importInputRef.current) importInputRef.current.value = '' }}
                className="w-full text-center text-[12px] font-mono text-dbx-gray-400 hover:text-dbx-gray-600 dark:hover:text-dbx-gray-300"
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
