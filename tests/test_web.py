"""Tests for the kanban web server (FastAPI + HTMX routes)."""

import pytest
from fastapi.testclient import TestClient
from kanban import db
from kanban.web import app


@pytest.fixture
def tclient(tmp_db_path):
    """Fixture: patch DB path and create a fresh TestClient per test."""
    db.DB_PATH = tmp_db_path
    with TestClient(app) as client:
        yield client


class TestIndex:
    def test_index_returns_html(self, tclient):
        resp = tclient.get("/")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")

    def test_empty_state(self, tclient):
        """No boards should show empty-state content."""
        resp = tclient.get("/")
        assert resp.status_code == 200
        assert "No boards yet" in resp.text


class TestBoardRoutes:
    def test_create_board(self, tclient):
        resp = tclient.post("/boards", data={"name": "My Board"})
        assert resp.status_code == 200
        boards = db.get_boards()
        assert len(boards) == 1
        assert boards[0].name == "My Board"

    def test_delete_board(self, tclient):
        board = db.create_board("To Delete")
        assert len(db.get_boards()) == 1
        resp = tclient.delete(f"/boards/{board.id}")
        assert resp.status_code == 200
        assert len(db.get_boards()) == 0


class TestListRoutes:
    def test_create_list(self, tclient):
        board = db.create_board("Test Board")
        resp = tclient.post(f"/boards/{board.id}/lists", data={"name": "Todo"})
        assert resp.status_code == 200
        boards = db.get_boards()
        assert len(boards[0].lists) == len(db.DEFAULT_LISTS) + 1
        assert boards[0].lists[-1].name == "Todo"

    def test_delete_list(self, tclient):
        board = db.create_board("Board")
        lst = db.create_list(board.id, "List")
        resp = tclient.delete(f"/lists/{lst.id}")
        assert resp.status_code == 200
        boards = db.get_boards()
        assert len(boards[0].lists) == len(db.DEFAULT_LISTS)


class TestCardRoutes:
    def test_create_card(self, tclient):
        board = db.create_board("Board")
        lst = db.create_list(board.id, "List")
        resp = tclient.post(f"/lists/{lst.id}/cards", data={"title": "Task 1", "description": "Details"})
        assert resp.status_code == 200
        boards = db.get_boards()
        target = [l for l in boards[0].lists if l.id == lst.id][0]
        assert len(target.cards) == 1
        assert target.cards[0].title == "Task 1"

    def test_delete_card(self, tclient):
        board = db.create_board("B")
        lst = db.create_list(board.id, "L")
        card = db.create_card(lst.id, "To Delete")
        resp = tclient.delete(f"/cards/{card.id}")
        assert resp.status_code == 200
        boards = db.get_boards()
        target = [l for l in boards[0].lists if l.id == lst.id][0]
        assert len(target.cards) == 0

    def test_move_card(self, tclient):
        board = db.create_board("Board")
        lst1 = db.create_list(board.id, "Todo")
        lst2 = db.create_list(board.id, "Done")
        card = db.create_card(lst1.id, "Moving Card")
        resp = tclient.patch(
            f"/cards/{card.id}/move",
            data={"list_id": lst2.id, "position": 1000},
        )
        assert resp.status_code == 200
        boards = db.get_boards()
        l1 = [l for l in boards[0].lists if l.id == lst1.id][0]
        l2 = [l for l in boards[0].lists if l.id == lst2.id][0]
        assert len(l1.cards) == 0  # Todo is empty
        assert len(l2.cards) == 1  # Done has the card
        assert l2.cards[0].id == card.id

    def test_get_card_modal(self, tclient):
        board = db.create_board("B")
        lst = db.create_list(board.id, "L")
        card = db.create_card(lst.id, "Modal Card", "Some notes")
        resp = tclient.get(f"/cards/{card.id}")
        assert resp.status_code == 200
        assert "Edit Card" in resp.text
        assert "Modal Card" in resp.text
        assert "Some notes" in resp.text

    def test_update_card(self, tclient):
        board = db.create_board("B")
        lst = db.create_list(board.id, "L")
        card = db.create_card(lst.id, "Original", "Original desc")
        resp = tclient.patch(
            f"/cards/{card.id}",
            data={"title": "Updated", "description": "Updated desc"},
        )
        assert resp.status_code == 200
        boards = db.get_boards()
        target = [l for l in boards[0].lists if l.id == lst.id][0]
        updated = target.cards[0]
        assert updated.title == "Updated"
        assert updated.description == "Updated desc"

    def test_create_card_has_default_status_priority(self, tclient):
        """POST create card returns card with default status/pending, priority/medium."""
        board = db.create_board("Board")
        lst = db.create_list(board.id, "List")
        resp = tclient.post(f"/lists/{lst.id}/cards", data={"title": "Task"})
        assert resp.status_code == 200
        assert "Pending" in resp.text
        assert "medium" in resp.text

    def test_update_card_with_status_priority(self, tclient):
        """PATCH update card with status and priority changes them."""
        board = db.create_board("B")
        lst = db.create_list(board.id, "L")
        card = db.create_card(lst.id, "Original")
        resp = tclient.patch(
            f"/cards/{card.id}",
            data={"title": "Updated", "status": "in_progress", "priority": "high"},
        )
        assert resp.status_code == 200
        assert "In Progress" in resp.text
        assert "high" in resp.text

    def test_update_card_without_status_preserves_default(self, tclient):
        """PATCH without status/priority leaves defaults unchanged."""
        board = db.create_board("B")
        lst = db.create_list(board.id, "L")
        card = db.create_card(lst.id, "Card")
        resp = tclient.patch(
            f"/cards/{card.id}",
            data={"title": "New"},
        )
        assert resp.status_code == 200
        boards = db.get_boards()
        target = [l for l in boards[0].lists if l.id == lst.id][0]
        updated = target.cards[0]
        assert updated.status == "pending"
        assert updated.priority == "medium"


class TestSubtaskRoutes:
    @staticmethod
    def _list_by_name(name):
        """Find list by name on the only board in the test DB."""
        boards = db.get_boards()
        return [l for l in boards[0].lists if l.name == name][0]

    def test_create_subtask(self, tclient):
        board = db.create_board("B")
        lst = db.create_list(board.id, "L")
        card = db.create_card(lst.id, "C")
        resp = tclient.post(f"/cards/{card.id}/subtasks", data={"name": "Checklist item"})
        assert resp.status_code == 200
        target = self._list_by_name("L")
        assert len(target.cards[0].subtasks) == 1
        assert target.cards[0].subtasks[0].name == "Checklist item"

    def test_toggle_subtask(self, tclient):
        board = db.create_board("B")
        lst = db.create_list(board.id, "L")
        card = db.create_card(lst.id, "C")
        sub = db.create_subtask(card.id, "Toggle me")
        assert sub.is_completed is False
        resp = tclient.patch(f"/subtasks/{sub.id}/toggle")
        assert resp.status_code == 200
        target = self._list_by_name("L")
        toggled = target.cards[0].subtasks[0]
        assert toggled.is_completed is True

    def test_delete_subtask(self, tclient):
        board = db.create_board("B")
        lst = db.create_list(board.id, "L")
        card = db.create_card(lst.id, "C")
        sub = db.create_subtask(card.id, "Delete me")
        assert len([c for l in db.get_boards()[0].lists for c in l.cards if c.id == card.id]) == 1
        resp = tclient.delete(f"/subtasks/{sub.id}")
        assert resp.status_code == 200
        target = self._list_by_name("L")
        assert len(target.cards[0].subtasks) == 0


class TestUpdateList:
    def test_update_list_name(self, tclient):
        """Update list name via PATCH."""
        board = db.create_board("Board")
        lst = db.create_list(board.id, "Old Name")
        resp = tclient.patch(f"/lists/{lst.id}", data={"name": "New Name"})
        assert resp.status_code == 200
        boards = db.get_boards()
        updated = [l for l in boards[0].lists if l.id == lst.id][0]
        assert updated.name == "New Name"

    def test_update_nonexistent_list(self, tclient):
        """PATCH on non-existent list returns 404."""
        resp = tclient.patch("/lists/9999", data={"name": "Whatever"})
        assert resp.status_code == 404


class TestErrorHandling:
    def test_create_card_missing_title(self, tclient):
        """POST create card without title returns 422 or 200 with empty."""
        board = db.create_board("B")
        lst = db.create_list(board.id, "L")
        resp = tclient.post(f"/lists/{lst.id}/cards", data={})
        # Should either work (empty title allowed) or return 422
        assert resp.status_code in (200, 422)

    def test_create_board_empty_name(self, tclient):
        """Empty board name is rejected (422) by FastAPI Form validation."""
        resp = tclient.post("/boards", data={"name": ""})
        assert resp.status_code == 422

    def test_get_nonexistent_card(self, tclient):
        """GET non-existent card returns 404."""
        resp = tclient.get("/cards/9999")
        assert resp.status_code == 404

    def test_delete_nonexistent_card(self, tclient):
        """DELETE non-existent card returns 200 (idempotent)."""
        resp = tclient.delete("/cards/9999")
        assert resp.status_code == 200


class TestSubtaskEdgeCases:
    def test_create_subtask_empty_name(self, tclient):
        """Subtask with empty name is rejected (422) by FastAPI Form validation."""
        board = db.create_board("B")
        lst = db.create_list(board.id, "L")
        card = db.create_card(lst.id, "C")
        resp = tclient.post(f"/cards/{card.id}/subtasks", data={"name": ""})
        assert resp.status_code == 422

    def test_toggle_nonexistent_subtask(self, tclient):
        """Toggle non-existent subtask returns 404."""
        resp = tclient.patch("/subtasks/9999/toggle")
        assert resp.status_code == 404

    def test_delete_nonexistent_subtask(self, tclient):
        """DELETE non-existent subtask returns 404 (not found)."""
        resp = tclient.delete("/subtasks/9999")
        assert resp.status_code == 404

    def test_create_subtask_on_nonexistent_card(self, tclient):
        """POST subtask on non-existent card raises IntegrityError (FK constraint)."""
        with pytest.raises(Exception):
            tclient.post("/cards/9999/subtasks", data={"name": "Sub"})

    def test_delete_subtask_twice(self, tclient):
        """Deleting same subtask twice — second returns 404."""
        board = db.create_board("B")
        lst = db.create_list(board.id, "L")
        card = db.create_card(lst.id, "C")
        sub = db.create_subtask(card.id, "Sub")
        resp1 = tclient.delete(f"/subtasks/{sub.id}")
        assert resp1.status_code == 200
        resp2 = tclient.delete(f"/subtasks/{sub.id}")
        assert resp2.status_code == 404  # Already deleted


class TestFullCrudFlow:
    def test_create_board_then_list_then_card_then_subtask(self, tclient):
        """Full CRUD via web API: board -> list -> card -> subtask -> verify."""
        board = db.create_board("My Board")
        resp = tclient.post(f"/boards/{board.id}/lists", data={"name": "Todo"})
        assert resp.status_code == 200
        boards = db.get_boards()
        lst = [l for l in boards[0].lists if l.name == "Todo"][0]
        
        resp = tclient.post(f"/lists/{lst.id}/cards", data={"title": "Task", "description": "Notes"})
        assert resp.status_code == 200
        boards = db.get_boards()
        card = [l for l in boards[0].lists if l.name == "Todo"][0].cards[0]
        
        resp = tclient.post(f"/cards/{card.id}/subtasks", data={"name": "Check"})
        assert resp.status_code == 200
        
        # Final assertion
        boards = db.get_boards()
        assert len(boards) == 1
        assert len(boards[0].lists) == len(db.DEFAULT_LISTS) + 1
        todo = [l for l in boards[0].lists if l.name == "Todo"][0]
        assert len(todo.cards) == 1
        assert len(todo.cards[0].subtasks) == 1
        assert todo.cards[0].subtasks[0].name == "Check"


class TestChatMessages:
    def test_chat_section_in_card_html(self, tclient):
        board = db.create_board("Board")
        lst = db.create_list(board.id, "List")
        card = db.create_card(lst.id, "Card")
        resp = tclient.get(f"/board/{board.id}")
        assert resp.status_code == 200
        assert "Chat (0)" in resp.text

    def test_create_chat_message_via_web(self, tclient):
        board = db.create_board("Board")
        lst = db.create_list(board.id, "List")
        card = db.create_card(lst.id, "Card")
        resp = tclient.post(f"/cards/{card.id}/messages", data={"author": "Alice", "body": "Hello"})
        assert resp.status_code == 200

    def test_get_chat_messages_html(self, tclient):
        board = db.create_board("Board")
        lst = db.create_list(board.id, "List")
        card = db.create_card(lst.id, "Card")
        tclient.post(f"/cards/{card.id}/messages", data={"author": "Alice", "body": "Hello"})
        resp = tclient.get(f"/cards/{card.id}/messages")
        assert resp.status_code == 200
        assert "Hello" in resp.text

    def test_chat_message_nonexistent_card(self, tclient):
        resp = tclient.post("/cards/9999/messages", data={"author": "Alice", "body": "Hello"})
        assert resp.status_code == 404

    def test_chat_message_empty_body(self, tclient):
        board = db.create_board("Board")
        lst = db.create_list(board.id, "List")
        card = db.create_card(lst.id, "Card")
        resp = tclient.post(f"/cards/{card.id}/messages", data={"author": "Alice", "body": ""})
        assert resp.status_code == 422