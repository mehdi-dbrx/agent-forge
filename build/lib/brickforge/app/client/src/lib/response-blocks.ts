/**
 * Parses assistant message text for structured response blocks.
 * Framework blocks: refresh_table, knowledge_base.
 * Any unrecognised block type is emitted as a generic 'domain_block' segment
 * so the domain plugin registry can render it.
 * Block format: ```blockType\ncontent\n```
 */

// biome-ignore lint/suspicious/noExplicitAny: domain blocks have varied parsed shapes
export type ResponseSegment =
  | { type: 'markdown'; content: string }
  | { type: 'refresh_table'; content: string; parsed: { table: string } }
  | { type: 'knowledge_base'; content: string; parsed: { header: string; items: string[]; footer?: string } }
  | { type: string; content: string; parsed: any };

const FENCE = '```';

function parseRefreshTable(inner: string): { table: string } {
  const table = inner.trim().split(/\r?\n/)[0]?.trim() ?? '';
  return { table };
}

function parseKnowledgeBase(inner: string): {
  header: string;
  items: string[];
  footer?: string;
} {
  const lines = inner.trim().split(/\r?\n/).map((l) => l.trim());
  const headerLines: string[] = [];
  const items: string[] = [];
  let footer = '';
  let phase: 'header' | 'items' | 'footer' = 'header';

  for (const line of lines) {
    if (line === '---') {
      phase = 'footer';
      continue;
    }
    if (phase === 'header') {
      if (line.startsWith('- ')) {
        phase = 'items';
        items.push(line.slice(2).trim());
      } else {
        headerLines.push(line);
      }
      continue;
    }
    if (phase === 'items') {
      if (line.startsWith('- ')) {
        items.push(line.slice(2).trim());
      } else if (line === '---') {
        phase = 'footer';
      } else if (line) {
        items.push(line);
      }
      continue;
    }
    if (phase === 'footer' && line) {
      footer += (footer ? '\n' : '') + line;
    }
  }

  return {
    header: headerLines.join(' ').trim(),
    items,
    footer: footer.trim() || undefined,
  };
}

/**
 * Generic parser for domain blocks: splits inner content into lines,
 * attempts pipe-delimited key-value extraction, falls back to raw content.
 */
function parseDomainBlock(inner: string): Record<string, unknown> {
  const lines = inner.trim().split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  // If single line with pipes, treat as delimited fields
  if (lines.length === 1 && lines[0].includes('|')) {
    const parts = lines[0].split('|').map((p) => p.trim());
    return { parts, raw: inner };
  }
  return { lines, raw: inner };
}

/**
 * Splits message text into segments: markdown and structured blocks.
 * Framework blocks (refresh_table, knowledge_base) get dedicated parsers.
 * All other blocks are emitted as their block type with generic parsing,
 * allowing the domain plugin registry to render them.
 */
export function parseResponseBlocks(text: string): ResponseSegment[] {
  const segments: ResponseSegment[] = [];
  let remaining = text;

  while (remaining.length > 0) {
    const open = remaining.indexOf(FENCE);
    if (open < 0) {
      if (remaining.trim()) segments.push({ type: 'markdown', content: remaining });
      break;
    }

    const before = remaining.slice(0, open);
    if (before.trim()) segments.push({ type: 'markdown', content: before });
    remaining = remaining.slice(open + FENCE.length);
    const afterFence = remaining.replace(/^\s+/, '');
    const newline = afterFence.indexOf('\n');
    const lang =
      newline >= 0
        ? afterFence.slice(0, newline).trim().toLowerCase()
        : afterFence.trim().toLowerCase();
    const contentStart =
      remaining.length - afterFence.length + (newline >= 0 ? newline + 1 : afterFence.length);
    const closeIdx = remaining.indexOf(FENCE, contentStart);
    if (closeIdx < 0) {
      segments.push({ type: 'markdown', content: FENCE + remaining });
      break;
    }

    const inner = remaining.slice(contentStart, closeIdx);
    remaining = remaining.slice(closeIdx + FENCE.length);

    try {
      if (lang === 'refresh_table') {
        segments.push({ type: 'refresh_table', content: inner, parsed: parseRefreshTable(inner) });
      } else if (lang === 'knowledge_base') {
        segments.push({ type: 'knowledge_base', content: inner, parsed: parseKnowledgeBase(inner) });
      } else if (lang === 'chart') {
        // Chart block -- parse JSON content for chart rendering
        try {
          const chartData = JSON.parse(inner.trim());
          segments.push({ type: 'chart', content: inner, parsed: chartData });
        } catch {
          segments.push({ type: 'markdown', content: FENCE + lang + '\n' + inner + FENCE });
        }
      } else if (lang && !['json', 'python', 'sql', 'bash', 'typescript', 'javascript', 'yaml', 'xml', 'html', 'css', 'markdown', 'text', 'sh', 'py', 'ts', 'js'].includes(lang)) {
        // Domain block -- emit with generic parsing, let domain plugin handle rendering
        segments.push({ type: lang, content: inner, parsed: parseDomainBlock(inner) });
      } else {
        // Standard code fence -- render as markdown
        segments.push({ type: 'markdown', content: FENCE + lang + (newline >= 0 ? '\n' + inner : '') + FENCE });
      }
    } catch {
      segments.push({ type: 'markdown', content: FENCE + lang + '\n' + inner + FENCE });
    }
  }

  return segments;
}

export function hasResponseBlocks(text: string): boolean {
  return parseResponseBlocks(text).some((s) => s.type !== 'markdown');
}
