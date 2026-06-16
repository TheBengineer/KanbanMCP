import sqlite3

from kanban import db
from kanban.models import Board, Card, List, Subtask
import pytest
from kanban import db as kanban_db


def _raw_conn(path: str) -> sqlite3.Connection:
    """Open a direct connection to a db file for inspection."""
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def test_init_db_creates_tables(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    conn = _raw_conn(tmp_db_path)
    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "boards" in tables
    assert "lists" in tables
    assert "cards" in tables
    assert "subtasks" in tables


def test_get_boards_empty(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()
    assert db.get_boards() == []


def test_create_and_get_board(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("My Board")
    assert board.id > 0
    assert board.name == "My Board"
    assert board.created_at != ""

    boards = db.get_boards()
    assert len(boards) == 1
    assert boards[0].id == board.id
    assert boards[0].name == "My Board"


def test_create_board_name(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("Test")
    assert board.name == "Test"
    assert board.created_at != ""
    assert len(board.created_at) > 0


def test_create_list(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("Board")
    lst = db.create_list(board.id, "Todo")
    assert lst.id > 0
    assert lst.board_id == board.id
    assert lst.name == "Todo"
    # First list gets position 1000
    assert lst.position == 1000

    # Second list gets 2000
    lst2 = db.create_list(board.id, "Done")
    assert lst2.position == 2000


def test_create_card(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("Board")
    lst = db.create_list(board.id, "List")
    card = db.create_card(lst.id, "Task 1", "Details")

    assert card.id > 0
    assert card.list_id == lst.id
    assert card.title == "Task 1"
    assert card.description == "Details"
    # First card gets position 1000
    assert card.position == 1000
    assert card.created_at != ""
    # Default subtasks should be empty
    assert card.subtasks == []


def test_create_card_default_description(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("B")
    lst = db.create_list(board.id, "L")
    card = db.create_card(lst.id, "No desc")

    assert card.description == ""


def test_create_subtask(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("Board")
    lst = db.create_list(board.id, "List")
    card = db.create_card(lst.id, "Card")
    sub = db.create_subtask(card.id, "Subtask A")

    assert sub.id > 0
    assert sub.card_id == card.id
    assert sub.name == "Subtask A"
    assert sub.is_completed is False
    assert sub.position == 1000

    sub2 = db.create_subtask(card.id, "Subtask B")
    assert sub2.position == 2000


def test_delete_board_cascade(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("Board")
    lst = db.create_list(board.id, "List")
    card = db.create_card(lst.id, "Card")
    db.create_subtask(card.id, "Sub")

    db.delete_board(board.id)
    assert db.get_boards() == []

    conn = _raw_conn(tmp_db_path)
    assert conn.execute("SELECT COUNT(*) FROM boards").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM lists").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM subtasks").fetchone()[0] == 0
    conn.close()


def test_delete_list_cascade(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("Board")
    lst1 = db.create_list(board.id, "List1")
    lst2 = db.create_list(board.id, "List2")
    card = db.create_card(lst1.id, "Card")
    db.create_subtask(card.id, "Sub")

    db.delete_list(lst1.id)

    conn = _raw_conn(tmp_db_path)
    assert conn.execute("SELECT COUNT(*) FROM lists").fetchone()[0] == 1
    assert conn.execute("SELECT name FROM lists").fetchone()["name"] == "List2"
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM subtasks").fetchone()[0] == 0
    conn.close()


def test_delete_card_cascade(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("Board")
    lst = db.create_list(board.id, "List")
    card1 = db.create_card(lst.id, "Card1")
    card2 = db.create_card(lst.id, "Card2")
    db.create_subtask(card1.id, "Sub")

    db.delete_card(card1.id)

    conn = _raw_conn(tmp_db_path)
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1
    assert conn.execute("SELECT title FROM cards").fetchone()["title"] == "Card2"
    assert conn.execute("SELECT COUNT(*) FROM subtasks").fetchone()[0] == 0
    conn.close()


def test_move_card_between_lists(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("Board")
    lst1 = db.create_list(board.id, "List1")
    lst2 = db.create_list(board.id, "List2")
    card = db.create_card(lst1.id, "Moving Card")

    db.move_card(card.id, lst2.id, 1000)

    boards = db.get_boards()
    board_fetched = boards[0]
    # card should now be in lst2
    assert len(board_fetched.lists[0].cards) == 0  # lst1 has no cards
    assert len(board_fetched.lists[1].cards) == 1  # lst2 has the card
    moved = board_fetched.lists[1].cards[0]
    assert moved.id == card.id
    assert moved.title == "Moving Card"
    assert moved.list_id == lst2.id
    assert moved.position == 1000


def test_toggle_subtask(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("Board")
    lst = db.create_list(board.id, "List")
    card = db.create_card(lst.id, "Card")
    sub = db.create_subtask(card.id, "Sub")

    assert sub.is_completed is False

    # Toggle on
    sub = db.toggle_subtask(sub.id)
    assert sub is not None
    assert sub.is_completed is True

    # Toggle off
    sub = db.toggle_subtask(sub.id)
    assert sub is not None
    assert sub.is_completed is False


def test_toggle_subtask_not_found(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()
    assert db.toggle_subtask(999) is None


def test_position_rebalance_after_delete(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("Board")
    lst = db.create_list(board.id, "List")

    # Create 3 cards with default positions
    c1 = db.create_card(lst.id, "A")
    c2 = db.create_card(lst.id, "B")
    c3 = db.create_card(lst.id, "C")
    assert c1.position == 1000
    assert c2.position == 2000
    assert c3.position == 3000

    # Delete the middle card
    db.delete_card(c2.id)

    # Rebalance should have happened: remaining cards get 1000, 2000
    boards = db.get_boards()
    remaining = boards[0].lists[0].cards
    assert len(remaining) == 2
    # They should be renumbered starting at 1000
    assert remaining[0].position == 1000
    assert remaining[0].title == "A"
    assert remaining[1].position == 2000
    assert remaining[1].title == "C"


def test_update_card_partial(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("Board")
    lst = db.create_list(board.id, "List")
    card = db.create_card(lst.id, "Original", "Original desc")

    # Update only title
    updated = db.update_card(card.id, title="New Title")
    assert updated is not None
    assert updated.title == "New Title"
    assert updated.description == "Original desc"

    # Update only description
    updated = db.update_card(card.id, description="New Desc")
    assert updated is not None
    assert updated.title == "New Title"
    assert updated.description == "New Desc"

    # Update both
    updated = db.update_card(card.id, title="Both", description="Changed")
    assert updated is not None
    assert updated.title == "Both"
    assert updated.description == "Changed"


def test_update_card_not_found(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()
    assert db.update_card(999, title="Nope") is None


def test_get_boards_nested(tmp_db_path):
    db.DB_PATH = tmp_db_path
    db.init_db()

    board = db.create_board("Project")
    lst1 = db.create_list(board.id, "Backlog")
    lst2 = db.create_list(board.id, "Active")
    c1 = db.create_card(lst1.id, "Idea")
    c2 = db.create_card(lst2.id, "Working", "In progress")
    db.create_subtask(c1.id, "Research")
    db.create_subtask(c1.id, "Write")
    db.create_subtask(c2.id, "Test")

    boards = db.get_boards()
    assert len(boards) == 1
    b = boards[0]
    assert b.name == "Project"
    assert len(b.lists) == 2

    # Lists ordered by position
    assert b.lists[0].name == "Backlog"
    assert b.lists[1].name == "Active"

    # Backlog has 1 card
    backlog_cards = b.lists[0].cards
    assert len(backlog_cards) == 1
    assert backlog_cards[0].title == "Idea"
    assert len(backlog_cards[0].subtasks) == 2
    assert backlog_cards[0].subtasks[0].name == "Research"
    assert backlog_cards[0].subtasks[1].name == "Write"

    # Active has 1 card with 1 subtask
    active_cards = b.lists[1].cards
    assert len(active_cards) == 1
    assert active_cards[0].title == "Working"
    assert active_cards[0].description == "In progress"
    assert len(active_cards[0].subtasks) == 1
    assert active_cards[0].subtasks[0].name == "Test"


def test_delete_nonexistent_board(tmp_db_path):
    """Deleting a board that doesn't exist should not raise."""
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    kanban_db.delete_board(999)  # Should not raise


def test_delete_nonexistent_list(tmp_db_path):
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    kanban_db.delete_list(999)


def test_delete_nonexistent_card(tmp_db_path):
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    kanban_db.delete_card(999)


def test_delete_nonexistent_subtask(tmp_db_path):
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    kanban_db.delete_subtask(999)


def test_update_nonexistent_list(tmp_db_path):
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    result = kanban_db.update_list(999, "New Name")
    assert result is None


def test_update_nonexistent_card(tmp_db_path):
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    result = kanban_db.update_card(999, title="Whatever")
    assert result is None


def test_toggle_nonexistent_subtask(tmp_db_path):
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    result = kanban_db.toggle_subtask(999)
    assert result is None


def test_create_board_default_name(tmp_db_path):
    """Board can be created with empty name."""
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    board = kanban_db.create_board("")
    assert board.name == ""


def test_create_list_with_empty_name(tmp_db_path):
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    board = kanban_db.create_board("Board")
    lst = kanban_db.create_list(board.id, "")
    assert lst.name == ""


def test_create_card_with_empty_title(tmp_db_path):
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    board = kanban_db.create_board("Board")
    lst = kanban_db.create_list(board.id, "List")
    card = kanban_db.create_card(lst.id, "", "Notes")
    assert card.title == ""
    assert card.description == "Notes"


def test_create_subtask_with_empty_name(tmp_db_path):
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    board = kanban_db.create_board("Board")
    lst = kanban_db.create_list(board.id, "List")
    card = kanban_db.create_card(lst.id, "Card")
    subtask = kanban_db.create_subtask(card.id, "")
    assert subtask.name == ""


def test_get_boards_with_multiple_boards(tmp_db_path):
    """Multiple boards each with their own data should be isolated."""
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    b1 = kanban_db.create_board("Board 1")
    b2 = kanban_db.create_board("Board 2")
    l1 = kanban_db.create_list(b1.id, "List 1-1")
    kanban_db.create_card(l1.id, "Card on Board 1")
    l2 = kanban_db.create_list(b2.id, "List 2-1")
    kanban_db.create_card(l2.id, "Card on Board 2")

    boards = kanban_db.get_boards()
    assert len(boards) == 2
    assert len(boards[0].lists) == 1
    assert len(boards[1].lists) == 1
    assert boards[0].lists[0].cards[0].title == "Card on Board 1"
    assert boards[1].lists[0].cards[0].title == "Card on Board 2"


def test_move_card_to_same_list(tmp_db_path):
    """Move card within same list changes position."""
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    board = kanban_db.create_board("Board")
    lst = kanban_db.create_list(board.id, "List")
    c1 = kanban_db.create_card(lst.id, "Card 1")  # position 1000
    c2 = kanban_db.create_card(lst.id, "Card 2")  # position 2000
    kanban_db.move_card(c1.id, lst.id, 3000)      # c1 moved past c2

    boards = kanban_db.get_boards()
    # c2 (pos 2000) should come before c1 (pos 3000)
    assert boards[0].lists[0].cards[0].id == c2.id
    assert boards[0].lists[0].cards[1].id == c1.id


def test_create_card_with_long_title(tmp_db_path):
    """Card with very long title should be stored."""
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    board = kanban_db.create_board("Board")
    lst = kanban_db.create_list(board.id, "List")
    long_title = "X" * 500
    card = kanban_db.create_card(lst.id, long_title)
    assert len(card.title) == 500


def test_get_single_board(tmp_db_path):
    """create_board returns the board with id and created_at."""
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    board = kanban_db.create_board("My Board")
    assert board.id is not None
    assert board.id > 0
    assert board.name == "My Board"
    assert board.created_at != ""


def test_rebalance_after_multiple_deletes(tmp_db_path):
    """Rebalancing renumbers to 1000, 2000, 3000."""
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    board = kanban_db.create_board("Board")
    lst = kanban_db.create_list(board.id, "List")
    c1 = kanban_db.create_card(lst.id, "C1")
    c2 = kanban_db.create_card(lst.id, "C2")
    c3 = kanban_db.create_card(lst.id, "C3")
    kanban_db.delete_card(c2.id)

    boards = kanban_db.get_boards()
    remaining = boards[0].lists[0].cards
    assert len(remaining) == 2
    assert remaining[0].position == 1000
    assert remaining[1].position == 2000


def test_delete_list_with_cards(tmp_db_path):
    """Deleting a list removes its cards and subtasks."""
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    board = kanban_db.create_board("Board")
    lst = kanban_db.create_list(board.id, "List")
    card = kanban_db.create_card(lst.id, "Card")
    kanban_db.create_subtask(card.id, "Sub")
    kanban_db.delete_list(lst.id)

    boards = kanban_db.get_boards()
    assert boards[0].lists == []  # List cascade deleted


def test_update_card_only_title(tmp_db_path):
    """Updating only title keeps description unchanged."""
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    board = kanban_db.create_board("Board")
    lst = kanban_db.create_list(board.id, "List")
    card = kanban_db.create_card(lst.id, "Original", "Original notes")
    kanban_db.update_card(card.id, title="Updated")

    boards = kanban_db.get_boards()
    updated = boards[0].lists[0].cards[0]
    assert updated.title == "Updated"
    assert updated.description == "Original notes"


def test_create_and_get_board_with_created_at(tmp_db_path):
    """Board should have a non-empty created_at timestamp."""
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()
    board = kanban_db.create_board("Timestamp Test")
    assert board.created_at != ""
    assert "T" in board.created_at or " " in board.created_at  # ISO format or similar
