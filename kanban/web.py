from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
import os

from kanban.db import (
    get_boards,
    create_board,
    delete_board,
    create_list,
    update_list,
    delete_list,
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

    subs = "".join(_subtask_row(s, f"subtasks-{card.id}") for s in card.subtasks[:3])
    more = ""
    if len(card.subtasks) > 3:
        more = f'<span class="more-subtasks">+{len(card.subtasks) - 3} more</span>'

    desc = ""
    if card.description:
        preview = card.description[:80]
        if len(card.description) > 80:
            preview += "..."
        desc = f'<div class="notes-preview">{preview}</div>'

    return f"""<div class="card" id="card-{card.id}" data-card-id="{card.id}">
  <div class="card-title">{card.title}</div>
  {progress}
  <div id="subtasks-{card.id}" class="subtask-list">
    {subs}{more}
  </div>
  <form hx-post="/cards/{card.id}/subtasks"
        hx-target="#subtasks-{card.id}"
        hx-swap="innerHTML"
        class="board-form" style="margin-top:4px">
    <input type="text" name="name" placeholder="Add task..." required>
  </form>
  {desc}
  <div class="card-actions">
    <button hx-get="/cards/{card.id}" hx-target="#modal" class="btn-add">Edit</button>
    <button hx-delete="/cards/{card.id}"
            hx-target="#card-{card.id}"
            hx-swap="delete"
            class="btn-danger">×</button>
  </div>
</div>"""


def _subtask_list_html(card_id: int, subtasks: list) -> str:
    items = "".join(_subtask_row(s, f"subtasks-list-{card_id}") for s in subtasks)
    return f'<div id="subtasks-list-{card_id}" class="subtask-list">{items}</div>'


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


# ── Board Routes ──────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    boards = get_boards()
    return templates.TemplateResponse(request, "index.html", {"boards": boards})


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


@app.delete("/lists/{list_id}", response_class=HTMLResponse)
async def delete_list_route(list_id: int):
    delete_list(list_id)
    boards = get_boards()
    return _render_boards_html(boards)


# ── Card Routes ───────────────────────────────────────────────────────────


@app.post("/lists/{list_id}/cards", response_class=HTMLResponse)
async def create_card_route(list_id: int, title: str = Form(...), description: str = Form("")):
    card = create_card(list_id, title, description)
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
    return f"""<div class="modal-overlay active" id="modal">
  <div class="modal-content">
    <h2>Edit Card</h2>
    <form hx-patch="/cards/{card.id}" hx-target="#card-{card.id}" hx-swap="outerHTML">
      <label>Title</label>
      <input type="text" name="title" value="{card.title}" required>

      <label>Description</label>
      <textarea name="description">{card.description}</textarea>

      <label>Subtasks</label>
      <div id="subtasks-container-{card.id}">
        {subs}
        <form hx-post="/cards/{card.id}/subtasks"
              hx-target="#subtasks-container-{card.id}"
              hx-swap="innerHTML"
              class="board-form" style="margin-top:8px">
          <input type="text" name="name" placeholder="Add subtask..." required>
          <button type="submit" class="btn-add">Add</button>
        </form>
      </div>

      <div class="modal-actions">
        <button type="submit" class="btn-add">Save</button>
        <button type="button" onclick="this.closest('.modal-overlay').innerHTML=''" class="btn-danger">Cancel</button>
      </div>
    </form>
  </div>
</div>"""


@app.patch("/cards/{card_id}", response_class=HTMLResponse)
async def update_card_route(
    card_id: int,
    title: str = Form(...),
    description: str = Form(""),
):
    updated = update_card(card_id, title=title, description=description)
    if updated is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return _card_html(updated)


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
  <div class="empty-state">
    <h2>Welcome to Kanban!</h2>
    <p>No boards yet. Create your first board to get started.</p>
    <form class="board-form" style="max-width:360px;margin:0 auto" hx-post="/boards" hx-target="#boards" hx-swap="outerHTML">
      <input type="text" name="name" placeholder="Board name" required>
      <button type="submit" class="btn-add">Create Board</button>
    </form>
  </div>
</div>"""

    boards_html = ""
    for b in boards:
        lists_html = ""
        for lst in b.lists:
            cards_html = "".join(_card_html(c) for c in lst.cards)
            lists_html += f"""<div class="list" id="list-{lst.id}">
  <div class="list-header">
    <h2>{lst.name}</h2>
    <button hx-delete="/lists/{lst.id}"
            hx-target="#list-{lst.id}"
            hx-swap="delete"
            class="btn-danger">×</button>
  </div>
  <div class="cards" id="cards-{lst.id}" data-list-id="{lst.id}">
    {cards_html}
  </div>
  <div class="list-footer" style="padding:4px">
    <form class="board-form" hx-post="/lists/{lst.id}/cards" hx-target="#cards-{lst.id}" hx-swap="beforeend">
      <input type="text" name="title" placeholder="Card title..." required>
      <button type="submit" class="btn-add">+</button>
    </form>
  </div>
</div>"""

        boards_html += f"""<div class="board-section" id="board-section-{b.id}">
  <div class="board-header-row">
    <h2>{b.name}</h2>
    <button hx-delete="/boards/{b.id}"
            hx-target="#board-section-{b.id}"
            hx-swap="delete"
            class="btn-danger">×</button>
  </div>
  <div class="board-footer">
    <form class="board-form" hx-post="/boards/{b.id}/lists" hx-target="#boards" hx-swap="outerHTML">
      <input type="text" name="name" placeholder="New list name" required>
      <button type="submit" class="btn-add">+ New List</button>
    </form>
  </div>
  <div class="board">
    {lists_html}
  </div>
</div>"""

    return f"""<div id="boards">
  {boards_html}
  <div class="board-section" style="opacity:0.6">
    <div class="board-footer">
      <form class="board-form" hx-post="/boards" hx-target="#boards" hx-swap="outerHTML">
        <input type="text" name="name" placeholder="New board name" required>
        <button type="submit" class="btn-add">+ New Board</button>
      </form>
    </div>
  </div>
</div>"""
