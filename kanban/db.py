import sqlite3
import os

from kanban.models import Board, Card, List, Subtask, ChatMessage

DB_PATH = os.environ.get("KANBAN_DB_PATH") or os.path.join(os.path.dirname(__file__), "kanban.db")


def get_conn() -> sqlite3.Connection:
    """Create a new WAL-mode SQLite connection with row factory and foreign keys."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist (idempotent)."""
    conn = get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS boards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT 'Kanban',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS subtasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                is_completed INTEGER NOT NULL DEFAULT 0,
                position INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                author TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_chat_messages_card ON chat_messages(card_id, created_at);
        """)

        # Migrate existing databases: add status and priority columns if missing
        cursor = conn.execute("PRAGMA table_info(cards)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        if "status" not in existing_cols:
            conn.execute("ALTER TABLE cards ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
        if "priority" not in existing_cols:
            conn.execute("ALTER TABLE cards ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'")

        conn.commit()
    finally:
        conn.close()


def get_boards() -> list[Board]:
    """Full nested fetch: boards -> lists -> cards -> subtasks.

    Returns list of Board Pydantic models with nested Lists, Cards, Subtasks.
    """
    conn = get_conn()
    try:
        board_rows = conn.execute("SELECT * FROM boards ORDER BY id").fetchall()
        result: list[Board] = []
        for br in board_rows:
            board = Board(id=br["id"], name=br["name"], created_at=br["created_at"])

            list_rows = conn.execute(
                "SELECT * FROM lists WHERE board_id = ? ORDER BY position, id",
                (br["id"],),
            ).fetchall()

            for lr in list_rows:
                lst = List(
                    id=lr["id"],
                    board_id=lr["board_id"],
                    name=lr["name"],
                    position=lr["position"],
                )

                card_rows = conn.execute(
                    "SELECT * FROM cards WHERE list_id = ? ORDER BY position, id",
                    (lr["id"],),
                ).fetchall()

                for cr in card_rows:
                    card = Card(
                        id=cr["id"],
                        list_id=cr["list_id"],
                        title=cr["title"],
                        description=cr["description"],
                        position=cr["position"],
                        created_at=cr["created_at"],
                        status=cr["status"],
                        priority=cr["priority"],
                    )

                    subtask_rows = conn.execute(
                        "SELECT * FROM subtasks WHERE card_id = ? ORDER BY position, id",
                        (cr["id"],),
                    ).fetchall()

                    for sr in subtask_rows:
                        card.subtasks.append(
                            Subtask(
                                id=sr["id"],
                                card_id=sr["card_id"],
                                name=sr["name"],
                                is_completed=bool(sr["is_completed"]),
                                position=sr["position"],
                            )
                        )

                    lst.cards.append(card)

                board.lists.append(lst)

            result.append(board)

        return result
    finally:
        conn.close()


def _next_position(conn: sqlite3.Connection, table: str, parent_col: str, parent_id: int) -> int:
    """Get the next position (rounded to nearest 1000 above current max)."""
    row = conn.execute(
        f"SELECT COALESCE(MAX(position), 0) AS max_pos FROM {table} WHERE {parent_col} = ?",
        (parent_id,),
    ).fetchone()
    return ((row["max_pos"] // 1000) + 1) * 1000


def _rebalance(table: str, parent_col: str, parent_id: int, conn: sqlite3.Connection | None = None) -> None:
    """Renumber positions: 1000, 2000, 3000... for items with given parent."""
    close = False
    if conn is None:
        conn = get_conn()
        close = True
    try:
        rows = conn.execute(
            f"SELECT id FROM {table} WHERE {parent_col} = ? ORDER BY position, id",
            (parent_id,),
        ).fetchall()
        for i, row in enumerate(rows):
            conn.execute(
                f"UPDATE {table} SET position = ? WHERE id = ?",
                ((i + 1) * 1000, row["id"]),
            )
        conn.commit()
    finally:
        if close:
            conn.close()


def get_board(board_id: int) -> Board | None:
    """Fetch a single board by id with all nested lists, cards, subtasks."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone()
        if row is None:
            return None
        board = Board(id=row["id"], name=row["name"], created_at=row["created_at"])

        list_rows = conn.execute(
            "SELECT * FROM lists WHERE board_id = ? ORDER BY position, id",
            (board_id,),
        ).fetchall()

        for lr in list_rows:
            lst = List(
                id=lr["id"],
                board_id=lr["board_id"],
                name=lr["name"],
                position=lr["position"],
            )

            card_rows = conn.execute(
                "SELECT * FROM cards WHERE list_id = ? ORDER BY position, id",
                (lr["id"],),
            ).fetchall()

            for cr in card_rows:
                card = Card(
                    id=cr["id"],
                    list_id=cr["list_id"],
                    title=cr["title"],
                    description=cr["description"],
                    position=cr["position"],
                    created_at=cr["created_at"],
                    status=cr["status"],
                    priority=cr["priority"],
                )

                subtask_rows = conn.execute(
                    "SELECT * FROM subtasks WHERE card_id = ? ORDER BY position, id",
                    (cr["id"],),
                ).fetchall()

                for sr in subtask_rows:
                    card.subtasks.append(
                        Subtask(
                            id=sr["id"],
                            card_id=sr["card_id"],
                            name=sr["name"],
                            is_completed=bool(sr["is_completed"]),
                            position=sr["position"],
                        )
                    )

                lst.cards.append(card)

            board.lists.append(lst)

        return board
    finally:
        conn.close()


def get_blocked_tasks() -> list[dict]:
    """Return cards in Blocked lists across all boards, with board/list context."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT c.id, c.title, c.description, c.status, c.priority,
                   b.id AS board_id, b.name AS board_name,
                   l.id AS list_id, l.name AS list_name
            FROM cards c
            JOIN lists l ON c.list_id = l.id
            JOIN boards b ON l.board_id = b.id
            WHERE l.name = 'Blocked'
            ORDER BY b.name, c.title
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_dashboard_stats() -> dict:
    """Return summary stats for the dashboard."""
    conn = get_conn()
    try:
        board_count = conn.execute("SELECT COUNT(*) FROM boards").fetchone()[0]
        list_count = conn.execute("SELECT COUNT(*) FROM lists").fetchone()[0]
        card_count = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        subtask_count = conn.execute("SELECT COUNT(*) FROM subtasks").fetchone()[0]
        chat_count = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
        return {
            "boards": board_count,
            "lists": list_count,
            "cards": card_count,
            "subtasks": subtask_count,
            "chat_messages": chat_count,
        }
    finally:
        conn.close()


def _fetch_board(conn: sqlite3.Connection, board_id: int) -> Board | None:
    """Fetch a single board by id. Delegates to get_board()."""
    return get_board(board_id)


def _fetch_card(conn: sqlite3.Connection, card_id: int) -> Card | None:
    """Fetch a single card by id."""
    row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    if row is None:
        return None
    card = Card(
        id=row["id"],
        list_id=row["list_id"],
        title=row["title"],
        description=row["description"],
        position=row["position"],
        created_at=row["created_at"],
        status=row["status"],
        priority=row["priority"],
    )
    subtask_rows = conn.execute(
        "SELECT * FROM subtasks WHERE card_id = ? ORDER BY position, id",
        (card_id,),
    ).fetchall()
    for sr in subtask_rows:
        card.subtasks.append(
            Subtask(
                id=sr["id"],
                card_id=sr["card_id"],
                name=sr["name"],
                is_completed=bool(sr["is_completed"]),
                position=sr["position"],
            )
        )
    return card


def _fetch_list(conn: sqlite3.Connection, list_id: int) -> List | None:
    """Fetch a single list by id."""
    row = conn.execute("SELECT * FROM lists WHERE id = ?", (list_id,)).fetchone()
    if row is None:
        return None
    return List(id=row["id"], board_id=row["board_id"], name=row["name"], position=row["position"])


DEFAULT_LISTS = ["Backlog", "Blocked", "Todo", "In Progress", "Done", "Wontfix"]


def create_board(name: str) -> Board:
    """INSERT into boards with default lists, return the created Board."""
    conn = get_conn()
    try:
        cur = conn.execute("INSERT INTO boards (name) VALUES (?)", (name,))
        board_id = cur.lastrowid
        for i, list_name in enumerate(DEFAULT_LISTS):
            conn.execute(
                "INSERT INTO lists (board_id, name, position) VALUES (?, ?, ?)",
                (board_id, list_name, (i + 1) * 1000),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone()
        return Board(id=row["id"], name=row["name"], created_at=row["created_at"])
    finally:
        conn.close()


def delete_board(board_id: int) -> None:
    """DELETE board by id (cascade deletes lists/cards/subtasks via FK)."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM boards WHERE id = ?", (board_id,))
        conn.commit()
    finally:
        conn.close()


def move_list(list_id: int, board_id: int, position: int) -> None:
    """Move list to a new position (0 = first), then rebalance."""
    conn = get_conn()
    try:
        conn.execute("UPDATE lists SET board_id = ?, position = ? WHERE id = ?", (board_id, position, list_id))
        conn.commit()
        _rebalance("lists", "board_id", board_id, conn)
    finally:
        conn.close()


def create_list(board_id: int, name: str) -> List:
    """INSERT list with auto-position (next 1000 gap)."""
    conn = get_conn()
    try:
        pos = _next_position(conn, "lists", "board_id", board_id)
        cur = conn.execute(
            "INSERT INTO lists (board_id, name, position) VALUES (?, ?, ?)",
            (board_id, name, pos),
        )
        list_id = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM lists WHERE id = ?", (list_id,)).fetchone()
        return List(id=row["id"], board_id=row["board_id"], name=row["name"], position=row["position"])
    finally:
        conn.close()


def update_list(list_id: int, name: str) -> List | None:
    """UPDATE list name. Returns None if not found."""
    conn = get_conn()
    try:
        cur = conn.execute("UPDATE lists SET name = ? WHERE id = ?", (name, list_id))
        if cur.rowcount == 0:
            return None
        conn.commit()
        return _fetch_list(conn, list_id)
    finally:
        conn.close()


def delete_list(list_id: int) -> None:
    """DELETE list + rebalance positions."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT board_id FROM lists WHERE id = ?", (list_id,)).fetchone()
        if row is None:
            return
        board_id = row["board_id"]
        conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))
        conn.commit()
        _rebalance("lists", "board_id", board_id, conn)
    finally:
        conn.close()


def create_card(list_id: int, title: str, description: str = "", status: str = "pending", priority: str = "medium") -> Card:
    """INSERT card with auto-position."""
    conn = get_conn()
    try:
        pos = _next_position(conn, "cards", "list_id", list_id)
        cur = conn.execute(
            "INSERT INTO cards (list_id, title, description, position, status, priority) VALUES (?, ?, ?, ?, ?, ?)",
            (list_id, title, description, pos, status, priority),
        )
        card_id = cur.lastrowid
        conn.commit()
        return _fetch_card(conn, card_id)
    finally:
        conn.close()


def update_card(card_id: int, title: str | None = None, description: str | None = None, status: str | None = None, priority: str | None = None) -> Card | None:
    """Partial update — only set non-None fields."""
    conn = get_conn()
    try:
        updates: dict[str, str] = {}
        if title is not None:
            updates["title"] = title
        if description is not None:
            updates["description"] = description
        if status is not None:
            updates["status"] = status
        if priority is not None:
            updates["priority"] = priority
        if not updates:
            return _fetch_card(conn, card_id)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        values.append(card_id)
        cur = conn.execute(f"UPDATE cards SET {set_clause} WHERE id = ?", values)
        if cur.rowcount == 0:
            return None
        conn.commit()
        return _fetch_card(conn, card_id)
    finally:
        conn.close()


def delete_card(card_id: int) -> None:
    """DELETE card + rebalance."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT list_id FROM cards WHERE id = ?", (card_id,)).fetchone()
        if row is None:
            return
        list_id = row["list_id"]
        conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        conn.commit()
        _rebalance("cards", "list_id", list_id, conn)
    finally:
        conn.close()


def move_card(card_id: int, target_list_id: int, position: int) -> None:
    """Move card to a list, set position (0 = top), then renumber to 1000-gaps."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE cards SET list_id = ?, position = ? WHERE id = ?",
            (target_list_id, position, card_id),
        )
        conn.commit()
        _rebalance("cards", "list_id", target_list_id, conn)
    finally:
        conn.close()


def move_subtask(subtask_id: int, position: int) -> None:
    """Move subtask to new position (0 = top), then rebalance its card."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT card_id FROM subtasks WHERE id = ?", (subtask_id,)).fetchone()
        if row is None:
            return
        card_id = row["card_id"]
        conn.execute(
            "UPDATE subtasks SET position = ? WHERE id = ?",
            (position, subtask_id),
        )
        conn.commit()
        _rebalance("subtasks", "card_id", card_id, conn)
    finally:
        conn.close()


def create_subtask(card_id: int, name: str) -> Subtask:
    """INSERT subtask with auto-position."""
    conn = get_conn()
    try:
        pos = _next_position(conn, "subtasks", "card_id", card_id)
        cur = conn.execute(
            "INSERT INTO subtasks (card_id, name, position) VALUES (?, ?, ?)",
            (card_id, name, pos),
        )
        subtask_id = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM subtasks WHERE id = ?", (subtask_id,)).fetchone()
        return Subtask(
            id=row["id"],
            card_id=row["card_id"],
            name=row["name"],
            is_completed=bool(row["is_completed"]),
            position=row["position"],
        )
    finally:
        conn.close()


def toggle_subtask(subtask_id: int) -> Subtask | None:
    """Flip is_completed bit (0->1 or 1->0)."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE subtasks SET is_completed = 1 - is_completed WHERE id = ?",
            (subtask_id,),
        )
        if cur.rowcount == 0:
            return None
        conn.commit()
        row = conn.execute("SELECT * FROM subtasks WHERE id = ?", (subtask_id,)).fetchone()
        return Subtask(
            id=row["id"],
            card_id=row["card_id"],
            name=row["name"],
            is_completed=bool(row["is_completed"]),
            position=row["position"],
        )
    finally:
        conn.close()


def delete_subtask(subtask_id: int) -> None:
    """DELETE subtask + rebalance."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT card_id FROM subtasks WHERE id = ?", (subtask_id,)).fetchone()
        if row is None:
            return
        card_id = row["card_id"]
        conn.execute("DELETE FROM subtasks WHERE id = ?", (subtask_id,))
        conn.commit()
        _rebalance("subtasks", "card_id", card_id, conn)
    finally:
        conn.close()


def _fetch_chat_message(conn: sqlite3.Connection, message_id: int) -> ChatMessage | None:
    """Fetch a single chat message by id."""
    row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
    if row is None:
        return None
    return ChatMessage(
        id=row["id"],
        card_id=row["card_id"],
        author=row["author"],
        body=row["body"],
        created_at=row["created_at"],
    )


def create_chat_message(card_id: int, author: str = "", body: str = "") -> ChatMessage:
    """INSERT a chat message."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO chat_messages (card_id, author, body) VALUES (?, ?, ?)",
            (card_id, author, body),
        )
        message_id = cur.lastrowid
        conn.commit()
        return _fetch_chat_message(conn, message_id)
    finally:
        conn.close()


def get_chat_messages(card_id: int) -> list[ChatMessage]:
    """Fetch all messages for a card, ordered chronologically."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE card_id = ? ORDER BY created_at, id",
            (card_id,),
        ).fetchall()
        return [
            ChatMessage(
                id=row["id"],
                card_id=row["card_id"],
                author=row["author"],
                body=row["body"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
    finally:
        conn.close()
