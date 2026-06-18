from pydantic import BaseModel
from typing import Optional


class Subtask(BaseModel):
    id: int
    card_id: int
    name: str
    is_completed: bool = False
    position: int = 0


class Card(BaseModel):
    id: int
    list_id: int
    title: str
    description: str = ""
    position: int = 0
    created_at: str = ""
    subtasks: list[Subtask] = []
    status: str = "pending"
    priority: str = "medium"


class List(BaseModel):
    id: int
    board_id: int
    name: str
    position: int = 0
    cards: list[Card] = []


class Board(BaseModel):
    id: int
    name: str
    created_at: str = ""
    lists: list[List] = []


class CreateBoard(BaseModel):
    name: str


class CreateList(BaseModel):
    board_id: int
    name: str


class CreateCard(BaseModel):
    list_id: int
    title: str
    description: str = ""


class UpdateCard(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None


class MoveCard(BaseModel):
    list_id: int
    position: int


class CreateSubtask(BaseModel):
    name: str


class ToggleSubtask(BaseModel):
    is_completed: bool
