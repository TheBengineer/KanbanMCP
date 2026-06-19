#!/usr/bin/env python3
"""Kanban CLI — starts web server (default), MCP stdio proxy, or backup."""

import os
import sys
import time

import uvicorn
from kanban import db
from kanban.web import app


def _mcp_proxy():
    """Read JSON-RPC from stdin, POST to localhost:8080/mcp, write to stdout."""
    import json
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = Request(
            "http://localhost:8080/mcp",
            data=line.encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(req) as resp:
                body = resp.read()
                if body and body.strip():
                    sys.stdout.write(body.decode().strip() + "\n")
                    sys.stdout.flush()
        except URLError as e:
            msg = f"Web server unreachable (http://localhost:8080): {e.reason}"
            print(msg, file=sys.stderr)
            try:
                req_id = json.loads(line).get("id")
            except json.JSONDecodeError:
                req_id = None
            err = json.dumps({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": "Server unavailable. Start with `python kanban.py` first."},
            })
            sys.stdout.write(err + "\n")
            sys.stdout.flush()


def _backup():
    import shutil
    from datetime import datetime

    backup_dir = sys.argv[2] if len(sys.argv) > 2 else "backups"
    keep_days = int(sys.argv[3]) if len(sys.argv) > 3 else 30

    db.init_db()

    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(backup_dir, f"kanban-{ts}.db")
    shutil.copy2(db.DB_PATH, dest)
    size = os.path.getsize(dest)
    print(f"Backup saved: {dest} ({size / 1024:.1f} KB)")

    now = time.time()
    cutoff = now - keep_days * 86400
    pruned = 0
    for entry in os.listdir(backup_dir):
        path = os.path.join(backup_dir, entry)
        if os.path.isfile(path) and entry.startswith("kanban-") and entry.endswith(".db"):
            if os.path.getmtime(path) < cutoff:
                os.unlink(path)
                pruned += 1
    if pruned:
        print(f"Pruned {pruned} old backup(s) (retention: {keep_days} days)")
    remaining = sum(
        1 for e in os.listdir(backup_dir)
        if os.path.isfile(os.path.join(backup_dir, e))
        and e.startswith("kanban-") and e.endswith(".db")
    )
    print(f"Backups retained: {remaining}")


def main():
    db.init_db()

    if len(sys.argv) < 2 or sys.argv[1] == "web":
        if len(sys.argv) >= 2 and sys.argv[1] == "web":
            print("Note: 'web' arg is now the default. Just run `python kanban.py`.", file=sys.stderr)
        print("Starting kanban web server on http://localhost:8080")
        uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
    elif sys.argv[1] == "mcp":
        _mcp_proxy()
    elif sys.argv[1] == "backup":
        _backup()
    else:
        print(f"Unknown mode: {sys.argv[1]}")
        print("Usage: python kanban.py [web|mcp|backup [backup_dir] [keep_days]]")
        sys.exit(1)


if __name__ == "__main__":
    main()
