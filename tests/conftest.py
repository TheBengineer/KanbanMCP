import pytest
import os
import tempfile


@pytest.fixture
def tmp_db_path():
    """Create a temporary SQLite database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def app():
    """Import FastAPI app - import is inside fixture to avoid side effects."""
    from kanban.web import app
    return app


@pytest.fixture
def tclient(tmp_db_path):
    """Fixture: patch DB path and create fresh TestClient per test."""
    from fastapi.testclient import TestClient
    from kanban import db
    from kanban.web import app
    db.DB_PATH = tmp_db_path
    with TestClient(app) as client:
        yield client


@pytest.fixture
def populated_db(tmp_db_path):
    """Create a populated temp database with 1 board, 2 lists, 3 cards, 2 subtasks.
    Returns the board ID for use in tests."""
    from kanban import db as kanban_db
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()

    board = kanban_db.create_board("Test Board")
    list1 = kanban_db.create_list(board.id, "To Do")
    list2 = kanban_db.create_list(board.id, "Done")

    card1 = kanban_db.create_card(list1.id, "Task 1", "First task notes")
    card2 = kanban_db.create_card(list1.id, "Task 2")
    card3 = kanban_db.create_card(list2.id, "Task 3", "Completed task")

    kanban_db.create_subtask(card1.id, "Subtask A")
    kanban_db.create_subtask(card1.id, "Subtask B")

    return {
        "board": board,
        "lists": [list1, list2],
        "cards": [card1, card2, card3],
    }


@pytest.fixture
def populated_tclient(tmp_db_path, tclient, populated_db):
    """Test client with pre-populated database."""
    return tclient


@pytest.fixture
def mcp_server(tmp_db_path):
    """Start MCP server as subprocess with temp database."""
    import subprocess
    import sys
    import json

    env = os.environ.copy()
    env["KANBAN_DB_PATH"] = tmp_db_path

    # Initialize DB first
    from kanban import db as kanban_db
    kanban_db.DB_PATH = tmp_db_path
    kanban_db.init_db()

    proc = subprocess.Popen(
        [sys.executable, "-m", "kanban.mcp_server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, env=env,
    )

    # Perform initialize handshake
    init_msg = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "0.1.0"}}
    })
    proc.stdin.write(init_msg + "\n")
    proc.stdin.flush()
    resp_line = proc.stdout.readline()

    # Send initialized notification
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()

    def send_request(method_name, params=None):
        """Helper to send JSON-RPC request and get response."""
        req_id = 2  # Simple counter - works for sequential calls
        request = {
            "jsonrpc": "2.0", "id": req_id, "method": method_name,
            "params": params or {}
        }
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        return json.loads(line)

    yield proc, send_request, tmp_db_path

    proc.terminate()
    proc.wait()
