from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader
import os
import asyncio
import subprocess
from typing import AsyncGenerator

try:
    GIT_HASH = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, timeout=5,
        cwd=os.path.dirname(__file__),
    ).stdout.strip()
except Exception:
    GIT_HASH = "unknown"

from kanban.db import (
    get_boards,
    create_board,
    delete_board,
    create_list,
    update_list,
    delete_list,
    move_list,
    create_card,
    update_card,
    delete_card,
    move_card,
    create_subtask,
    toggle_subtask,
    delete_subtask,
    move_subtask,
    init_db,
)
from kanban.mcp_server import MCPServer

templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")

# Custom env with no cache to avoid Jinja2/Starlette compat issue with unhashable Request
env = Environment(
    loader=FileSystemLoader(templates_dir),
    autoescape=True,
    cache_size=0,
)
templates = Jinja2Templates(env=env)

app = FastAPI()
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
async def startup():
    init_db()


# ── Helpers ────────────────────────────────────────────────────────────────


def _card_html(card) -> str:
    progress = ""
    if card.subtasks:
        done = sum(1 for s in card.subtasks if s.is_completed)
        total = len(card.subtasks)
        progress = f'<div class="subtask-progress">{done}/{total} done</div>'

    subs = "".join(_subtask_row(s, f"subtask-list-{card.id}") for s in card.subtasks)

    desc = ""
    if card.description:
        preview = card.description[:80]
        if len(card.description) > 80:
            preview += "..."
        desc = f'<div class="notes-preview">{preview}</div>'

    return f"""<div class="card bg-[#1e2a45] rounded-md p-3 mb-2 border border-border" id="card-{card.id}" data-card-id="{card.id}">
  <div class="card-title font-medium text-white text-sm mb-1">{card.title}</div>
  <div id="subtasks-{card.id}">
    {progress}
    <div id="subtask-list-{card.id}" class="subtask-list">
      {subs}
    </div>
    <form hx-post="/cards/{card.id}/subtasks"
          hx-target="#subtask-list-{card.id}"
          hx-swap="innerHTML"
          class="board-form" style="margin-top:4px">
    <input type="text" name="name" placeholder="Add task..." class="flex-1 px-2 py-1 rounded bg-[#0f0f1a] border border-border text-white text-xs" required>
    <button type="submit" class="btn-add px-2 py-1 rounded bg-accent text-white text-xs">+</button>
    </form>
  </div>
  {desc}
  <div class="flex items-center gap-2 mt-1 mb-1">
    <span class="inline-block w-2 h-2 rounded-full {'bg-red-500' if card.priority == 'high' else 'bg-yellow-500' if card.priority == 'medium' else 'bg-gray-400'} mr-1" title="{card.priority} priority"></span>
    <span class="text-xs text-muted">{card.status.replace('_', ' ').title()}</span>
  </div>
  <div class="card-actions flex gap-2 mt-2 pt-2 border-t border-border">
    <button hx-get="/cards/{card.id}" hx-target="#modal" class="btn-add">Edit</button>
    <button hx-delete="/cards/{card.id}"
            hx-target="#card-{card.id}"
            hx-swap="delete"
            class="btn-danger">×</button>
  </div>
</div>"""


def _subtask_list_html(card_id: int, subtasks: list) -> str:
    return "".join(_subtask_row(s, f"subtasks-list-{card_id}") for s in subtasks)


def _subtask_row(sub, container_id: str) -> str:
    """Render a single subtask <label> element for HTMX swap."""
    checked = 'checked' if sub.is_completed else ''
    return f'''<label class="subtask-item" id="subtask-{sub.id}">
      <input type="checkbox" class="subtask-checkbox"
             hx-patch="/subtasks/{sub.id}/toggle"
             hx-target="#{container_id}"
             hx-swap="innerHTML"
             {checked}>
      <span>{sub.name}</span>
      <button hx-delete="/subtasks/{sub.id}"
              hx-target="#subtask-{sub.id}"
              hx-swap="delete"
              class="btn-danger">×</button>
    </label>'''


# ── MCP HTTP Endpoint ────────────────────────────────────────────────────

_mcp_server = MCPServer()


@app.get("/version")
async def version():
    """Return the current git commit hash."""
    return JSONResponse({"version": GIT_HASH, "name": "kanban-mcp"})


@app.get("/sse")
@app.get("/mcp")
async def mcp_sse(request: Request):
    """MCP Streamable HTTP — SSE endpoint. Keeps connection alive for server messages."""
    base = str(request.base_url).rstrip("/")

    async def event_stream() -> AsyncGenerator[str, None]:
        yield f"event: endpoint\ndata: {base}/mcp\n\n"
        try:
            while True:
                yield ": keepalive\n\n"
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/mcp")
async def mcp_http_endpoint(request: Request):
    """JSON-RPC 2.0 MCP endpoint over HTTP for Streamable HTTP transport."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
            status_code=400,
        )
    result = _mcp_server.handle_json_rpc(body)
    if result is None:
        return JSONResponse(content=None, status_code=200)
    return JSONResponse(content=result)


# ── Board Routes ──────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    boards = get_boards()
    return templates.TemplateResponse(request, "index.html", {"boards": boards, "version": GIT_HASH})


@app.post("/boards", response_class=HTMLResponse)
async def create_board_route(name: str = Form(...)):
    create_board(name)
    boards = get_boards()
    return _render_boards_html(boards)


@app.delete("/boards/{board_id}", response_class=HTMLResponse)
async def delete_board_route(board_id: int):
    delete_board(board_id)
    boards = get_boards()
    return _render_boards_html(boards)


# ── List Routes ───────────────────────────────────────────────────────────


@app.post("/boards/{board_id}/lists", response_class=HTMLResponse)
async def create_list_route(board_id: int, name: str = Form(...)):
    create_list(board_id, name)
    boards = get_boards()
    return _render_boards_html(boards)


@app.patch("/lists/{list_id}", response_class=HTMLResponse)
async def update_list_route(list_id: int, name: str = Form(...)):
    updated = update_list(list_id, name)
    if updated is None:
        raise HTTPException(status_code=404, detail="List not found")
    boards = get_boards()
    return _render_boards_html(boards)


@app.patch("/lists/{list_id}/move", response_class=HTMLResponse)
async def move_list_route(list_id: int, board_id: int = Form(...), position: int = Form(...)):
    move_list(list_id, board_id, position)
    return HTMLResponse(content="", headers={"HX-Trigger": "boardRefresh"})


@app.delete("/lists/{list_id}", response_class=HTMLResponse)
async def delete_list_route(list_id: int):
    delete_list(list_id)
    boards = get_boards()
    return _render_boards_html(boards)


# ── Card Routes ───────────────────────────────────────────────────────────


@app.post("/lists/{list_id}/cards", response_class=HTMLResponse)
async def create_card_route(list_id: int, title: str = Form(...),
    description: str = Form(""), status: str = Form("pending"),
    priority: str = Form("medium")):
    card = create_card(list_id, title, description, status=status, priority=priority)
    return _card_html(card)


@app.get("/cards/{card_id}", response_class=HTMLResponse)
async def get_card_modal(card_id: int):
    boards = get_boards()
    card = None
    for b in boards:
        for lst in b.lists:
            for c in lst.cards:
                if c.id == card_id:
                    card = c
                    break
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    subs = _subtask_list_html(card.id, card.subtasks)
    return f"""<div class="modal-overlay active fixed inset-0 z-50 flex items-center justify-center bg-black/60" id="modal">
  <div class="modal-content bg-cardbg rounded-lg p-6 max-w-lg w-full mx-4 border border-border">
    <h2 class="text-xl font-bold text-white mb-4">Edit Card</h2>
    <form hx-patch="/cards/{card.id}" hx-target="#card-{card.id}" hx-swap="outerHTML">
      <label class="block text-sm text-muted mb-1">Title</label>
      <input type="text" name="title" value="{card.title}" class="w-full px-3 py-2 rounded bg-[#0f0f1a] border border-border text-white text-sm mb-3" required>

      <label class="block text-sm text-muted mb-1">Description</label>
      <textarea name="description" class="w-full px-3 py-2 rounded bg-[#0f0f1a] border border-border text-white text-sm mb-4">{card.description}</textarea>

      <label class="block text-sm text-muted mb-1">Status</label>
      <select name="status" class="w-full px-3 py-2 rounded bg-[#0f0f1a] border border-border text-white text-sm mb-3">
        <option value="pending" {"selected" if card.status == "pending" else ""}>Pending</option>
        <option value="in_progress" {"selected" if card.status == "in_progress" else ""}>In Progress</option>
        <option value="completed" {"selected" if card.status == "completed" else ""}>Completed</option>
        <option value="cancelled" {"selected" if card.status == "cancelled" else ""}>Cancelled</option>
      </select>

      <label class="block text-sm text-muted mb-1">Priority</label>
      <select name="priority" class="w-full px-3 py-2 rounded bg-[#0f0f1a] border border-border text-white text-sm mb-3">
        <option value="low" {"selected" if card.priority == "low" else ""}>Low</option>
        <option value="medium" {"selected" if card.priority == "medium" else ""}>Medium</option>
        <option value="high" {"selected" if card.priority == "high" else ""}>High</option>
      </select>

      <div class="modal-actions flex gap-2 justify-end">
        <button type="submit" class="btn-add px-4 py-2 rounded bg-accent text-white text-sm font-medium hover:bg-red-700">Save</button>
        <button type="button" onclick="document.getElementById('modal').innerHTML=''" class="btn-danger px-4 py-2 rounded bg-gray-600 text-white text-sm font-medium hover:bg-gray-500">Cancel</button>
      </div>
    </form>

    <hr style="margin:12px 0">

    <label>Subtasks</label>
    <div id="subtasks-container-{card.id}">
      <div id="subtasks-list-{card.id}" class="subtask-list">
        {subs}
      </div>
      <form hx-post="/cards/{card.id}/subtasks"
            hx-target="#subtasks-list-{card.id}"
            hx-swap="innerHTML"
            class="board-form" style="margin-top:8px">
        <input type="text" name="name" placeholder="Add subtask..." class="flex-1 px-2 py-1 rounded bg-[#0f0f1a] border border-border text-white text-xs" required>
        <button type="submit" class="btn-add px-2 py-1 rounded bg-accent text-white text-xs">Add</button>
      </form>
    </div>
  </div>
</div>"""


@app.patch("/cards/{card_id}", response_class=HTMLResponse)
async def update_card_route(
    card_id: int,
    title: str | None = Form(None),
    description: str | None = Form(None),
    status: str | None = Form(None),
    priority: str | None = Form(None),
):
    updated = update_card(card_id, title=title, description=description, status=status, priority=priority)
    if updated is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return HTMLResponse(
        content=_card_html(updated),
        headers={"HX-Trigger": "closeModal"},
    )


@app.delete("/cards/{card_id}", response_class=HTMLResponse)
async def delete_card_route(card_id: int):
    delete_card(card_id)
    return HTMLResponse("")


@app.patch("/cards/{card_id}/move", response_class=HTMLResponse)
async def move_card_route(card_id: int, list_id: int = Form(...), position: int = Form(0)):
    move_card(card_id, list_id, position)
    return HTMLResponse(content="", headers={"HX-Trigger": "boardRefresh"})


@app.patch("/subtasks/{subtask_id}/move", response_class=HTMLResponse)
async def move_subtask_route(subtask_id: int, position: int = Form(...)):
    move_subtask(subtask_id, position)
    return HTMLResponse(content="", headers={"HX-Trigger": "boardRefresh"})


# ── Subtask Routes ────────────────────────────────────────────────────────


@app.post("/cards/{card_id}/subtasks", response_class=HTMLResponse)
async def create_subtask_route(card_id: int, name: str = Form(...)):
    create_subtask(card_id, name)
    boards = get_boards()
    card = None
    for b in boards:
        for lst in b.lists:
            for c in lst.cards:
                if c.id == card_id:
                    card = c
                    break
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return _subtask_list_html(card_id, card.subtasks)


@app.patch("/subtasks/{subtask_id}/toggle", response_class=HTMLResponse)
async def toggle_subtask_route(subtask_id: int):
    subtask = toggle_subtask(subtask_id)
    if subtask is None:
        raise HTTPException(status_code=404, detail="Subtask not found")
    boards = get_boards()
    card = None
    for b in boards:
        for lst in b.lists:
            for c in lst.cards:
                if c.id == subtask.card_id:
                    card = c
                    break
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return _subtask_list_html(card.id, card.subtasks)


@app.delete("/subtasks/{subtask_id}", response_class=HTMLResponse)
async def delete_subtask_route(subtask_id: int):
    boards = get_boards()
    card_id = None
    for b in boards:
        for lst in b.lists:
            for c in lst.cards:
                for s in c.subtasks:
                    if s.id == subtask_id:
                        card_id = c.id
                        break
    if card_id is None:
        raise HTTPException(status_code=404, detail="Subtask not found")
    delete_subtask(subtask_id)
    boards = get_boards()
    for b in boards:
        for lst in b.lists:
            for c in lst.cards:
                if c.id == card_id:
                    return _subtask_list_html(card_id, c.subtasks)
    return _subtask_list_html(card_id, [])


# ── Internal helpers ───────────────────────────────────────────────────────


def _render_boards_html(boards) -> str:
    if not boards:
        return """<div id="boards">
  <div class="empty-state text-center py-16">
    <h2 class="text-2xl font-bold text-white mb-2">Welcome to Kanban!</h2>
    <p class="text-muted mb-6">No boards yet. Create your first board to get started.</p>
    <form class="board-form flex gap-2 max-w-sm mx-auto" hx-post="/boards" hx-target="#boards" hx-swap="outerHTML">
      <input type="text" name="name" placeholder="Board name" class="flex-1 px-3 py-1.5 rounded bg-[#0f0f1a] border border-border text-white text-sm" required>
      <button type="submit" class="btn-add px-3 py-1.5 rounded bg-accent text-white text-sm font-medium hover:bg-red-700">Create Board</button>
    </form>
  </div>
</div>"""

    boards_html = ""
    for b in boards:
        lists_html = ""
        for lst in b.lists:
            cards_html = "".join(_card_html(c) for c in lst.cards)
            lists_html += f"""<div class="list bg-cardbg rounded-lg p-3 min-w-[260px] border border-border" id="list-{lst.id}">
  <div class="list-header flex items-center justify-between mb-2">
    <h2 class="font-semibold text-white text-sm">{lst.name}</h2>
    <button hx-delete="/lists/{lst.id}"
            hx-target="#list-{lst.id}"
            hx-swap="delete"
            class="btn-danger">×</button>
  </div>
  <div class="cards" id="cards-{lst.id}" data-list-id="{lst.id}">
    {cards_html}
  </div>
  <div class="list-footer p-1">
    <form class="board-form flex gap-1" hx-post="/lists/{lst.id}/cards" hx-target="#cards-{lst.id}" hx-swap="beforeend">
      <input type="text" name="title" placeholder="Card title..." class="flex-1 px-2 py-1 rounded bg-[#0f0f1a] border border-border text-white text-xs" required>
      <button type="submit" class="btn-add px-2 py-1 rounded bg-accent text-white text-xs">+</button>
    </form>
  </div>
</div>"""

        boards_html += f"""<div class="board-section mb-6" id="board-section-{b.id}">
  <div class="board-header-row flex items-center justify-between mb-3">
    <h2 class="text-lg font-semibold text-white">{b.name}</h2>
    <button hx-delete="/boards/{b.id}"
            hx-target="#board-section-{b.id}"
            hx-swap="delete"
            class="btn-danger"
            onclick="return confirm('Delete this board and all its lists and cards?')">Delete</button>
  </div>
  <div class="board-footer mb-3">
    <form class="board-form flex gap-2" hx-post="/boards/{b.id}/lists" hx-target="#boards" hx-swap="outerHTML">
      <input type="text" name="name" placeholder="New list name" class="flex-1 px-3 py-1.5 rounded bg-[#0f0f1a] border border-border text-white text-sm" required>
      <button type="submit" class="btn-add px-3 py-1.5 rounded bg-accent text-white text-sm font-medium hover:bg-red-700">+ New List</button>
    </form>
  </div>
  <div class="board" data-board-id="{b.id}">
    {lists_html}
  </div>
</div>"""

    return f"""<div id="boards">
  <div class="board-section opacity-60 mb-6">
    <div class="board-footer mb-3">
      <form class="board-form flex gap-2 max-w-sm" hx-post="/boards" hx-target="#boards" hx-swap="outerHTML">
        <input type="text" name="name" placeholder="New board name" class="flex-1 px-3 py-1.5 rounded bg-[#0f0f1a] border border-border text-white text-sm" required>
        <button type="submit" class="btn-add px-3 py-1.5 rounded bg-accent text-white text-sm font-medium hover:bg-red-700">+ New Board</button>
      </form>
    </div>
  </div>
  {boards_html}
</div>"""
