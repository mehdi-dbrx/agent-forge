import { cn } from '@/lib/utils';
import { domainToolMessages } from '@/domain';

const STATUS_PHRASES = ['Thinking…', 'Analysing…', 'Almost there…'];

/** Tool name -> friendly loading message. Domain-specific messages loaded from domain plugin. */
const TOOL_MESSAGES: Record<string, string> = {
  ...domainToolMessages,
};

const ACTIVE_TOOL_STATES = new Set([
  'input-streaming',
  'input-available',
  'output-available',
  'output-streaming',
  'approval-requested',
  'approval-responded',
]);

type ToolPart = {
  type?: string;
  toolName?: string;
  state?: string;
  callProviderMetadata?: { databricks?: { toolName?: string } };
};

function normalizeToolName(part: ToolPart): string {
  let raw = part.toolName ?? '';
  // Databricks wraps tools: use providerMetadata.databricks.toolName for actual tool
  const metaName = part.callProviderMetadata?.databricks?.toolName;
  if (metaName) raw = metaName;
  return String(raw).replace(/-/g, '_').toLowerCase();
}

function isToolPart(p: ToolPart): boolean {
  return p.type === 'dynamic-tool' || p.type === 'tool-call';
}

function isActiveToolPart(p: ToolPart): boolean {
  if (!isToolPart(p)) return false;
  // Include if state is active, or if state is missing (stream may not have set it yet)
  if (p.state == null || p.state === '') return true;
  return ACTIVE_TOOL_STATES.has(p.state);
}

function formatToolLabel(name: string): string {
  const known = TOOL_MESSAGES[name];
  if (known) return known;
  // Fallback: humanize tool name (e.g. query_some_data → "Running query some data")
  const readable = name
    .replace(/^query_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
  return `Running ${readable}`;
}

/** Get friendly loading message for a tool name (for use in Tool header, etc.) */
export function getToolMessage(toolName: string): string {
  const name = String(toolName ?? '').replace(/-/g, '_').toLowerCase();
  if (!name) return '';
  return formatToolLabel(name);
}

export function getActiveToolMessage(
  message: { parts?: Array<ToolPart> } | null
): string | null {
  if (!message?.parts) return null;
  // Prefer the last active tool part (most recently called)
  const toolParts = message.parts.filter(isActiveToolPart);
  const toolPart = toolParts.length > 0 ? toolParts[toolParts.length - 1]! : null;
  if (!toolPart) return null;
  const name = normalizeToolName(toolPart);
  if (!name) return null;
  return formatToolLabel(name);
}

export function ChatLoadingIndicator({
  activeToolMessage,
  className,
}: {
  activeToolMessage?: string | null;
  className?: string;
}) {
  return (
    <div className={cn('flex items-center gap-2 text-muted-foreground text-sm', className)}>
      <div className="flex gap-1" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className="chat-loading-dot size-1.5 rounded-full bg-current" />
        ))}
      </div>
      <div className="relative h-5 min-w-[120px] overflow-hidden">
        {activeToolMessage ? (
          <span className="chat-loading-status absolute inset-0 flex items-center">
            {activeToolMessage}
          </span>
        ) : (
          <>
            <span className="chat-loading-status chat-status-phrase-1 absolute inset-0 flex items-center">
              {STATUS_PHRASES[0]}
            </span>
            <span className="chat-loading-status chat-status-phrase-2 absolute inset-0 flex items-center">
              {STATUS_PHRASES[1]}
            </span>
            <span className="chat-loading-status chat-status-phrase-3 absolute inset-0 flex items-center">
              {STATUS_PHRASES[2]}
            </span>
          </>
        )}
      </div>
    </div>
  );
}
