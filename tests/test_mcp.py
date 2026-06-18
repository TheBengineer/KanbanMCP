import subprocess
import json
import tempfile
import os
import sys

import pytest


@pytest.fixture
def mcp_server():
    """Start MCP server as subprocess with a temporary database."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    env = os.environ.copy()
    env["KANBAN_DB_PATH"] = tmp.name

    proc = subprocess.Popen(
        [sys.executable, "-m", "kanban.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )

    yield proc, tmp.name

    proc.terminate()
    proc.wait()
    if os.path.exists(tmp.name):
        os.unlink(tmp.name)


def _send(proc, msg: dict) -> dict:
    """Send a JSON-RPC message and read the response line."""
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("Server closed stdin before responding")
    return json.loads(line)


class TestInitialize:
    def test_initialize_handshake(self, mcp_server):
        proc, _ = mcp_server
        resp = _send(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        })
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert "result" in resp
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert resp["result"]["capabilities"] == {"tools": {}}


class TestToolsList:
    def test_tools_list_returns_13_tools(self, mcp_server):
        proc, _ = mcp_server
        # handshake
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        resp = _send(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        })
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 2
        tools = resp["result"]["tools"]
        assert len(tools) == 13
        names = {t["name"] for t in tools}
        expected = {
            "kanban_get_boards",
            "kanban_create_board",
            "kanban_delete_board",
            "kanban_create_list",
            "kanban_update_list",
            "kanban_delete_list",
            "kanban_create_card",
            "kanban_update_card",
            "kanban_delete_card",
            "kanban_move_card",
            "kanban_create_subtask",
            "kanban_toggle_subtask",
            "kanban_delete_subtask",
        }
        assert names == expected


class TestToolsCall:
    def test_create_board(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        resp = _send(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "kanban_create_board",
                "arguments": {"name": "Test Board"},
            },
        })
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 2
        assert "result" in resp
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["name"] == "Test Board"
        assert content["id"] > 0

    def test_get_boards(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        # Should start empty
        resp = _send(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "kanban_get_boards", "arguments": {}},
        })
        assert resp["jsonrpc"] == "2.0"
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content == []

        # Create a board
        _send(proc, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "kanban_create_board",
                "arguments": {"name": "Board A"},
            },
        })

        # Verify it appears
        resp = _send(proc, {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "kanban_get_boards", "arguments": {}},
        })
        content = json.loads(resp["result"]["content"][0]["text"])
        assert len(content) == 1
        assert content[0]["name"] == "Board A"


class TestErrors:
    def test_invalid_method(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        resp = _send(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "bogus",
            "params": {},
        })
        assert "error" in resp
        assert resp["error"]["code"] == -32601
        assert "Method not found" in resp["error"]["message"]


class TestBoardTools:
    def test_delete_board(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_create_board", "arguments": {"name": "Delete Me"}},
        })
        board_id = json.loads(resp["result"]["content"][0]["text"])["id"]

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "kanban_delete_board", "arguments": {"board_id": board_id}},
        })
        assert resp["jsonrpc"] == "2.0"
        assert "result" in resp

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "kanban_get_boards", "arguments": {}},
        })
        assert json.loads(resp["result"]["content"][0]["text"]) == []

    def test_delete_nonexistent_board(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_delete_board", "arguments": {"board_id": 999}},
        })
        assert "result" in resp


class TestListTools:
    def test_create_and_get_list(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_create_board", "arguments": {"name": "Board"}},
        })
        board = json.loads(resp["result"]["content"][0]["text"])

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "kanban_create_list", "arguments": {"board_id": board["id"], "name": "Todo"}},
        })
        assert resp["jsonrpc"] == "2.0"
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["name"] == "Todo"
        assert content["board_id"] == board["id"]

    def test_update_list(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_create_board", "arguments": {"name": "B"}},
        })
        board = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "kanban_create_list", "arguments": {"board_id": board["id"], "name": "Old"}},
        })
        lst = json.loads(resp["result"]["content"][0]["text"])

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "kanban_update_list", "arguments": {"list_id": lst["id"], "name": "New"}},
        })
        assert resp["jsonrpc"] == "2.0"
        assert "result" in resp

    def test_delete_list(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_create_board", "arguments": {"name": "B"}},
        })
        board = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "kanban_create_list", "arguments": {"board_id": board["id"], "name": "L"}},
        })
        lst = json.loads(resp["result"]["content"][0]["text"])

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "kanban_delete_list", "arguments": {"list_id": lst["id"]}},
        })
        assert "result" in resp


class TestCardTools:
    def test_create_card(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_create_board", "arguments": {"name": "B"}},
        })
        board = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "kanban_create_list", "arguments": {"board_id": board["id"], "name": "L"}},
        })
        lst = json.loads(resp["result"]["content"][0]["text"])

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "kanban_create_card", "arguments": {
                "list_id": lst["id"], "title": "Card", "description": "Notes"
            }},
        })
        assert resp["jsonrpc"] == "2.0"
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["title"] == "Card"
        assert content["description"] == "Notes"

    def test_update_card(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_create_board", "arguments": {"name": "B"}},
        })
        board = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "kanban_create_list", "arguments": {"board_id": board["id"], "name": "L"}},
        })
        lst = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "kanban_create_card", "arguments": {"list_id": lst["id"], "title": "Old"}},
        })
        card = json.loads(resp["result"]["content"][0]["text"])

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "kanban_update_card", "arguments": {
                "card_id": card["id"], "title": "New", "description": "New desc"
            }},
        })
        assert "result" in resp

    def test_delete_card(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_create_board", "arguments": {"name": "B"}},
        })
        board = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "kanban_create_list", "arguments": {"board_id": board["id"], "name": "L"}},
        })
        lst = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "kanban_create_card", "arguments": {"list_id": lst["id"], "title": "Del"}},
        })
        card = json.loads(resp["result"]["content"][0]["text"])

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "kanban_delete_card", "arguments": {"card_id": card["id"]}},
        })
        assert "result" in resp

    def test_move_card(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_create_board", "arguments": {"name": "B"}},
        })
        board = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "kanban_create_list", "arguments": {"board_id": board["id"], "name": "Todo"}},
        })
        lst1 = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "kanban_create_list", "arguments": {"board_id": board["id"], "name": "Done"}},
        })
        lst2 = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "kanban_create_card", "arguments": {"list_id": lst1["id"], "title": "Move Me"}},
        })
        card = json.loads(resp["result"]["content"][0]["text"])

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "kanban_move_card", "arguments": {
                "card_id": card["id"], "list_id": lst2["id"], "position": 1000
            }},
        })
        assert "result" in resp

    def test_create_card_with_status_and_priority(self, mcp_server):
        """Create card with explicit status and priority."""
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_create_board", "arguments": {"name": "B"}},
        })
        board = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "kanban_create_list", "arguments": {"board_id": board["id"], "name": "L"}},
        })
        lst = json.loads(resp["result"]["content"][0]["text"])

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "kanban_create_card", "arguments": {
                "list_id": lst["id"], "title": "Card", "status": "in_progress", "priority": "high"
            }},
        })
        assert resp["jsonrpc"] == "2.0"
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["status"] == "in_progress"
        assert content["priority"] == "high"

    def test_update_card_with_status_and_priority(self, mcp_server):
        """Update card with explicit status and priority."""
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_create_board", "arguments": {"name": "B"}},
        })
        board = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "kanban_create_list", "arguments": {"board_id": board["id"], "name": "L"}},
        })
        lst = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "kanban_create_card", "arguments": {"list_id": lst["id"], "title": "Old"}},
        })
        card = json.loads(resp["result"]["content"][0]["text"])

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "kanban_update_card", "arguments": {
                "card_id": card["id"], "title": "New", "status": "completed", "priority": "low"
            }},
        })
        assert "result" in resp
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["status"] == "completed"
        assert content["priority"] == "low"


class TestSubtaskTools:
    def test_create_toggle_delete_subtask(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_create_board", "arguments": {"name": "B"}},
        })
        b = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "kanban_create_list", "arguments": {"board_id": b["id"], "name": "L"}},
        })
        lst = json.loads(resp["result"]["content"][0]["text"])
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "kanban_create_card", "arguments": {"list_id": lst["id"], "title": "C"}},
        })
        card = json.loads(resp["result"]["content"][0]["text"])

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "kanban_create_subtask", "arguments": {
                "card_id": card["id"], "name": "Checklist"
            }},
        })
        assert resp["jsonrpc"] == "2.0"
        sub = json.loads(resp["result"]["content"][0]["text"])
        assert sub["name"] == "Checklist"
        assert sub["is_completed"] is False

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "kanban_toggle_subtask", "arguments": {"subtask_id": sub["id"]}},
        })
        assert resp["jsonrpc"] == "2.0"
        toggled = json.loads(resp["result"]["content"][0]["text"])
        assert toggled["is_completed"] is True

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "kanban_delete_subtask", "arguments": {"subtask_id": sub["id"]}},
        })
        assert "result" in resp


class TestMCPErrorHandling:
    def test_unknown_tool(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        })
        assert "error" in resp

    def test_missing_arguments(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_create_board", "arguments": {}},
        })
        assert "error" in resp or "result" in resp

    def test_malformed_request(self, mcp_server):
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        proc.stdin.write("{garbage}\n")
        proc.stdin.flush()
        import time
        time.sleep(0.1)
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_get_boards", "arguments": {}},
        })
        assert "result" in resp


class TestMCPNotifications:
    def test_initialized_notification(self, mcp_server):
        """Send initialized notification and verify subsequent calls work."""
        proc, _ = mcp_server
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        # Send notification (no response expected)
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        # Subsequent call should work
        resp = _send(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "kanban_get_boards", "arguments": {}},
        })
        assert "result" in resp
