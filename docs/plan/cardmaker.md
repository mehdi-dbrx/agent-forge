# CardMaker - Dynamic Card Renderer

> Status: IMPLEMENTING — agent chat done, Mage chat + selector next
> Created: 2026-06-17

## Context

Cards render in BOTH chat UIs:
- **Deployed agent chat**: tool results (search → list card, action → confirmation card)
- **Mage chat**: feature/brick selector during discovery, spec summary, progress

Generic renderer — one component per app, any domain, any card type.

## Card Types

| Type | Color | Layout | Use case |
|------|-------|--------|----------|
| confirmation | Green | Key-value | Action completed |
| info | Blue | Key-value | Details, profiles |
| list | Neutral | Table | Search results, history |
| error | Red | Key-value | Failed operations |
| warning | Amber | Key-value | Conflicts, alerts |
| selector | Neutral | Toggles + confirm | Feature/brick picker |

## Card JSON

```json
{"type": "list", "title": "Browse Menu",
 "columns": ["Item", "Name", "Price"],
 "rows": [["P1", "Nebula Margherita", "12.99"]]}

{"type": "confirmation", "title": "Place Order Completed",
 "fields": [{"label": "Customer", "value": "Zara"}]}

{"type": "error", "title": "Place Order Failed",
 "fields": [{"label": "Error", "value": "Customer not found"}]}

{"type": "selector", "title": "Choose extras for your agent",
 "items": [
   {"key": "CHART", "label": "Charts", "description": "Inline visualizations in chat", "default": true, "ready": true},
   {"key": "MEMORY", "label": "Memory", "description": "Persistent conversation history", "default": false, "ready": false},
   {"key": "KA", "label": "Knowledge Assistant", "description": "RAG with cited sources", "default": false, "ready": false}
 ]}
```

## Requirements (non-negotiable)

### R1: Humanized titles
`browse_menu` → `"Browse Menu"`. Strip underscores, title-case. In `tool_factory.py`.

### R2: Humanized field labels
`p_customer_name` → `"Customer Name"`. Strip `p_` prefix, title-case. In `tool_factory.py`.

### R3: Empty state
List cards with 0 rows show "No results found". In component.

### R4: Error cards
Errors return error cards, not plain text. In `tool_factory.py`.

### R5: Mobile responsive
`overflow-x-auto` on table containers. In component.

### R6: Dark mode
All variants have dark mode colors. Agent chat = `gray-*`, Mage chat = `dbx-gray-*`.

### R7: Malformed JSON fallback
Bad JSON → plain text markdown. In `response-blocks.ts` catch block.

### R8: Selector card with toggles
Interactive card for feature/brick selection during Mage discovery.
- Each item: toggle switch + label + description
- Items with `ready: false` toggle ON but LLM explains "coming soon"
- Confirm button sends selections back via `sendMessage`
- Card becomes read-only after confirm

### R9: All features/bricks shown in selector
Show everything. LLM handles "coming soon" messaging for unimplemented ones.

| Key | Label | Description | Ready? |
|-----|-------|-------------|--------|
| CHART | Charts | Inline visualizations | Yes |
| VISION | Vision | Image upload in chat | Yes |
| PERSONAS | Personas | Role selector | Yes |
| MEMORY | Memory | Persistent conversation history (requires Lakebase) | No — needs provisioning |
| VOICE | Voice | Speech input (requires OpenAI key) | No — needs API key |
| DASHBOARD | Dashboard | Live data tables on home page | No — needs domain config |
| KA | Knowledge Assistant | RAG with cited sources | No — needs docs + VS index |
| INFO_EXTRACTION | Info Extraction | Structured data from text | No — not implemented |
| DOC_PARSING | Doc Parsing | Parse PDFs/Word/HTML | No — not implemented |
| TEXT_CLASSIFICATION | Text Classification | Categorize text | No — not implemented |

## Agent Chat Pipeline (DONE)

```
tool_factory.py → ```card\n{json}\n``` → response-blocks.ts → message.tsx → <DynamicCard />
```

Files done:
- [x] `brickforge/app/client/src/components/elements/dynamic-card.tsx`
- [x] `brickforge/app/client/src/lib/response-blocks.ts` — `card` fence parsing
- [x] `brickforge/app/client/src/components/message.tsx` — render branch
- [x] `brickforge/tools/tool_factory.py` — list/confirmation/error cards

## Mage Chat Pipeline (TODO)

MageView uses SSE events, not code fences. Tools emit cards via `sse_queue`.

```
mage_tools.py → sse_queue.put({"event": "card", "data": card_json}) → MageView SSE handler → <DynamicCard />
```

### Files to Create

| File | Purpose |
|------|---------|
| `visual/frontend/src/components/DynamicCard.tsx` | Card renderer for Mage chat (`dbx-gray-*` tokens) |

### Files to Modify

| File | Change |
|------|--------|
| `visual/frontend/src/components/MageView.tsx` | Handle `card` SSE event, render DynamicCard, handle selector confirm |
| `brickforge/lib/mage_tools.py` | Add `suggest_extras` tool — emits selector card via sse_queue |
| `brickforge/lib/mage_agent.py` | Move extras from post-deploy step 6 to discovery phase |

## Selector Card Flow

1. During discovery, after understanding the domain, LLM calls `suggest_extras()`
2. Tool emits `event: card` with selector type showing all features/bricks
3. Tool returns "Extras presented. Wait for user response."
4. User flips toggles, clicks Confirm
5. MageView sends `sendMessage("Selected: Chart, Vision", { type: "card_action", selections: ["CHART", "VISION"] })`
6. LLM sees selections, calls `toggle_feature` for each ready item
7. For not-ready items user selected, LLM says "Memory is coming soon — requires Lakebase setup"
8. LLM proceeds to `present_spec` with selected features noted
9. Build includes toggled features, one deploy, everything included

## Implementation Order

1. `DynamicCard.tsx` for Mage chat — same logic as agent version, `dbx-gray-*` tokens, plus `selector` type with toggles
2. `MageView.tsx` — handle `card` SSE event, pass `sendMessage` to DynamicCard for selector confirm
3. `mage_tools.py` — add `suggest_extras` tool
4. `mage_agent.py` — move extras to discovery, instruct LLM to call `suggest_extras` before `present_spec`

## Verification

### Agent chat (done — needs deploy to test)
- Search query → list card with humanized title, columns, rows
- Search with 0 results → "No results found"
- Action → green confirmation card with humanized labels
- Failed action → red error card
- Text + card in same message → both render
- Malformed JSON → plain text fallback
- Dark mode: all types correct
- Mobile: horizontal scroll on wide tables

### Mage chat (TODO)
- Discovery: selector card appears with all features/bricks
- Ready items toggle normally
- Not-ready items toggle but LLM explains "coming soon"
- Confirm sends selections back
- Card becomes read-only after confirm
- LLM toggles selected features, proceeds to spec
- Dark mode: correct `dbx-*` colors
