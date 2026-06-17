# CardMaker - Dynamic Card Renderer for Agent Chat

> Status: PLANNED
> Creawhat ted: 2026-06-17

## Context

The deployed agent returns structured data (reservation confirmations, guest profiles, room listings) as plain text. Users see walls of text instead of styled visual cards. The amadeus-checkin project has domain-specific hardcoded cards (checkin-impact-card.tsx, etc.). CardMaker is a generic renderer - one component, any domain. Card definitions generated alongside functions by Mage.

## How It Works

Agent outputs a ```card``` code fence in its response (same pattern as ```chart``` for inline charts). Chat UI detects the fence, parses JSON, renders a styled card component.

```
User: "Book cabin 7 for Zara, July 20-25"
Agent: "Done!"

┌─────────────────────────────────┐
│ ✓ Reservation Confirmed         │
├─────────────────────────────────┤
│ Reservation  RES-00042          │
│ Guest        Zara               │
│ Room         Cabin 7            │
│ Check-in     July 20, 2025      │
│ Check-out    July 25, 2025      │
│ Total        2,500 credits      │
└─────────────────────────────────┘
```

## Card Types

| Type | Header | Icon | Use case |
|------|--------|------|----------|
| confirmation | Green | Check | Reservation created, guest registered |
| info | Blue | Info | Room details, guest profile |
| list | Neutral | None | Search results, booking history (table layout) |
| error | Red | X | Failed operations |
| warning | Amber | Alert | Near-capacity, conflicts |

Two layout variants:
- **Key-value**: single item with labeled fields (confirmation, info)
- **Table**: multiple rows with columns (list)

Cards can be **interactive** - buttons that let users act without typing:
- List card with [Book] per row -> user clicks -> sends choice to LLM -> agent acts
- Confirmation card with [Confirm] / [Cancel] buttons
- Info card with [Check In] / [View Bookings] actions
- Modification card with [Save] / [Discard]

This is a UX improvement: structured visual output + inline actions instead of "type your choice."

## Card JSON Schema

### Key-value card
```json
{"type": "confirmation", "title": "Reservation Confirmed",
 "icon": "check", "color": "green",
 "fields": [
   {"label": "Reservation", "value": "RES-00042"},
   {"label": "Guest", "value": "Zara"},
   {"label": "Room", "value": "Cabin 7, Deck 3"},
   {"label": "Check-in", "value": "July 20, 2025"},
   {"label": "Total", "value": "2,500 credits"}
 ]}
```

### Table card
```json
{"type": "list", "title": "Your Bookings",
 "columns": ["ID", "Room", "Dates", "Status"],
 "rows": [
   ["RES-00042", "Cabin 7", "Jul 20-25", "Confirmed"],
   ["RES-00038", "Pod 3", "Jun 1-3", "Checked Out"]
 ]}
```

### Interactive card (with actions)
```json
{"type": "list", "title": "Available Rooms",
 "columns": ["Room", "Type", "Deck", "Price/Night"],
 "rows": [
   ["Cabin 7", "Pod", "Deck 3", "250"],
   ["Suite 12", "Suite", "Deck 5", "500"],
   ["Pod 3", "Zero-G", "Deck 1", "180"]
 ],
 "actions": [
   {"label": "Book", "action": "book_room", "per_row": true}
 ]}
```

When `per_row: true`, each row gets its own button. Click sends `{type: "card_action", action: "book_room", row_index: 2, row_data: ["Pod 3", "Zero-G", "Deck 1", "180"]}` to the agent.

### Confirmation card (with actions)
```json
{"type": "confirmation", "title": "Confirm Reservation",
 "fields": [
   {"label": "Room", "value": "Pod 3"},
   {"label": "Dates", "value": "Jul 20-25"},
   {"label": "Total", "value": "900 credits"}
 ],
 "actions": [
   {"label": "Confirm", "action": "confirm_booking", "style": "primary"},
   {"label": "Cancel", "action": "cancel_booking", "style": "secondary"}
 ]}
```

Actions without `per_row` are card-level buttons (bottom of card). `style` controls appearance: primary = orange/solid, secondary = gray/outline.

## Card Definition Generation (Mage build time)

During routine generation, Mage also generates card definitions per function/procedure:

```json
{
  "cards": [
    {
      "tool": "make_reservation",
      "card_type": "confirmation",
      "title_template": "Reservation Confirmed",
      "fields": [
        {"key": "reservation_id", "label": "Reservation"},
        {"key": "guest_name", "label": "Guest"},
        {"key": "room_number", "label": "Room"},
        {"key": "check_in_date", "label": "Check-in", "format": "date"},
        {"key": "total_cost", "label": "Total", "format": "currency"}
      ]
    },
    {
      "tool": "search_available_rooms",
      "card_type": "list",
      "title_template": "Available Rooms",
      "columns": ["Room", "Type", "Deck", "Price/Night"],
      "field_keys": ["room_number", "type", "deck", "price_per_night"]
    }
  ]
}
```

Stored in `projects/<name>/cards.json`. Deployed with agent bundle. Injected into agent system prompt so the LLM knows to output ```card``` fences.

## Data Source for Cards - Tools Return Card Fences Directly

The chart tool already returns a code fence directly (generate_chart.py:67):
```python
return f"```chart\n{json.dumps(config)}\n```"
```

CardMaker follows the same pattern. **Tools themselves** return card fences, not the LLM. More reliable.

**Read functions** (search_available_rooms, get_traveler_reservations):
- tool_factory.py already gets `columns` and `rows` from `execute_query()`
- Return a list card fence instead of plain text:
```python
card = {"type": "list", "title": tool_name, "columns": columns, "rows": rows}
return f"```card\n{json.dumps(card)}\n```"
```

**Action tools** (make_reservation, register_guest):
- tool_factory.py knows the params it was called with
- Return a confirmation card fence:
```python
card = {"type": "confirmation", "title": f"{tool_name} completed",
        "fields": [{"label": k, "value": v} for k, v in kwargs.items()]}
return f"```card\n{json.dumps(card)}\n```"
```

**Interactive cards** (search results with [Book] buttons):
- Tool adds `actions` from card definition in cards.json
- Card definition specifies which tools get which actions

Tools produce structured output. LLM wraps it in natural language around the card.

## Existing Infrastructure (discovered during inventory)

The chat UI already has a code fence parsing + card rendering pipeline:

- `response-blocks.ts:parseResponseBlocks()` - splits message text into segments by code fence type
- `response-blocks.ts:126-133` - `chart` type already parsed as JSON
- `response-blocks.ts:134` - any unrecognized fence type emitted as domain block
- `domain/index.ts:domainCardRenderers` - registry mapping block type -> React component
- `message.tsx:256` - checks `domainCardRenderers[seg.type]` and renders if found

**Key insight**: we don't need to modify message.tsx or response-blocks.ts parsing. We just need to:
1. Add `'card'` as a JSON-parsed type in `parseResponseBlocks` (same as `chart`)
2. Create the `DynamicCard` component
3. Register in `domainCardRenderers` OR render directly in message.tsx

## Files to Create

| File | Purpose |
|------|---------|
| `brickforge/app/client/src/components/elements/dynamic-card.tsx` | Generic card renderer (key-value + table + interactive actions) |
| `brickforge/data/gen/card_generator.py` | Generate card definitions from routine specs |

## Dual Chat Support

Cards render in BOTH chat UIs:

| Chat UI | Location | When |
|---------|----------|------|
| **Mage chat** | `visual/frontend/src/components/MageView.tsx` | During discovery (warehouse picker), build (progress), post-deploy (summary) |
| **Agent chat** | `brickforge/app/client/src/components/message.tsx` | At runtime (search results, confirmations, guest profiles) |

Two separate React apps - can't share imports directly. DynamicCard component built twice (same code, two locations) or extracted to a shared JS file loaded by both.

**Mage chat card use cases:**
- Discovery: "I found 3 warehouses" -> list card with [Select] per row
- Discovery: "Here's the spec" -> info card with capability list
- Build: progress stepper card (live updating)
- Post-deploy: "Here's what I built" -> summary card (tables, functions, app URL)
- Amend: "Current config" -> info card with settings

**Agent chat card use cases:**
- Search results -> list card with [Book] buttons
- Confirmations -> confirmation card (green, fields)
- Guest profile -> info card (blue, fields)
- Errors -> error card (red, message)
- Booking history -> list card

Same JSON schema, same component, two apps.

## Files to Create

| File | Purpose |
|------|---------|
| `brickforge/app/client/src/components/elements/dynamic-card.tsx` | Card renderer for agent chat |
| `visual/frontend/src/components/DynamicCard.tsx` | Card renderer for Mage chat (same code) |
| `brickforge/data/gen/card_generator.py` | Generate card definitions from routine specs |

## Files to Modify

| File | Change |
|------|--------|
| `brickforge/app/client/src/lib/response-blocks.ts` | Add `card` as JSON-parsed type (3 lines, same pattern as `chart`) |
| `brickforge/app/client/src/components/message.tsx` | Import DynamicCard, add `seg.type === 'card'` render branch (3 lines) |
| `visual/frontend/src/components/MageView.tsx` | Add card message type + DynamicCard rendering |
| `brickforge/tools/tool_factory.py` | Read tools return list card fences, action tools return confirmation card fences + verify INSERT success |
| `brickforge/agent/agent.py` | Load cards.json, inject card schemas into system prompt |
| `brickforge/deploy/deploy_agent_app.py` | Include cards.json in deploy bundle (via conf/ dir, already bundled) |
| `brickforge/lib/mage_agent.py` | Add card generation step to build protocol |
| `brickforge/lib/mage_tools.py` | Read tools return card fences for Mage (warehouse list, catalog list, etc.) |

## Gaps Identified (from unravel)

| # | Gap | Severity | Resolution |
|---|-----|----------|-----------|
| 1 | Card action button -> how to send to agent | Medium | Convert to natural language with embedded data ("Book room P-03, Pod, Deck 1, 180/night"), send as user message. No API changes. |
| 2 | Action tools don't know output (reservation_id, total) | Medium | V1: show input params only. V2: follow-up SELECT after CALL. |
| 3 | Confirmation card on silently failed operation | **High** | tool_factory MUST verify INSERT success (follow-up SELECT) before returning confirmation card. If not found, return error card. Not optional. |
| 4 | tool_factory.py needs to read cards.json | Medium | Load from conf/cards.json at tool creation time. Cards define which tools get which card type + actions. |
| 5 | Mobile responsive for list cards | Low | overflow-x-auto on table container. |
| 6 | Two separate React apps need same component | Medium | Duplicate DynamicCard in both apps (same code). Extract to shared JS file later if needed. |

**Gap 3 is critical.** A green confirmation card for a failed booking is worse than plain text. Must be fixed alongside CardMaker.

## Gap Fixes

### Gap 1: Card action button -> agent
Button click converts to natural language with embedded data. No API changes.
```
User clicks [Book] on row "P-03, Pod, Deck 1, 180/night"
-> sendMessage("I'd like to book room P-03 (Pod, Deck 1, 180/night)")
```
In MageView: same pattern for [Select] buttons on warehouse/catalog lists.
Both apps use `sendMessage` which already exists in both chat UIs.

### Gap 2: Action tools don't know output
V1: confirmation card shows input params only (what the user asked for).
V2: tool_factory.py does a follow-up SELECT after CALL to get the created row:
```python
execute_statement(w, wh_id, stmt)  # CALL proc(...)
# Verify + get actual data
verify_stmt = f"SELECT * FROM {schema}.{table} WHERE {lookup_col} = '{lookup_val}' ORDER BY created_at DESC LIMIT 1"
columns, rows = execute_query(w, wh_id, verify_stmt)
```
The lookup column/table comes from cards.json definition for this tool.

### Gap 3: Verify INSERT success (CRITICAL)
tool_factory.py action tools currently return "success" without checking.
Fix: after every CALL, verify the row exists. If not, return error card.
```python
execute_statement(w, wh_id, stmt)

# Verify - cards.json provides verify_query template per tool
if verify_query:
    columns, rows = execute_query(w, wh_id, verify_query.format(**kwargs))
    if not rows:
        card = {"type": "error", "title": f"{safe_proc} failed",
                "fields": [{"label": "Reason", "value": "Operation completed but no data was created. Check input values."}]}
        return f"```card\n{json.dumps(card)}\n```"

card = {"type": "confirmation", ...}
return f"```card\n{json.dumps(card)}\n```"
```
The verify_query in cards.json:
```json
{
  "tool": "make_reservation",
  "verify_query": "SELECT * FROM {schema}.reservations WHERE traveler_id = '{p_traveler_id}' ORDER BY created_at DESC LIMIT 1",
  "card_type": "confirmation"
}
```

### Gap 4: tool_factory reads cards.json
At tool creation time, load cards.json from conf/cards.json (or PROJECT_DIR/conf/cards.json).
Pass card definition to create_sql_read_tool / create_action_tool as optional param.
Tool uses it to format return as card fence + set verify_query for action tools.

### Gap 5: Mobile responsive
Add `overflow-x-auto` to the table container in DynamicCard:
```tsx
<div className="overflow-x-auto">
  <table>...</table>
</div>
```

### Gap 6: Two React apps
Duplicate DynamicCard.tsx in both locations. Same code, no shared imports.
- `brickforge/app/client/src/components/elements/dynamic-card.tsx`
- `visual/frontend/src/components/DynamicCard.tsx`
Extract to shared package only if the component diverges significantly.

## Implementation Order

1. Build `dynamic-card.tsx` for agent chat - key-value, table, interactive actions, error variant
2. Add `card` JSON parser to `response-blocks.ts` (3 lines)
3. Add card render branch to `message.tsx` (3 lines)
4. Duplicate DynamicCard to `visual/frontend/src/components/DynamicCard.tsx` for Mage chat
5. Add card message type to MageView.tsx SSE handler + render
6. Fix tool_factory.py - read tools return list cards, action tools verify + return confirmation/error cards
7. Build `card_generator.py` - LLM generates card defs from routine specs
8. Wire into Mage build flow (after routine gen, before deploy)
9. Load cards.json in agent.py, inject into system prompt
10. Test agent chat: search -> list card, book -> confirmation card, failed book -> error card
11. Test Mage chat: warehouse picker -> list card, spec -> info card

## Verification

- Agent: search rooms -> list card with [Book] buttons renders
- Agent: make reservation -> confirmation card (green, fields) renders
- Agent: failed reservation -> error card (red) renders, NOT confirmation
- Agent: guest lookup -> info card (blue) renders
- Mage: warehouse selection -> list card with [Select] renders
- Mage: spec presentation -> info card renders
- Both: malformed JSON -> falls back to plain text (no crash)
- Both: dark mode -> correct colors
- Both: mobile -> horizontal scroll on wide tables
- Deploy: cards.json included in bundle, loaded at agent startup
