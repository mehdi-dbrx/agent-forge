import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  type Node,
  type Edge,
  type NodeMouseHandler,
  type OnNodeDrag,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useCallback, useRef } from 'react'
import { nodeTypes } from '../nodeTypes'
import type { ArchNodeData } from '../types'

interface ArchCanvasProps {
  nodes: Node<ArchNodeData>[]
  edges: Edge[]
  onNodeClick: NodeMouseHandler<Node<ArchNodeData>>
}

const defaultEdgeOptions = {
  type: 'smoothstep' as const,
  style: { stroke: '#a1a1aa', strokeWidth: 1.5 },
  labelStyle: { fontSize: 10, fill: '#71717a' },
  labelBgStyle: { fill: '#f4f4f5', fillOpacity: 0.85 },
  labelBgPadding: [4, 2] as [number, number],
  labelBgBorderRadius: 3,
}

function saveLayout(nodes: Node<ArchNodeData>[]) {
  const positions: Record<string, { x: number; y: number }> = {}
  for (const n of nodes) positions[n.id] = n.position
  fetch('/api/layout', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(positions),
  }).catch((e: unknown) => console.warn('[layout] save failed:', e))
}

export function ArchCanvas({ nodes: initialNodes, edges, onNodeClick }: ArchCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setNodes(initialNodes)
  }, [initialNodes, setNodes])

  const onNodeDragStop: OnNodeDrag = useCallback(() => {
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      setNodes((current) => { saveLayout(current); return current })
    }, 300)
  }, [setNodes])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      nodeTypes={nodeTypes}
      onNodeClick={onNodeClick}
      defaultEdgeOptions={defaultEdgeOptions}
      onNodeDragStop={onNodeDragStop}
      nodesConnectable={false}
      elementsSelectable={true}
      fitView
      fitViewOptions={{ padding: 0.15 }}
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#e4e4e7" gap={20} />
      <Controls showInteractive={false} />
      <MiniMap
        nodeColor={(node) => {
          const kind = (node.data as ArchNodeData).kind
          const colors: Record<string, string> = {
            agent: '#93c5fd',
            llm:   '#c4b5fd',
            tool:  '#fcd34d',
            genie: '#fda4af',
            data:  '#5eead4',
          }
          return colors[kind] ?? '#d4d4d8'
        }}
        maskColor="rgba(244,244,245,0.6)"
      />
    </ReactFlow>
  )
}
