# Hyperplan: Python Kanban Tool — Structured Insight Bundle

## Request Summary
Build a Python kanban tool with:
- Simple web UI (full CRUD: create, edit, move, delete boards/lists/cards)
- MCP server for LLM access over local network, compatible with opencode
- Sub-tasks/checklist on cards (TODO with checkboxes)
- Notes section on cards
- No auth, no scalability requirements, lightweight over robust

---

## Round 1: Members & Positions

| Member | Category | Approach |
|---|---|---|
| minimalist | unspecified-low | 3 files, 0 deps, stdlib http.server + sqlite3 + vanilla JS, ~500 lines |
| creative-designer | artistry | FastAPI + htmx, core/web/mcp/cli modules, CSS animations, dark mode |
| thorough-planner | unspecified-high | Full relational schema (8+ tables), SQLAlchemy, websocket pub/sub, fractional indexing |
| deep-logician | ultrabrain | 5 strategic trade-off decisions, two-process topology, per-operation MCP tools |
| researcher | deep | MCP Python SDK (FastMCP v2 alpha) deep-dive, stdio transport, opencode config |

---

## Round 2: Cross-Attack Convergence Map

### RESOLVED: Decisions with team consensus

| Decision | Winner | Losers | Rationale |
|---|---|---|---|
| HTTP framework | **FastAPI** | stdlib http.server | http.server is synchronous (blocks per request); kanban needs concurrent reads; FastAPI gives Pydantic validation + async + auto-docs for free |
| Process topology | **Two-process** (MCP stdio + Web HTTP) | Single-process | MCP stdio reads stdin; HTTP reads TCP socket. Can't multiplex both in one thread cleanly. Minimalist's shared-handler dream is an actual IO deadlock risk |
| MCP transport | **stdio** | Streamable HTTP | opencode uses stdio transport for local MCP servers. Streamable HTTP has session-header requirements and is not what opencode expects |
| Position ordering | **Integer gaps** (1000,2000,3000) | Fractional indexing | Fractional indexing avoids rebalancing but needs arbitrary-precision math; integer gaps + periodic rebalance is simpler, no edge cases |
| State consistency | **Shared SQLite + always-fresh reads** | WebSocket pub/sub | Single-user local tool: no concurrent writers; SQLite WAL mode handles concurrent reads; WebSocket pub/sub is zero-value complexity here |
| MCP tool pattern | **Individual per-operation tools** | Action-dispatch (single tool with action enum) | Individual tools give precise JSON Schema per operation; LLM can understand each tool independently; no confusing `action` parameter |

### DEFERRED: Decisions for the plan agent

| Question | Options | Context |
|---|---|---|
| Project structure | Flat single-file vs modular package | Minimalist pushes single `.py`; creative-designer wants `core/web/mcp/cli/` subpackage. Cross-attack landed on: **modular but flat** (2-3 modules, not 6+) |
| MCP SDK approach | Pinned v2 alpha vs minimal hand-rolled protocol | Researcher thoroughly documented FastMCP v2 alpha SDK; deep-logician warned alpha deps can break. **Hand-rolled MCP** over raw stdin/stdout JSON-RPC is simpler (no dep) but more work. SDK wins for correctness. |
| Tool naming | `kanban_*` vs `kanban_mcp_*` | Existing opencode config uses `kanban_mcp_*` namespace. Either works with correct config. |
| UI rendering | Server-rendered HTML (htmx/Jinja2) vs client-side JS | Htmx works for form actions; drag-and-drop needs client-side JS (SortableJS). **Hybrid**: htmx for CRUD forms, SortableJS for drag |
| Card data model | Sub-tasks as separate table vs JSON field | Checklist items are relational (order, completion status per item) → **separate table**. Notes = text field on card |

---

## Recommended Architecture

```
kanban/
├── kanban.py            # Entry point: CLI arg parsing, starts web or mcp mode
├── db.py                # SQLite schema + queries (pure functions)
├── models.py            # Pydantic models for all entities
├── web.py               # FastAPI app with htmx routes + static file serving
├── mcp_server.py        # MCP protocol server (stdio transport)
├── static/
│   ├── index.html       # Main kanban board UI
│   ├── style.css        # Styling (dark mode, responsive)
│   └── script.js        # HTMX + SortableJS interactions
└── kanban.db            # SQLite database (auto-created)
```

### Data Model

```sql
-- Boards (top-level containers)
CREATE TABLE boards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL DEFAULT 'Kanban',
  created_at TEXT DEFAULT (datetime('now'))
);

-- Lists/Columns
CREATE TABLE lists (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0
);

-- Cards
CREATE TABLE cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT DEFAULT '',         -- Notes section
  position INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);

-- Sub-tasks (checklist items)
CREATE TABLE subtasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  is_completed INTEGER NOT NULL DEFAULT 0,
  position INTEGER NOT NULL DEFAULT 0
);
```

### REST API (for web UI)

```
GET    /api/boards              → list boards with all nested data
POST   /api/boards              → create board           {name}
DELETE /api/boards/{id}         → delete board + cascade
POST   /api/boards/{id}/lists   → create list            {name}
PATCH  /api/lists/{id}          → update list name       {name}
DELETE /api/lists/{id}          → delete list
POST   /api/lists/{id}/cards    → create card            {title, description}
PATCH  /api/cards/{id}          → update card            {title, description, list_id, position}
DELETE /api/cards/{id}          → delete card
POST   /api/cards/{id}/subtasks → create subtask         {name}
PATCH  /api/subtasks/{id}       → toggle subtask         {is_completed}
DELETE /api/subtasks/{id}       → delete subtask
PATCH  /api/cards/{id}/move     → move card between lists {list_id, position}
```

### MCP Tools

```
kanban_get_boards()                          → list all boards with full state
kanban_create_board(name)                    → create new board
kanban_delete_board(board_id)                → delete board
kanban_create_list(board_id, name)           → create list on board
kanban_update_list(list_id, name)            → update list name
kanban_delete_list(list_id)                  → delete list
kanban_create_card(list_id, title, description) → create card
kanban_update_card(card_id, title, description)  → update card
kanban_delete_card(card_id)                  → delete card
kanban_move_card(card_id, list_id, position) → move card between lists
kanban_create_subtask(card_id, name)         → add checklist item
kanban_toggle_subtask(subtask_id)            → toggle completion
kanban_delete_subtask(subtask_id)            → remove checklist item
```

### UI Layout

```
┌──────────────────────────────────────────────────────┐
│  Board: [My Kanban]  [+ New List]                    │
├──────────────┬──────────────┬───────────────────────┤
│  To Do       │  In Progress │  Done                  │
│  ┌────────┐  │  ┌────────┐  │  ┌───────────────────┐ │
│  │ Card 1 │  │  │ Card 3 │  │  │ Card 5            │ │
│  │ [ ] s1 │  │  │        │  │  │ [x] step1         │ │
│  │ [ ] s2 │  │  │        │  │  │ [x] step2         │ │
│  │        │  │  │        │  │  │ Notes: shipped!    │ │
│  └────────┘  │  └────────┘  │  └───────────────────┘ │
│  ┌────────┐  │  ┌────────┐  │                        │
│  │ Card 2 │  │  │ Card 4 │  │                        │
│  └────────┘  │  └────────┘  │                        │
│  [+ Card]    │  [+ Card]    │  [+ Card]              │
└──────────────┴──────────────┴───────────────────────┘
```

### MCP Server (opencode config)

```jsonc
// In opencode.json or ~/.config/opencode/opencode.jsonc
{
  "mcpServers": {
    "kanban": {
      "command": "python",
      "args": ["/path/to/kanban/mcp_server.py"]
    }
  }
}
```

### Interaction Flow
1. User runs `python kanban.py web` → starts FastAPI on :8080 with UI
2. User runs `python kanban.py mcp` → starts MCP server on stdio (for opencode)
3. Both processes read/write the same `kanban.db` SQLite file
4. UI uses HTMX for page interactions, SortableJS for drag-and-drop
5. MCP server uses stdio transport, exposes tools listed above

---

## Must-Haves from Cross-Attack

1. ✅ **FastAPI** (not stdlib http.server — blocks, not concurrent)
2. ✅ **Two processes** (not single — IO multiplexing is a real problem)
3. ✅ **SQLite with WAL mode** (not WebSockets — zero-value complexity for single-user)
4. ✅ **Integer gap positioning** (not fractional indexing — simpler, no edge cases)
5. ✅ **Individual per-operation MCP tools** (not action-dispatch — better LLM ergonomics)
6. ✅ **Sub-tasks as separate table** (not JSON field — needs ordering + completion status)
7. ✅ **Notes as description field on cards** (not separate table — 1:1 with card)
8. ✅ **MCP on stdio** (not Streamable HTTP — opencode requires stdio)
9. ✅ **HTMX + SortableJS** (htmx for CRUD forms, SortableJS for drag-and-drop client-side)
10. ✅ **No auth, no Docker, no ORM** (raw sqlite3 + Pydantic is sufficient)

## Nice-to-Haves (skip for MVP)

- Dark mode toggle (CSS variable swap — 10 lines, add if user wants)
- Keyboard shortcuts (add in v2)
- CSS animations (add in v2)
- Card labels/tags (user didn't request)
