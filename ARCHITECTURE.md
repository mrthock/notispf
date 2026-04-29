# notispf — Architecture

notispf is a terminal text editor inspired by the ISPF editor from z/OS mainframes.
This document describes the internal structure for contributors and porters.

## Module Overview

```
notispf/
├── __main__.py          Entry points: main() for curses, main_qt() for GUI
├── _qt_main.py          Thin PyInstaller entry point for the Qt build
├── app.py               Top-level controller — owns all state, runs the curses event loop
├── app_qt.py            AppQt(App) subclass — replaces I/O layer with PyQt6
├── buffer.py            Pure data layer — lines, undo/redo, clipboard, file I/O
├── display.py           Curses rendering engine — the only file that touches curses
├── display_qt.py        PyQt6 rendering layer — EditorViewport, CommandInput, NotispfWindow
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

**Left/Right arrow navigation** — In text mode, pressing Left when `cursor_col == 0`
enters prefix mode for the current line instead of stopping at the column boundary.
In prefix mode, pressing Right exits back to text mode at column 0. This mirrors the
ISPF experience of moving fluidly between the prefix and text areas.

**ISPF prefix overlay** — While typing in prefix mode the line number stays visible.
Typed characters overtype it from the left (e.g. typing `D` on line 1 shows `D00001`).
Implemented in `_render()` by computing `(typed + line_num_str[len(typed):])[:6]`.
Only `prefix_input` (not the overlay string) is staged.

---

### `display.py` — Rendering

`Display` is the only file that calls curses. Everything else is curses-free.

**`ViewState`** is a plain dataclass that holds all rendering state:
cursor position, scroll offsets, mode flags (`command_mode`, `prefix_mode`,
`help_mode`, `hex_mode`, `show_command`), the live prefix input buffer, the
highlight pattern, etc. It is owned by `App` and passed into `Display.render()`
on every frame. `show_command` (default `True`) controls whether the command bar
row is visible; `command_mode` controls whether the cursor is focused there.

The render pipeline per frame:

1. `_render_status()` — row 0: status bar (filename, modified flag, line/total, cursor column, `[HEX]` indicator)
2. `_render_command_bar()` — row 1: always-visible command input (`===> ...`), shown when `show_command` is True
3. `_render_content()` or `_render_help()` — main content area (starts at row 2 when command bar is visible)
4. `_render_fkey_bar()` — second-to-last row: always-visible function key reference (`F1-HELP  F3-SAVE  F5-RFIND …`)
5. `_render_bottom()` — last row: status messages
6. `_place_cursor()` — moves the hardware cursor to the right position (row 1 when `command_mode`, otherwise into content)

**`build_view()`** converts the buffer into a flat list of view entries:
- `('line', buf_idx)` — a normal visible line
- `('fold', start, end, count)` — a run of excluded lines collapsed to one row

**Color pairs** are defined as module-level constants (`_CP_STATUS`, `_CP_PREFIX`,
etc.) and initialized once in `_init_curses()`. If `curses.can_change_color()`
returns True, a custom dark olive color (`_COLOR_DARK_OLIVE`, `#2d4a1e`) is
defined via `curses.init_color()` and used for the command bar background;
otherwise it falls back to `COLOR_GREEN`.

Pattern highlighting is handled per-line in `_render_line_text()`, which splits
each visible line into highlighted and non-highlighted spans and writes them with
different attributes.

---

### `display_qt.py` and `app_qt.py` — PyQt6 Layer

The Qt frontend follows the same architecture as the curses frontend: `AppQt` subclasses
`App` and overrides only the I/O methods; all business logic (prefix execution, command
parsing, find/change, undo/redo) is inherited unchanged.

**`display_qt.py`** contains three widgets:

- **`EditorViewport(QAbstractScrollArea)`** — custom `paintEvent` that draws the prefix
  column, text area, column ruler, and help screen using `QPainter`. Handles mouse clicks
  to position the cursor and enter prefix mode. Cursor is rendered as a blinking underline
  bar via a `QTimer`.
- **`CommandInput(QLineEdit)`** — the `===>` command bar. Overrides `event()` to intercept
  Tab/Backtab before Qt's focus-traversal machinery steals them.
- **`NotispfWindow(QMainWindow)`** — top-level window. Hosts the status label, command bar,
  editor viewport, function key bar label, and message bar. An event filter on `CommandInput`
  handles F3, F5, F6, Escape, and Down from the command bar.

**`app_qt.py`** (`AppQt`) overrides:

- `run()` — creates the `QApplication` and `NotispfWindow`, calls `qt_app.exec()`
- `_render()` — calls `window.refresh()` instead of `Display.render()`
- `_content_rows()` — delegates to `EditorViewport.content_rows()`
- `_handle_key_qt()`, `_handle_help_key_qt()`, `_handle_prefix_key_qt()` — Qt equivalents
  of the curses key handlers, using `Qt.Key` constants instead of `curses.KEY_*`

Tab and Backtab require `event()` overrides in both `CommandInput` and `EditorViewport`
because Qt's focus traversal consumes them before `keyPressEvent` sees them.

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
{"F": "FIND", "C": "CHANGE", "CAN": "CANCEL", "RESET": "CLEAR", "RES": "CLEAR"}
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

- **Linux** — curses works natively; Qt version distributed as an AppImage
- **macOS** — curses works natively; Qt version distributed as a `.dmg` containing a `.app` bundle
- **Windows** — the curses binary bundles `windows-curses`; Qt version distributed via an Inno Setup installer
- **z/OS USS** — install via `zopen` (see `github.com/mrthock/notispfport`).
  EBCDIC encoding is not handled by notispf — mount MVS datasets into the USS
  filesystem via DSFS before editing.

Distribution binaries are built by GitHub Actions on every `v*` tag using PyInstaller.
The Qt builds use `--collect-all PyQt6` to bundle all Qt platform plugins.
Icons are generated from `assets/icon.svg` by `scripts/make_icons.py` (requires Pillow).

The `display.py` / `display_qt.py` split is deliberate: all rendering is isolated in those
two files so that porting to a new UI toolkit only requires replacing the display layer.
