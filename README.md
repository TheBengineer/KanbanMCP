# Kanban — Python Kanban Board with Web UI + MCP

A lightweight kanban board for local use — web UI for humans, MCP server for LLMs. No Node.js, no database server. One SQLite file, single process.

## Quick Start

### Native (no Docker)

```bash
# 1. Create virtual environment and install
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn pydantic jinja2 python-multipart

# 2. Start the server (web UI + MCP over HTTP)
python kanban.py
```

### Docker

```bash
# Build and start the web server
docker compose up -d
```

Open **[http://localhost:8080](http://localhost:8080)** in your browser. The database is persisted in a Docker volume (`kanban-data`).

The database (`kanban/kanban.db`) is auto-created on first run.

## Usage

```bash
# Start the server (web UI + MCP over HTTP)
python kanban.py

# MCP stdio proxy (for clients that only support stdio transport)
python kanban.py mcp
```

## Features

- **Boards** with named lists (columns)
- **Cards** with title, notes (description), and position ordering
- **Checklists** (sub-tasks) on cards with toggleable checkboxes
- **Drag-and-drop** cards between lists via SortableJS
- **Inline editing** via HTMX — click to edit, no page reload
- **MCP server** — expose your kanban board to any MCP-compatible LLM (opencode, Claude Desktop, etc.)

## MCP Tools (13)

| Tool | Description |
|---|---|
| `kanban_get_boards` | List all boards with full nested state |
| `kanban_create_board` | Create a new board |
| `kanban_delete_board` | Delete a board |
| `kanban_create_list` | Add a column to a board |
| `kanban_update_list` | Rename a column |
| `kanban_delete_list` | Delete a column |
| `kanban_create_card` | Add a card with title and notes |
| `kanban_update_card` | Update card title/notes |
| `kanban_delete_card` | Delete a card |
| `kanban_move_card` | Move card between columns |
| `kanban_create_subtask` | Add a checklist item |
| `kanban_toggle_subtask` | Toggle checklist item |
| `kanban_delete_subtask` | Remove checklist item |

## Data Model

```
Board (id, name, created_at)
 └── List (id, board_id, name, position)
      └── Card (id, list_id, title, description, position, created_at)
           └── Subtask (id, card_id, name, is_completed, position)
```

- Integer-gap positioning (1000, 2000, 3000...) — rebalanced automatically
- SQLite with WAL mode for concurrent web + MCP access

## Project Structure

```
Dockerfile            Docker image definition
docker-compose.yml    Docker Compose service definition
kanban.py              CLI entry point (default: web + MCP, mcp: stdio proxy)
kanban/
  __init__.py
  models.py            Pydantic data models
  db.py                SQLite database layer (WAL mode)
  web.py               FastAPI web server + HTMX routes
  mcp_server.py        MCP stdio server (JSON-RPC 2.0)
  kanban.db            SQLite database (auto-created)
  SKILL.md             OpenCode skills plugin
templates/
  index.html           Jinja2 board template
static/
  style.css            Board styling
  script.js            SortableJS drag-and-drop + HTMX enhancements
tests/
  test_models.py       51 tests
  test_db.py           37 tests
  test_web.py          26 tests
  test_mcp.py          19 tests
  test_integration.py  11 tests
```

## Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

All 138 tests pass.

## opencode Integration

### Primary (HTTP)

The web server exposes an MCP endpoint over HTTP:

```jsonc
{
  "mcpServers": {
    "kanban": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

This enables remote access — replace `localhost` with the server's hostname or IP to connect from other machines.

### Legacy (stdio)

#### Native

Add to your `.opencode/opencode.jsonc`:

```jsonc
{
  "mcpServers": {
    "kanban": {
      "command": "python",
      "args": ["/path/to/kanban/kanban.py", "mcp"]
    }
  }
}
```

#### Docker

```jsonc
{
  "mcpServers": {
    "kanban": {
      "command": "docker",
      "args": ["exec", "-i", "kanban-web", "python", "kanban.py", "mcp"]
    }
  }
}
```

## OpenCode Skills Plugin

An OpenCode skill at `kanban/SKILL.md` teaches LLM agents how to correctly interact with this kanban board.

The skill is auto-discovered when your prompt mentions trigger keywords (kanban, board, card, list, subtask, ticket). No config files or symlinks needed.

**Activation:** Mention "kanban board" or "create a ticket" in any prompt — the skill loads automatically with guidance on the MCP tools, data model invariants, and anti-patterns.

**Verification:** The skill is active if OpenCode responds knowing about position semantics, cascade rules, and the connection lifecycle without you explaining them.

**Global install (optional):** For use across projects:
```bash
mkdir -p ~/.claude/skills/kanban/
ln -s $(pwd)/kanban/SKILL.md ~/.claude/skills/kanban/SKILL.md
```

## Architecture

- **Single process** — web (FastAPI + uvicorn) serves both the HTMX UI and the MCP HTTP endpoint
- **No ORM** — raw `sqlite3` + Pydantic for validation
- **No auth** — designed for local use
- **No caching** — every read hits SQLite directly
- **HTMX + SortableJS** — minimal JavaScript, server-driven UI

## Dependencies

- Python ≥ 3.10
- fastapi, uvicorn, pydantic, jinja2, python-multipart
- No Docker, no Node.js, no external database
