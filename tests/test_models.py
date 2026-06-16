"""Tests for kanban Pydantic models."""

import pytest
from pydantic import ValidationError

from kanban.models import (
    Board,
    Card,
    List,
    Subtask,
    CreateBoard,
    CreateList,
    CreateCard,
    UpdateCard,
    MoveCard,
    CreateSubtask,
    ToggleSubtask,
)


class TestSubtask:
    def test_create_with_all_fields(self):
        subtask = Subtask(id=1, card_id=2, name="Write tests", is_completed=True, position=3)
        assert subtask.id == 1
        assert subtask.card_id == 2
        assert subtask.name == "Write tests"
        assert subtask.is_completed is True
        assert subtask.position == 3

    def test_default_is_completed(self):
        subtask = Subtask(id=1, card_id=2, name="Write tests")
        assert subtask.is_completed is False

    def test_default_position(self):
        subtask = Subtask(id=1, card_id=2, name="Write tests")
        assert subtask.position == 0


class TestCard:
    def test_create_with_subtasks(self):
        subtasks = [
            Subtask(id=1, card_id=1, name="Subtask 1"),
            Subtask(id=2, card_id=1, name="Subtask 2"),
        ]
        card = Card(id=1, list_id=1, title="Test Card", subtasks=subtasks)
        assert card.id == 1
        assert card.list_id == 1
        assert card.title == "Test Card"
        assert len(card.subtasks) == 2
        assert card.subtasks[0].name == "Subtask 1"
        assert card.subtasks[1].name == "Subtask 2"

    def test_empty_subtasks(self):
        card = Card(id=1, list_id=1, title="Empty Card")
        assert card.subtasks == []

    def test_description_default(self):
        card = Card(id=1, list_id=1, title="Card")
        assert card.description == ""

    def test_position_default(self):
        card = Card(id=1, list_id=1, title="Card")
        assert card.position == 0

    def test_created_at_default(self):
        card = Card(id=1, list_id=1, title="Card")
        assert card.created_at == ""


class TestList:
    def test_create_with_cards(self):
        cards = [
            Card(id=1, list_id=1, title="Card A"),
            Card(id=2, list_id=1, title="Card B"),
        ]
        lst = List(id=1, board_id=1, name="To Do", cards=cards)
        assert lst.id == 1
        assert lst.board_id == 1
        assert lst.name == "To Do"
        assert len(lst.cards) == 2

    def test_empty_cards(self):
        lst = List(id=1, board_id=1, name="To Do")
        assert lst.cards == []

    def test_position_default(self):
        lst = List(id=1, board_id=1, name="To Do")
        assert lst.position == 0


class TestBoard:
    def test_create_with_lists(self):
        lists = [
            List(id=1, board_id=1, name="To Do"),
            List(id=2, board_id=1, name="Done"),
        ]
        board = Board(id=1, name="Project Alpha", lists=lists)
        assert board.id == 1
        assert board.name == "Project Alpha"
        assert len(board.lists) == 2
        assert board.lists[0].name == "To Do"
        assert board.lists[1].name == "Done"

    def test_empty_lists(self):
        board = Board(id=1, name="Empty Board")
        assert board.lists == []

    def test_nested_hierarchy(self):
        """Test full Board -> List -> Card -> Subtask hierarchy."""
        subtask = Subtask(id=1, card_id=1, name="Fix bug")
        card = Card(id=1, list_id=1, title="Bug fix", subtasks=[subtask])
        lst = List(id=1, board_id=1, name="In Progress", cards=[card])
        board = Board(id=1, name="Sprint 1", lists=[lst])

        assert board.lists[0].cards[0].subtasks[0].name == "Fix bug"

    def test_multiple_lists_and_cards(self):
        """Test board with multiple lists, each with multiple cards."""
        lst1 = List(
            id=1, board_id=1, name="To Do",
            cards=[
                Card(id=1, list_id=1, title="Task 1"),
                Card(id=2, list_id=1, title="Task 2"),
            ],
        )
        lst2 = List(
            id=2, board_id=1, name="Done",
            cards=[
                Card(id=3, list_id=2, title="Task 3"),
            ],
        )
        board = Board(id=1, name="Sprint 2", lists=[lst1, lst2])
        assert len(board.lists) == 2
        assert len(board.lists[0].cards) == 2
        assert len(board.lists[1].cards) == 1
        assert board.lists[1].cards[0].title == "Task 3"


class TestCreateBoard:
    def test_valid_name(self):
        req = CreateBoard(name="New Board")
        assert req.name == "New Board"


class TestCreateList:
    def test_valid(self):
        req = CreateList(board_id=1, name="To Do")
        assert req.board_id == 1
        assert req.name == "To Do"


class TestCreateCard:
    def test_required_fields(self):
        req = CreateCard(list_id=1, title="New Card")
        assert req.list_id == 1
        assert req.title == "New Card"

    def test_default_description(self):
        req = CreateCard(list_id=1, title="New Card")
        assert req.description == ""


class TestUpdateCard:
    def test_all_fields(self):
        req = UpdateCard(title="Updated", description="New desc")
        assert req.title == "Updated"
        assert req.description == "New desc"

    def test_optional_fields_default_to_none(self):
        req = UpdateCard()
        assert req.title is None
        assert req.description is None

    def test_partial_update(self):
        req = UpdateCard(title="Only title")
        assert req.title == "Only title"
        assert req.description is None


class TestMoveCard:
    def test_valid(self):
        req = MoveCard(list_id=2, position=0)
        assert req.list_id == 2
        assert req.position == 0


class TestCreateSubtask:
    def test_valid(self):
        req = CreateSubtask(name="Subtask name")
        assert req.name == "Subtask name"


class TestToggleSubtask:
    def test_complete(self):
        req = ToggleSubtask(is_completed=True)
        assert req.is_completed is True

    def test_incomplete(self):
        req = ToggleSubtask(is_completed=False)
        assert req.is_completed is False


class TestSerialization:
    def test_subtask_round_trip(self):
        obj = Subtask(id=1, card_id=2, name="Test", is_completed=True, position=1)
        data = obj.model_dump()
        restored = Subtask.model_validate(data)
        assert restored == obj

    def test_card_round_trip(self):
        obj = Card(id=1, list_id=1, title="Card", subtasks=[
            Subtask(id=1, card_id=1, name="Sub"),
        ])
        data = obj.model_dump()
        restored = Card.model_validate(data)
        assert restored == obj

    def test_board_round_trip(self):
        obj = Board(id=1, name="Board", lists=[
            List(id=1, board_id=1, name="List", cards=[
                Card(id=1, list_id=1, title="Card"),
            ]),
        ])
        data = obj.model_dump()
        restored = Board.model_validate(data)
        assert restored == obj


class TestValidation:
    def test_create_board_empty_name(self):
        """Board name can be empty string."""
        req = CreateBoard(name="")
        assert req.name == ""

    def test_create_card_missing_required_fields(self):
        """CreateCard requires list_id and title."""
        with pytest.raises(ValidationError):
            CreateCard()

    def test_create_list_missing_required_fields(self):
        with pytest.raises(ValidationError):
            CreateList()

    def test_create_card_very_long_title(self):
        """Card with 500-char title should be accepted by Pydantic."""
        title = "A" * 500
        req = CreateCard(list_id=1, title=title)
        assert len(req.title) == 500

    def test_create_card_very_long_description(self):
        desc = "B" * 1000
        req = CreateCard(list_id=1, title="Test", description=desc)
        assert len(req.description) == 1000

    def test_move_card_negative_position(self):
        """Position can be 0 or negative (just an integer)."""
        req = MoveCard(list_id=1, position=-1)
        assert req.position == -1

    def test_update_card_empty(self):
        """UpdateCard with no fields set."""
        req = UpdateCard()
        assert req.title is None
        assert req.description is None

    def test_create_subtask_empty_name(self):
        req = CreateSubtask(name="")
        assert req.name == ""

    def test_create_board_with_whitespace_name(self):
        req = CreateBoard(name="  ")
        assert req.name == "  "


class TestNestedValidation:
    def test_card_subtasks_max_items(self):
        """Card can have many subtasks."""
        subtasks = [Subtask(id=i, card_id=1, name=f"Task {i}") for i in range(100)]
        card = Card(id=1, list_id=1, title="Big Card", subtasks=subtasks)
        assert len(card.subtasks) == 100

    def test_board_deep_nesting(self):
        """Deep nesting: Board with 10 lists, each with 10 cards."""
        lists = []
        for li in range(10):
            cards = [Card(id=ci, list_id=li, title=f"Card {ci}") for ci in range(10)]
            lists.append(List(id=li, board_id=1, name=f"List {li}", cards=cards))
        board = Board(id=1, name="Deep Board", lists=lists)
        assert len(board.lists) == 10
        assert len(board.lists[0].cards) == 10
        assert board.lists[9].cards[9].title == "Card 9"


class TestSerializationRoundTrip:
    def test_create_board_round_trip(self):
        obj = CreateBoard(name="New Board")
        data = obj.model_dump()
        restored = CreateBoard.model_validate(data)
        assert restored.name == "New Board"

    def test_update_card_round_trip(self):
        obj = UpdateCard(title="Updated", description="Desc")
        data = obj.model_dump()
        restored = UpdateCard.model_validate(data)
        assert restored.title == "Updated"
        assert restored.description == "Desc"

    def test_move_card_round_trip(self):
        obj = MoveCard(list_id=5, position=2000)
        data = obj.model_dump()
        restored = MoveCard.model_validate(data)
        assert restored.list_id == 5
        assert restored.position == 2000

    def test_create_subtask_round_trip(self):
        obj = CreateSubtask(name="Checklist item")
        data = obj.model_dump()
        restored = CreateSubtask.model_validate(data)
        assert restored.name == "Checklist item"

    def test_toggle_subtask_round_trip(self):
        obj = ToggleSubtask(is_completed=True)
        data = obj.model_dump()
        restored = ToggleSubtask.model_validate(data)
        assert restored.is_completed is True
