# notispf — Architecture

notispf is a terminal text editor inspired by the ISPF editor from z/OS mainframes.
This document describes the internal structure for contributors and porters.

## Module Overview

```
notispf/
├── __main__.py          Entry point (parses args, calls App.run())
├── app.py               Top-level controller — owns all state, runs the event loop
├── buffer.py            Pure data layer — lines, undo/redo, clipboard, file I/O
├── display.py           Curses rendering engine — the only file that touches curses
├── prefix.py            Prefix column state machine
├── find_change.py       FIND / CHANGE / EXCLUDE / DELETE engine
└── commands/
    ├── registry.py      CommandSpec registry and normalize() parser
    ├── line_cmds.py     D, I, R, C, M, A, B, O, >, <, HEX, HEXB, HEXA, UC, LC implementations
    ├── block_cmds.py    DD, CC, MM, RR, OO, >>, << implementations
    └── exclude_cmds.py  X, XX, S, SS implementations
```

## Layers and Responsibilities

### `buffer.py` — Data Layer

`Buffer` is the single source of truth for file content. It has no knowledge of
curses, the display, or the event loop.

Key types:

- **`Line`** — dataclass with `text`, `label`, `excluded`, `modified`
- **`Buffer`** — list of `Line` objects plus undo/redo stacks and a clipboard

Every mutation (`replace_line`, `insert_lines`, `delete_lines`, `repeat_lines`)
calls `_snapshot()` first, which deep-copies the current line list onto the undo
stack and clears the redo stack. `undo()` and `redo()` swap snapshots in and out.

**Edit group coalescing** — `begin_edit_group()` takes one snapshot and sets a
`_grouping` flag so that subsequent `_snapshot()` calls within the same group are
no-ops. `end_edit_group()` clears the flag. This ensures that:

- Consecutive keystrokes (typing, backspace, delete, Enter) share a single undo
  step — the group is started on the first keystroke and ended by any
  non-text-edit key (navigation, F-keys, mode changes).
- Multi-line operations (`CHANGE ALL`, `DELETE ALL`, block indent `>>`/`<<`,
  `UC`, `LC`, `OO`, etc.) wrap their inner loops in
  `begin_edit_group()` / `end_edit_group()` so they also undo atomically.

The clipboard (`push_clipboard` / `pop_clipboard`) is a plain list of strings.
It is not part of the undo stack — paste commands read the current clipboard value
at execution time.

Labels (`.A`, `.B`, etc.) are stored directly on `Line.label`. At most one line
holds any given label at a time; `set_label()` clears duplicates.

File I/O is UTF-8. Lines are stored without trailing newlines; `save_file()` adds
them back. There is no EBCDIC handling — on z/OS USS, use DSFS to mount MVS
datasets into the USS filesystem before editing.

---

### `commands/` — Command Handlers

Commands are registered against a `CommandRegistry` (in `registry.py`) as
`CommandSpec` objects, each carrying:

- `name` — canonical uppercase name (e.g. `"D"`, `"DD"`)
- `handler` — callable that receives `(buffer, line_idx, numeric_arg)` for
  single-line commands, or `(buffer, start_idx, end_idx, numeric_arg)` for blocks
- `is_block` — `True` for block commands (DD, CC, MM, …)

`normalize(raw)` parses the raw prefix string into `(cmd_name, numeric_arg)`:
- `"D5"` → `("D", 5)`
- `"DD"` → `("DD", 1)`
- `">4"` → `(">", 4)`
- `">>4"` → `(">>", 4)`

All handlers return an `EditorResult(success, message, cursor_hint,
cleared_prefixes)`. `cursor_hint` is an absolute buffer line index the app
should move the cursor to after execution.

---

### `prefix.py` — Prefix Area State Machine

`PrefixArea` mediates between user input and command dispatch.

State:

- **`_pending`** — `dict[line_idx → raw_input]` of staged-but-not-yet-executed
  commands (shown live in the prefix column while the user is still typing)
- **`_open_block`** — a `PrefixEntry` holding the first half of a block command
  (e.g. the first `DD`) while waiting for its partner

When `enter_prefix(line_idx, raw)` is called:

1. Normalize `raw` to `(cmd_name, numeric_arg)`.
2. If it is a single-line command, execute immediately and return an `EditorResult`.
3. If it is a block command and `_open_block` is `None`, store it and return
   `None` (waiting for partner).
4. If it is a block command and `_open_block` is set, check that the names match,
   then execute the block handler with `(buffer, start_idx, end_idx, numeric_arg)`.

Mismatched block partners (e.g. `DD` followed by `CC`) are rejected with an error
message and both entries cleared.

---

### `display.py` — Rendering

`Display` is the only file that calls curses. Everything else is curses-free.

**`ViewState`** is a plain dataclass that holds all rendering state:
cursor position, scroll offsets, mode flags (`command_mode`, `prefix_mode`,
`help_mode`, `hex_mode`), the live prefix input buffer, the highlight pattern,
etc. It is owned by `App` and passed into `Display.render()` on every frame.

The render pipeline per frame:

1. `_render_status()` — top status bar (filename, modified flag, line/total, cursor column, `[HEX]` indicator)
2. `_render_content()` or `_render_help()` — main content area
3. `_render_bottom()` — bottom row (command input or message)
4. `_place_cursor()` — moves the hardware cursor to the right position

**`build_view()`** converts the buffer into a flat list of view entries:
- `('line', buf_idx)` — a normal visible line
- `('fold', start, end, count)` — a run of excluded lines collapsed to one row

**Color pairs** are defined as module-level constants (`_CP_STATUS`, `_CP_PREFIX`,
etc.) and initialized once in `_init_curses()`. The 10 pairs use the 8 standard
curses colors plus `-1` (terminal default).

Pattern highlighting is handled per-line in `_render_line_text()`, which splits
each visible line into highlighted and non-highlighted spans and writes them with
different attributes.

---

### `app.py` — Controller

`App` owns all state and runs the curses event loop via `curses.wrapper`.

**Event dispatch** in `_handle_key()`:

1. If `command_mode` → `_handle_command_key()`
2. If `help_mode` → `_handle_help_key()`
3. If `prefix_mode` → `_handle_prefix_key()`
4. Otherwise → navigation and text editing keys

**Two-pass prefix execution** in `_execute_staged_prefixes()`:

Pass 1 runs source commands (everything except A/B/O/OO) in line order, so the
clipboard is populated. Pass 2 runs paste commands (A/B/O/OO). This ensures that
`CC` + `A` works correctly regardless of which line comes first on screen.

**Command line** (`_execute_command()`): raw input is uppercased, split with
`shlex`, and dispatched by the first token. An alias table maps short forms to
canonical names before dispatch:

```python
{"F": "FIND", "C": "CHANGE", "CAN": "CANCEL"}
```

---

### `find_change.py` — Search Engine

`FindChangeEngine` wraps `Buffer` with stateful find/change/exclude/delete
operations. It tracks the last-found position so that repeated `FIND` calls
advance through the file. All operations are case-insensitive by default and
accept an optional column constraint.

---

## Data Flow Summary

```
keystroke
    │
    ▼
App._handle_key()
    │
    ├─ prefix key ──► PrefixArea.enter_prefix()
    │                     │
    │                     ▼
    │              CommandRegistry → handler(Buffer, …)
    │
    ├─ command line ► App._execute_command()
    │                     │
    │                     ├─ buffer mutations (undo/redo, save …)
    │                     └─ FindChangeEngine (find/change/exclude/delete)
    │
    └─ text edit ──► Buffer.replace_line() / insert_lines() / delete_lines()
                          │
                          ▼ (_snapshot() is a no-op inside a begin/end_edit_group())
                      Buffer._snapshot()

App._render()
    │
    ▼
Display.render(Buffer, PrefixArea, ViewState)
```

---

## Adding a New Prefix Command

1. Write a handler in `notispf/commands/line_cmds.py` (or a new file):

```python
def cmd_trim(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    for i in range(line_idx, min(line_idx + count, len(buffer))):
        buffer.replace_line(i, buffer.lines[i].text.rstrip())
    return EditorResult(success=True)
```

2. Register it in the same file's `register()` function:

```python
registry.register_line_cmd(CommandSpec("T", cmd_trim, description="Trim trailing whitespace"))
```

3. Add tests in `tests/test_line_cmds.py`.

No changes to `prefix.py`, `display.py`, or `app.py` are needed.

---

## Adding a New Command-Line Command

Add a new `if cmd == "MYCOMMAND":` block in `App._execute_command()` in
`app.py`. Return a string message to display in the status bar.

---

## Platform Notes

notispf runs on any platform with Python 3.11+ and curses:

- **Linux / macOS** — works natively
- **Windows** — the PyInstaller binary bundles `windows-curses`
- **z/OS USS** — install via `zopen` (see `github.com/mrthock/notispfport`).
  EBCDIC encoding is not handled by notispf — mount MVS datasets into the USS
  filesystem via DSFS before editing.

The `display.py` layer is deliberately isolated so that a future GUI front-end
would only need to replace that one file.
