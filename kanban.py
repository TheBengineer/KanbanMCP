#!/usr/bin/env python3
"""Kanban CLI — starts web server or MCP server."""

import sys

import uvicorn
from kanban import db
from kanban.web import app


def main():
    if len(sys.argv) < 2:
        print("Usage: python kanban.py [web|mcp]")
        print("  web  — Start the web UI at http://localhost:8080")
        print("  mcp  — Start the MCP server on stdio (for opencode)")
        sys.exit(1)

    mode = sys.argv[1]
    db.init_db()

    if mode == "web":
        print("Starting kanban web server on http://localhost:8080")
        uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
    elif mode == "mcp":
        from kanban.mcp_server import main as mcp_main

        mcp_main()
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python kanban.py [web|mcp]")
        sys.exit(1)


if __name__ == "__main__":
    main()
