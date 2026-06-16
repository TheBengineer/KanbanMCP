---
name: kanban
triggers:
  - kanban
  - board
  - card
  - list
  - subtask
  - MCP
  - ticket
description: OpenCode skill for the Python kanban board — teaches MCP tool usage, data model invariants, and common pitfalls.
---

# Kanban Board Skill

This skill teaches LLM agents how to use the 13 kanban MCP tools correctly. It covers implicit invariants not found in source code, tool decision logic for choosing the right MCP call, and common anti-patterns to avoid when working with this Python kanban board.

## Architecture Invariants

These are NOT documented in the README or source. They are implicit design decisions you MUST follow.

### Connection Lifecycle (CRITICAL)
- Every DB operation opens a new SQLite connection, does work, then closes it.
- This is deliberate: web (FastAPI) + MCP (stdio) are separate processes sharing one SQLite via WAL mode.
- DO NOT add a persistent connection pool. It breaks the shared-process architecture.
- DO NOT add async SQLite. Same reason.
- DO NOT add in-memory caching. Cached data will be stale when the other process writes.

### Integer-Gap Positioning
- All entities use integer-gap positioning: 1000, 2000, 3000...
- `create_*` functions auto-position at `_next_position()` (rounds MAX(position) up to next 1000).
- `move_card(card_id, list_id, position)` takes an explicit position. Pass 1000 to go to top.
- After deletes, `_rebalance()` renumbers remaining items to clean 1000-gaps.
- Do NOT insert items at position 0. Use the create functions.

### Cascade Rules
- Deleting a board cascades to all its lists, cards, and subtasks.
- Deleting a list cascades to all its cards and subtasks.
- Deleting a card cascades to all its subtasks.
- Deleting a non-existent entity is idempotent (no error).

### ID Types
- All `*_id` parameters are integers.
- IDs are returned by create operations. Always capture them.
- Boards and lists can share names. Always use IDs, never match by name.

### Read-Before-Write Pattern
- Call `kanban_get_boards()` before any create/update/move operation to get current IDs.
- Never cache board state between invocations. Always read fresh.

### Error Patterns
- `IntegrityError` (500): Foreign key violation, e.g. creating subtask on a non-existent card.
- `404`: Entity not found, e.g. toggling a deleted subtask.
- `422`: FastAPI form validation failure, e.g. empty required string.
- MCP returns error codes: `-32601` for unknown tool, `-32603` for internal errors.

## Tool Decision Logic

Use this flow to decide which MCP tool to call based on user intent.

**Board operations:**
→ `kanban_get_boards()` first to list all boards
→ `kanban_create_board(name)` to add one
→ `kanban_delete_board(board_id)` to remove one (cascades)

**List operations** (require board_id from get_boards):
→ `kanban_create_list(board_id, name)` to add a column
→ `kanban_update_list(list_id, name)` to rename
→ `kanban_delete_list(list_id)` to remove (cascades)

**Card operations** (require list_id from get_boards):
→ `kanban_create_card(list_id, title, description?)` to add a card
→ `kanban_update_card(card_id, title?, description?)` to edit
→ `kanban_delete_card(card_id)` to remove (cascades)
→ `kanban_move_card(card_id, list_id, position)` to move between lists

**Subtask operations** (require card_id from get_boards):
→ `kanban_create_subtask(card_id, name)` to add a checklist item
→ `kanban_toggle_subtask(subtask_id)` to toggle completion
→ `kanban_delete_subtask(subtask_id)` to remove

## Anti-Patterns

❌ **Adding a persistent DB connection pool.** SQLite WAL mode with two processes means each operation must open and close its own connection. A pool would serve stale connections to the wrong process.

❌ **Converting to async SQLite or adding caching.** Same root cause: two processes sharing one file. The sync connection-per-operation pattern is correct.

❌ **Inserting items at position 0.** Use the `create_*` functions which auto-compute the correct position via `_next_position()`.

❌ **Matching boards or lists by name instead of ID.** Names are not unique. Always use IDs from `get_boards()`.
