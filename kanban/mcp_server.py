import sys
import json
import os

from kanban import db


class MCPServer:
    def __init__(self):
        self.tool_definitions = [
            {
                "name": "kanban_get_boards",
                "description": "List all boards with full nested state (lists, cards, subtasks)",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "kanban_create_board",
                "description": "Create a new board",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Board name"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "kanban_delete_board",
                "description": "Delete a board and all its lists/cards/subtasks",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "integer", "description": "Board ID"},
                    },
                    "required": ["board_id"],
                },
            },
            {
                "name": "kanban_create_list",
                "description": "Create a new list on a board",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "integer"},
                        "name": {"type": "string"},
                    },
                    "required": ["board_id", "name"],
                },
            },
            {
                "name": "kanban_update_list",
                "description": "Update list name",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "list_id": {"type": "integer"},
                        "name": {"type": "string"},
                    },
                    "required": ["list_id", "name"],
                },
            },
            {
                "name": "kanban_delete_list",
                "description": "Delete a list",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "list_id": {"type": "integer"},
                    },
                    "required": ["list_id"],
                },
            },
            {
                "name": "kanban_create_card",
                "description": "Create a new card in a list",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "list_id": {"type": "integer"},
                        "title": {"type": "string"},
                        "description": {"type": "string", "description": "Notes"},
                        "status": {
                            "type": "string",
                            "description": "Card status (pending, in_progress, completed, cancelled)",
                            "default": "pending",
                            "enum": ["pending", "in_progress", "completed", "cancelled"],
                        },
                        "priority": {
                            "type": "string",
                            "description": "Card priority (low, medium, high)",
                            "default": "medium",
                            "enum": ["low", "medium", "high"],
                        },
                    },
                    "required": ["list_id", "title"],
                },
            },
            {
                "name": "kanban_update_card",
                "description": "Update card title and/or description (notes)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "integer"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "status": {"type": "string", "description": "Card status (pending, in_progress, completed, cancelled)"},
                        "priority": {"type": "string", "description": "Card priority (low, medium, high)"},
                    },
                    "required": ["card_id"],
                },
            },
            {
                "name": "kanban_delete_card",
                "description": "Delete a card",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "integer"},
                    },
                    "required": ["card_id"],
                },
            },
            {
                "name": "kanban_move_card",
                "description": "Move a card to a different list at a position",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "integer"},
                        "list_id": {"type": "integer"},
                        "position": {"type": "integer"},
                    },
                    "required": ["card_id", "list_id", "position"],
                },
            },
            {
                "name": "kanban_create_subtask",
                "description": "Add a checklist item to a card",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "integer"},
                        "name": {"type": "string"},
                    },
                    "required": ["card_id", "name"],
                },
            },
            {
                "name": "kanban_toggle_subtask",
                "description": "Toggle subtask completion status",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "subtask_id": {"type": "integer"},
                    },
                    "required": ["subtask_id"],
                },
            },
            {
                "name": "kanban_delete_subtask",
                "description": "Delete a subtask",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "subtask_id": {"type": "integer"},
                    },
                    "required": ["subtask_id"],
                },
            },
        ]
        self.initialized = False

    def handle_message(self, raw: str) -> str | None:
        """Parse JSON-RPC message and return JSON response string (or None for notifications)."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return None
        result = self.handle_json_rpc(msg)
        return json.dumps(result) if result else None

    def handle_json_rpc(self, msg: dict) -> dict | None:
        """Handle a parsed JSON-RPC request dict and return response dict (or None for notifications)."""
        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            result = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "kanban-mcp", "version": "0.1.0"},
                },
            }
            return result
        elif method == "notifications/initialized":
            self.initialized = True
            return None
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": self.tool_definitions},
            }
        elif method == "tools/call":
            return self._handle_tools_call(msg_id, params)
        else:
            return self._error(msg_id, -32601, f"Method not found: {method}")

    def _handle_tools_call(self, msg_id, params):
        name = params.get("name", "")
        args = params.get("arguments", {})
        try:
            result = self._dispatch(name, args)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, default=str)}]
                },
            }
        except Exception as e:
            return self._error(msg_id, -32603, str(e))

    def _dispatch(self, name, args):
        if name == "kanban_get_boards":
            return [b.model_dump() for b in db.get_boards()]
        elif name == "kanban_create_board":
            return db.create_board(args["name"]).model_dump()
        elif name == "kanban_delete_board":
            db.delete_board(args["board_id"])
            return {"ok": True}
        elif name == "kanban_create_list":
            return db.create_list(args["board_id"], args["name"]).model_dump()
        elif name == "kanban_update_list":
            result = db.update_list(args["list_id"], args["name"])
            if result is None:
                raise ValueError(f"List {args['list_id']} not found")
            return result.model_dump()
        elif name == "kanban_delete_list":
            db.delete_list(args["list_id"])
            return {"ok": True}
        elif name == "kanban_create_card":
            return db.create_card(
                args["list_id"], args["title"],
                args.get("description", ""),
                status=args.get("status", "pending"),
                priority=args.get("priority", "medium"),
            ).model_dump()
        elif name == "kanban_update_card":
            result = db.update_card(
                args["card_id"],
                title=args.get("title"),
                description=args.get("description"),
                status=args.get("status"),
                priority=args.get("priority"),
            )
            if result is None:
                raise ValueError(f"Card {args['card_id']} not found")
            return result.model_dump()
        elif name == "kanban_delete_card":
            db.delete_card(args["card_id"])
            return {"ok": True}
        elif name == "kanban_move_card":
            db.move_card(args["card_id"], args["list_id"], args["position"])
            return {"ok": True}
        elif name == "kanban_create_subtask":
            return db.create_subtask(args["card_id"], args["name"]).model_dump()
        elif name == "kanban_toggle_subtask":
            result = db.toggle_subtask(args["subtask_id"])
            if result is None:
                raise ValueError(f"Subtask {args['subtask_id']} not found")
            return result.model_dump()
        elif name == "kanban_delete_subtask":
            db.delete_subtask(args["subtask_id"])
            return {"ok": True}
        else:
            raise ValueError(f"Unknown tool: {name}")

    def _error(self, msg_id, code, message):
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }


def main():
    db_path = os.environ.get("KANBAN_DB_PATH")
    if db_path:
        db.DB_PATH = db_path
    db.init_db()
    server = MCPServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        response = server.handle_message(line)
        if response:
            sys.stdout.write(response + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
