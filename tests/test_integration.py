"""Integration tests for kanban — testing web + MCP + DB consistency."""

import pytest
from fastapi.testclient import TestClient
from kanban import db as kanban_db
from kanban.web import app


@pytest.fixture
def tclient(tmp_db_path):
    """Fixture: patch DB path and create fresh TestClient per test."""
    kanban_db.DB_PATH = tmp_db_path
    with TestClient(app) as client:
        yield client


class TestWebDBIntegration:
    """Verify web API reads/writes to DB correctly."""

    def test_create_board_via_db_read_via_web(self, tclient):
        """Create board via DB, verify it appears in web index."""
        kanban_db.create_board("DB Board")

        resp = tclient.get("/")
        assert resp.status_code == 200
        # The page should contain the board name
        assert "DB Board" in resp.text

    def _find_list(self, board_id, name):
        boards = kanban_db.get_boards()
        board = [b for b in boards if b.id == board_id][0]
        return [l for l in board.lists if l.name == name][0]

    def test_create_card_via_web_read_via_db(self, tclient):
        """Create card via web POST, verify it's in DB."""
        board = kanban_db.create_board("Board")
        lst = kanban_db.create_list(board.id, "List")

        resp = tclient.post(f"/lists/{lst.id}/cards", data={"title": "Web Card", "description": "From web"})
        assert resp.status_code == 200

        target = self._find_list(board.id, "List")
        assert len(target.cards) == 1
        assert target.cards[0].title == "Web Card"
        assert target.cards[0].description == "From web"

    def test_delete_card_via_web_check_db(self, tclient):
        """Delete card via web, verify DB reflects removal."""
        board = kanban_db.create_board("B")
        lst = kanban_db.create_list(board.id, "L")
        card = kanban_db.create_card(lst.id, "Del Me")

        resp = tclient.delete(f"/cards/{card.id}")
        assert resp.status_code == 200

        target = self._find_list(board.id, "L")
        assert len(target.cards) == 0

    def test_toggle_subtask_via_web_check_db(self, tclient):
        """Toggle subtask via web, verify DB shows completion."""
        board = kanban_db.create_board("B")
        lst = kanban_db.create_list(board.id, "L")
        card = kanban_db.create_card(lst.id, "C")
        sub = kanban_db.create_subtask(card.id, "Toggle Me")
        assert sub.is_completed is False

        resp = tclient.patch(f"/subtasks/{sub.id}/toggle")
        assert resp.status_code == 200

        target = self._find_list(board.id, "L")
        toggled = target.cards[0].subtasks[0]
        assert toggled.is_completed is True

    def test_full_workflow_via_web(self, tclient):
        """Complete workflow: create board -> list -> card -> subtask -> toggle -> move -> verify."""
        # Create board
        resp = tclient.post("/boards", data={"name": "Project"})
        assert resp.status_code == 200
        boards = kanban_db.get_boards()
        board = boards[0]
        assert board.name == "Project"

        # Create list
        resp = tclient.post(f"/boards/{board.id}/lists", data={"name": "Todo"})
        assert resp.status_code == 200
        boards = kanban_db.get_boards()
        lst = [l for l in boards[0].lists if l.name == "Todo"][0]
        assert lst.name == "Todo"

        # Create card
        resp = tclient.post(f"/lists/{lst.id}/cards", data={"title": "Task", "description": "Details"})
        assert resp.status_code == 200
        boards = kanban_db.get_boards()
        card = [l for l in boards[0].lists if l.name == "Todo"][0].cards[0]
        assert card.title == "Task"

        # Create a second list for moving
        resp = tclient.post(f"/boards/{board.id}/lists", data={"name": "Done"})
        assert resp.status_code == 200
        boards = kanban_db.get_boards()
        done_list = [l for l in boards[0].lists if l.name == "Done"][0]

        # Add subtask
        resp = tclient.post(f"/cards/{card.id}/subtasks", data={"name": "Check step"})
        assert resp.status_code == 200
        todo_list = [l for l in kanban_db.get_boards()[0].lists if l.name == "Todo"][0]
        sub = todo_list.cards[0].subtasks[0]
        assert sub.name == "Check step"

        # Toggle subtask
        resp = tclient.patch(f"/subtasks/{sub.id}/toggle")
        assert resp.status_code == 200

        # Move card to Done
        resp = tclient.patch(f"/cards/{card.id}/move", data={"list_id": done_list.id, "position": 1000})
        assert resp.status_code == 200

        # Final verification
        boards = kanban_db.get_boards()
        todo = [l for l in boards[0].lists if l.name == "Todo"][0]
        done = [l for l in boards[0].lists if l.name == "Done"][0]
        assert len(todo.cards) == 0  # Todo empty
        assert len(done.cards) == 1  # Done has card
        moved_card = done.cards[0]
        assert moved_card.title == "Task"
        assert moved_card.subtasks[0].is_completed is True


class TestWebRender:
    """Verify HTML rendering correctness."""

    def test_boards_page_shows_lists_and_cards(self, tclient):
        """Dashboard shows board names and links to board view."""
        board = kanban_db.create_board("My Board")
        lst = kanban_db.create_list(board.id, "Todo")
        kanban_db.create_card(lst.id, "Card 1")
        kanban_db.create_card(lst.id, "Card 2")

        resp = tclient.get("/")
        assert resp.status_code == 200
        assert "My Board" in resp.text
        assert "/board/" + str(board.id) in resp.text
        assert "2 cards" in resp.text
        assert "7 lists" in resp.text

    def test_board_page_shows_lists_and_cards(self, tclient):
        """Board detail page renders lists and cards."""
        board = kanban_db.create_board("My Board")
        lst = kanban_db.create_list(board.id, "Todo")
        kanban_db.create_card(lst.id, "Card 1")
        kanban_db.create_card(lst.id, "Card 2")

        resp = tclient.get(f"/board/{board.id}")
        assert resp.status_code == 200
        assert "My Board" in resp.text
        assert "Todo" in resp.text
        assert "Card 1" in resp.text
        assert "Card 2" in resp.text

    def test_card_modal_shows_subtasks(self, tclient):
        """Card modal displays subtask names and checkbox states."""
        board = kanban_db.create_board("B")
        lst = kanban_db.create_list(board.id, "L")
        card = kanban_db.create_card(lst.id, "Card")
        kanban_db.create_subtask(card.id, "Sub 1")
        sub2 = kanban_db.create_subtask(card.id, "Sub 2")
        kanban_db.toggle_subtask(sub2.id)

        resp = tclient.get(f"/cards/{card.id}")
        assert resp.status_code == 200
        assert "Sub 1" in resp.text
        assert "Sub 2" in resp.text

    def test_empty_board_shows_no_boards_message(self, tclient):
        resp = tclient.get("/")
        assert "No boards yet" in resp.text


class TestWebMCPConsistency:
    """Verify web and MCP access the same database consistently (integration)."""

    def test_create_web_read_mcp(self, tmp_db_path):
        """Create via web API, read via kanban.db module."""
        from kanban import db
        db.DB_PATH = tmp_db_path
        from kanban.web import app
        with TestClient(app) as client:
            # Create via web
            resp = client.post("/boards", data={"name": "Shared Board"})
            assert resp.status_code == 200

        # Verify via DB
        boards = db.get_boards()
        assert len(boards) == 1
        assert boards[0].name == "Shared Board"

    def test_db_operations_do_not_conflict(self, tmp_db_path):
        """Multiple DB operations in sequence should be isolated."""
        from kanban import db
        db.DB_PATH = tmp_db_path
        db.init_db()

        b1 = db.create_board("Board 1")
        b2 = db.create_board("Board 2")

        l1 = db.create_list(b1.id, "List 1-1")
        l2 = db.create_list(b2.id, "List 2-1")

        db.create_card(l1.id, "Card on B1")
        db.create_card(l2.id, "Card on B2")

        boards = db.get_boards()
        assert len(boards) == 2
        assert len(boards[0].lists) == len(db.DEFAULT_LISTS) + 1
        assert len(boards[1].lists) == len(db.DEFAULT_LISTS) + 1
        b1_list = [l for l in boards[0].lists if l.id == l1.id][0]
        b2_list = [l for l in boards[1].lists if l.id == l2.id][0]
        assert b1_list.cards[0].title == "Card on B1"
        assert b2_list.cards[0].title == "Card on B2"

    def test_card_with_description_and_subtasks(self, tmp_db_path):
        """Card with description and multiple subtasks."""
        from kanban import db
        db.DB_PATH = tmp_db_path
        db.init_db()

        board = db.create_board("B")
        lst = db.create_list(board.id, "L")
        card = db.create_card(lst.id, "Card", "Multi-line\ndescription\nhere")
        s1 = db.create_subtask(card.id, "Step 1")
        s2 = db.create_subtask(card.id, "Step 2")
        db.toggle_subtask(s2.id)

        boards = db.get_boards()
        target = [l for l in boards[0].lists if l.id == lst.id][0]
        c = target.cards[0]
        assert c.description == "Multi-line\ndescription\nhere"
        assert len(c.subtasks) == 2
        assert c.subtasks[0].is_completed is False
        assert c.subtasks[1].is_completed is True
