"""Top-level application controller."""
from __future__ import annotations
import curses
import os
import shlex

from notispf.buffer import Buffer, Line
from notispf.commands.registry import CommandRegistry
from notispf.commands import line_cmds, block_cmds, exclude_cmds
from notispf.commands.line_cmds import line_to_hex, hex_to_line
from notispf.buffer import Line
from notispf.display import Display, ViewState, TEXT_OFFSET
from notispf.find_change import FindChangeEngine
from notispf.prefix import PrefixArea


_CMD_ALIASES: dict[str, str] = {
    "F": "FIND", "C": "CHANGE", "CAN": "CANCEL",
    "RESET": "CLEAR", "RES": "CLEAR",
}


def _build_registry() -> CommandRegistry:
    r = CommandRegistry()
    line_cmds.register(r)
    block_cmds.register(r)
    exclude_cmds.register(r)
    return r


class App:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.registry = _build_registry()
        self.buffer = Buffer(filepath) if os.path.exists(filepath) \
            else self._new_buffer(filepath)
        self.prefix_area = PrefixArea(self.buffer, self.registry)
        self.find_engine = FindChangeEngine(self.buffer)
        self.vs = ViewState(
            top_line=0,
            cursor_line=0,
            cursor_col=0,
            screen_rows=24,
            screen_cols=80,
        )
        self._quit_flag = False

    def _new_buffer(self, filepath: str) -> Buffer:
        buf = Buffer()
        buf.filepath = filepath
        return buf

    def run(self) -> None:
        curses.wrapper(self._main)

    def _main(self, stdscr) -> None:
        self.display = Display(stdscr)
        self._render()

        while True:
            key = stdscr.getch()
            if self._handle_key(key) or self._quit_flag:
                break
            self._render()

    def _render(self) -> None:
        rows, cols = self.display.stdscr.getmaxyx()
        self.vs.screen_rows = rows
        self.vs.screen_cols = cols
        self.vs.pending_prefixes = dict(self.prefix_area._pending)
        # Overlay typed chars onto the line number digits (ISPF behaviour: number stays visible)
        if self.vs.prefix_mode:
            line_num_str = f"{self.vs.cursor_line + 1:06}"
            typed = self.vs.prefix_input
            self.vs.pending_prefixes[self.vs.cursor_line] = (typed + line_num_str[len(typed):])[:6]
        if self.prefix_area._open_block:
            self.vs.open_block_line = self.prefix_area._open_block.line_idx
            self.vs.open_block_cmd = self.prefix_area._open_block.cmd_name
        else:
            self.vs.open_block_line = None
            self.vs.open_block_cmd = ""
        self.display.render(self.buffer, self.prefix_area, self.vs)

    def _handle_key(self, key: int) -> bool:
        """Return True to quit."""
        vs = self.vs

        if vs.command_mode:
            self.buffer.end_edit_group()
            return self._handle_command_key(key)

        if vs.help_mode:
            self.buffer.end_edit_group()
            return self._handle_help_key(key)

        if vs.prefix_mode:
            self.buffer.end_edit_group()
            return self._handle_prefix_key(key)

        # End any active edit group for non-text-edit keys
        _text_edit_keys = {curses.KEY_BACKSPACE, 127, curses.KEY_DC,
                           curses.KEY_ENTER, ord('\n'), ord('\r')}
        if key not in _text_edit_keys and not (32 <= key <= 126):
            self.buffer.end_edit_group()

        content_rows = self._content_rows()

        # Navigation
        if key == curses.KEY_UP:
            if vs.show_command and vs.cursor_line <= vs.top_line:
                vs.command_mode = True
                vs.message = ""
            else:
                self._move_cursor(-1)
        elif key == curses.KEY_DOWN:
            self._move_cursor(1)
        elif key in (curses.KEY_PPAGE, curses.KEY_F7):   # Page Up
            self._move_cursor(-content_rows)
        elif key in (curses.KEY_NPAGE, curses.KEY_F8):   # Page Down
            self._move_cursor(content_rows)
        elif key == curses.KEY_F10:         # Scroll left
            vs.col_offset = max(0, vs.col_offset - (vs.screen_cols - TEXT_OFFSET))
        elif key == curses.KEY_F11:         # Scroll right
            vs.col_offset += vs.screen_cols - TEXT_OFFSET
        elif key == curses.KEY_HOME:                # Home — focus command bar
            if not vs.show_command:
                vs.show_command = True
            vs.command_mode = True
            vs.message = ""
        elif key == ord('\x01'):                    # Ctrl-A — start of line
            vs.cursor_col = 0
            self._scroll_col_to_cursor()
        elif key == curses.KEY_END or key == ord('\x05'):   # End / Ctrl-E
            if self.buffer.lines:
                vs.cursor_col = len(self.buffer.lines[vs.cursor_line].text)
            self._scroll_col_to_cursor()
        elif key == curses.KEY_LEFT:
            if vs.cursor_col == 0:
                vs.prefix_mode = True
                vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")
                vs.message = "Type prefix command, Enter to execute, Esc to cancel"
            else:
                vs.cursor_col -= 1
                self._scroll_col_to_cursor()
        elif key == curses.KEY_RIGHT:
            if self.buffer.lines:
                vs.cursor_col = min(
                    len(self.buffer.lines[vs.cursor_line].text),
                    vs.cursor_col + 1)
            self._scroll_col_to_cursor()

        # F6: focus command bar (show it first if hidden)
        elif key == curses.KEY_F6:
            if not vs.show_command:
                vs.show_command = True
            vs.command_mode = True
            vs.message = ""

        # F1 = HELP
        elif key == curses.KEY_F1:
            vs.help_mode = True
            vs.help_scroll = 0
            vs.message = ""

        # F3 = FILE (save and quit)
        elif key == curses.KEY_F3:
            self._save_and_quit()
            return True

        # F12 = CANCEL (quit without saving)
        elif key == curses.KEY_F12:
            return True

        # F5 = RFIND (repeat last find)
        elif key == curses.KEY_F5:
            pattern = self.find_engine._last_find
            if not pattern:
                vs.message = "No previous FIND"
            else:
                pos = self.find_engine.find_next(pattern)
                if pos:
                    vs.cursor_line, vs.cursor_col = pos
                    self._scroll_to_cursor()
                    self._scroll_col_to_cursor()
                    vs.highlight_pattern = pattern
                    vs.message = f"Found: {pattern!r}"
                else:
                    vs.highlight_pattern = ""
                    vs.message = f"Not found: {pattern!r}"

        # Tab: advance to next line and enter its prefix area
        elif key == ord('\t'):
            self._move_cursor(1, skip_excluded=False)
            vs.prefix_mode = True
            vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")
            vs.message = "Type prefix command, Enter to execute, Esc to cancel"

        # Shift+Tab: go to command bar if at top line, otherwise move up into prefix
        elif key == curses.KEY_BTAB:
            if vs.show_command and vs.cursor_line <= vs.top_line:
                vs.command_mode = True
                vs.message = ""
            else:
                self._move_cursor(-1, skip_excluded=False)
                vs.prefix_mode = True
                vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")
                vs.message = "Type prefix command, Enter to execute, Esc to cancel"

        # Undo / Redo
        elif key == ord('\x1a'):  # Ctrl+Z
            vs.message = "Undone" if self.buffer.undo() else "Nothing to undo"
        elif key == ord('\x19'):  # Ctrl+Y
            vs.message = "Redone" if self.buffer.redo() else "Nothing to redo"

        # Text editing (Phase 6 — placeholder)
        elif key == curses.KEY_BACKSPACE or key == 127:
            self._backspace()
        elif key == curses.KEY_DC:
            self._delete_char()
        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            self._enter_key()
        elif 32 <= key <= 126:
            self._insert_char(chr(key))

        return False

    def _handle_help_key(self, key: int) -> bool:
        vs = self.vs
        rows, _ = self.display.stdscr.getmaxyx()
        content_rows = rows - 2
        max_scroll = max(0, len(self.display._HELP_LINES) - content_rows)
        if key in (curses.KEY_DOWN, curses.KEY_NPAGE, curses.KEY_F8):
            vs.help_scroll = min(vs.help_scroll + (content_rows if key != curses.KEY_DOWN else 1), max_scroll)
        elif key in (curses.KEY_UP, curses.KEY_PPAGE, curses.KEY_F7):
            vs.help_scroll = max(vs.help_scroll - (content_rows if key != curses.KEY_UP else 1), 0)
        else:
            vs.help_mode = False
            vs.help_scroll = 0
        return False

    def _handle_command_key(self, key: int) -> bool:
        vs = self.vs
        if key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            result_msg = self._execute_command(vs.command_input.strip())
            vs.command_input = ""
            vs.message = result_msg
        elif key == 27:  # Escape — unfocus but keep bar visible
            vs.command_mode = False
            vs.command_input = ""
            vs.message = ""
        elif key == curses.KEY_F6:  # F6 again — hide bar
            vs.show_command = False
            vs.command_mode = False
            vs.command_input = ""
            vs.message = ""
        elif key == curses.KEY_DOWN:  # down arrow — return to text at current position
            vs.command_mode = False
            vs.message = ""
        elif key == ord('\t'):  # Tab — go to prefix area of line 1
            vs.command_mode = False
            vs.cursor_line = 0
            vs.cursor_col = 0
            vs.prefix_mode = True
            vs.prefix_input = self.prefix_area._pending.get(0, "")
            self._scroll_to_cursor()
            vs.message = "Type prefix command, Enter to execute, Esc to cancel"
        elif key == curses.KEY_BACKSPACE or key == 127:
            vs.command_input = vs.command_input[:-1]
        elif 32 <= key <= 126:
            vs.command_input += chr(key)
        elif key == curses.KEY_F3:
            vs.command_mode = False
            self._save_and_quit()
            return True
        return False

    def _execute_command(self, raw: str) -> str:
        if not raw:
            return ""
        try:
            tokens = shlex.split(raw)
        except ValueError:
            return f"Parse error: {raw}"
        if not tokens:
            return ""

        cmd = _CMD_ALIASES.get(tokens[0].upper(), tokens[0].upper())
        upper_tokens = [t.upper() for t in tokens]

        if cmd == "UNDO":
            return "Undone" if self.buffer.undo() else "Nothing to undo"

        if cmd == "REDO":
            return "Redone" if self.buffer.redo() else "Nothing to redo"

        if cmd == "HEX":
            sub = upper_tokens[1] if len(upper_tokens) > 1 else ""
            if sub == "ON":
                if self.vs.hex_mode:
                    return "Already in HEX mode"
                self.buffer._snapshot()
                for i, line in enumerate(self.buffer.lines):
                    self.buffer.lines[i] = Line(
                        text=line_to_hex(line.text), label=line.label, modified=True)
                self.buffer.modified = True
                self.vs.hex_mode = True
                return "HEX ON — use HEX OFF to restore"
            elif sub == "OFF":
                if not self.vs.hex_mode:
                    return "Not in HEX mode"
                new_lines = []
                bad = []
                for i, line in enumerate(self.buffer.lines):
                    try:
                        new_lines.append(Line(
                            text=hex_to_line(line.text), label=line.label, modified=True))
                    except ValueError:
                        bad.append(i + 1)
                if bad:
                    return f"Invalid hex on line(s): {', '.join(str(n) for n in bad[:5])}"
                self.buffer._snapshot()
                self.buffer.lines = new_lines
                self.buffer.modified = True
                self.vs.hex_mode = False
                return "HEX OFF"
            else:
                return "Usage: HEX ON | HEX OFF"

        if cmd == "HELP":
            self.vs.help_mode = True
            self.vs.help_scroll = 0
            return ""

        if cmd == "CLEAR":
            self.vs.highlight_pattern = ""
            return "Highlighting cleared"

        if cmd == "COLS":
            self.vs.show_cols = not self.vs.show_cols
            return "Column ruler on" if self.vs.show_cols else "Column ruler off"

        if cmd in ("CANCEL", "QUIT"):
            self._quit_flag = True
            return ""

        if cmd == "SHOW" and "ALL" in upper_tokens:
            self.buffer.show_all()
            return "All lines shown"

        if cmd == "COPY":
            if len(tokens) < 2:
                return "Usage: COPY filename"
            dest = tokens[1]
            try:
                saved_filepath = self.buffer.filepath
                saved_modified = self.buffer.modified
                self.buffer.save_file(dest)
                self.buffer.filepath = saved_filepath
                self.buffer.modified = saved_modified
                return f"Copied to: {dest}"
            except Exception as e:
                return f"Copy error: {e}"

        if cmd in ("SAVE", "FILE"):
            try:
                self.buffer.save_file()
                if cmd == "FILE":
                    self._quit_flag = True
                return f"Saved: {self.buffer.filepath}"
            except Exception as e:
                return f"Save error: {e}"

        if cmd == "EXCLUDE":
            if len(tokens) < 2:
                return "Usage: EXCLUDE 'pattern' [ALL | n]"
            pattern = tokens[1]
            rest = upper_tokens[2:]
            if rest:
                if rest[0] == "ALL":
                    limit = None
                else:
                    try:
                        limit = int(rest[0])
                    except ValueError:
                        return f"Invalid count: {rest[0]}"
            else:
                limit = 1
            n = self.find_engine.exclude_matching(pattern, limit=limit)
            return f"{n} line(s) excluded" if n else f"Not found: {pattern!r}"

        if cmd == "DELETE":
            if len(tokens) < 2:
                return "Usage: DELETE 'pattern' [ALL | n] | DELETE X ALL | DELETE NX ALL"

            qualifier = upper_tokens[1]

            # DELETE X ALL — delete all excluded lines
            if qualifier == "X":
                n = self.find_engine.delete_excluded()
                return f"{n} excluded line(s) deleted" if n else "No excluded lines"

            # DELETE NX ALL — delete all non-excluded lines
            if qualifier == "NX":
                n = self.find_engine.delete_non_excluded()
                return f"{n} non-excluded line(s) deleted" if n else "No non-excluded lines"

            # DELETE "pattern" [ALL | n]
            pattern = tokens[1]
            rest = upper_tokens[2:]
            if rest:
                if rest[0] == "ALL":
                    limit = None
                else:
                    try:
                        limit = int(rest[0])
                    except ValueError:
                        return f"Invalid count: {rest[0]}"
            else:
                limit = 1   # no qualifier — delete next match only
            n = self.find_engine.delete_matching(pattern, limit=limit)
            return f"{n} line(s) deleted" if n else f"Not found: {pattern!r}"

        if cmd == "FIND":
            if len(tokens) < 2:
                return "Usage: FIND <text> [column]"
            pattern = tokens[1]
            find_col = None
            if len(tokens) > 2:
                last = tokens[-1]
                if last.isdigit() and int(last) >= 1:
                    find_col = int(last)
            pos = self.find_engine.find_next(pattern, col=find_col)
            col_msg = f" at column {find_col}" if find_col else ""
            if pos:
                self.vs.cursor_line, self.vs.cursor_col = pos
                self._scroll_to_cursor()
                self._scroll_col_to_cursor()
                self.vs.highlight_pattern = pattern
                return f"Found: {pattern!r}{col_msg}"
            self.vs.highlight_pattern = ""
            return f"Not found: {pattern!r}{col_msg}"

        if cmd == "CHANGE":
            if len(tokens) < 3:
                return "Usage: CHANGE 'old' 'new' [ALL] [.lbl1 .lbl2] [column]"
            old, new = tokens[1], tokens[2]
            rest = upper_tokens[3:]
            # Extract optional column number — any token that is a positive integer
            change_col = None
            rest_no_col = []
            for t in rest:
                if t.isdigit() and int(t) >= 1:
                    change_col = int(t)
                else:
                    rest_no_col.append(t)
            rest = rest_no_col
            try:
                if "ALL" in rest:
                    labels = [t for t in rest if t.startswith(".")]
                    if len(labels) >= 2:
                        n = self.find_engine.change_in_range(
                            old, new, labels[0], labels[1], col=change_col)
                    else:
                        n = self.find_engine.change_all(old, new, col=change_col)
                    if n:
                        self.vs.highlight_pattern = new
                    return f"{n} change(s) made"
                else:
                    labels = [t for t in rest if t.startswith(".")]
                    if len(labels) >= 2:
                        n = self.find_engine.change_in_range(
                            old, new, labels[0], labels[1], col=change_col)
                        if n:
                            self.vs.highlight_pattern = new
                        return f"{n} change(s) made"
                    n = self.find_engine.change_next(old, new, col=change_col)
                    if n:
                        self.vs.highlight_pattern = new
                    return f"{n} change(s) made" if n else f"Not found: {old!r}"
            except ValueError as e:
                return str(e)

        return f"Unknown command: {cmd}"

    def _handle_prefix_key(self, key: int) -> bool:
        vs = self.vs

        if key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            # Save current line's input, then execute all staged prefixes
            self._stage_current_prefix()
            vs.prefix_mode = False
            vs.prefix_input = ""
            vs.message = ""
            self._execute_staged_prefixes()

        elif key == curses.KEY_UP:
            self._stage_current_prefix()
            self._move_cursor(-1, skip_excluded=False)
            vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")

        elif key == curses.KEY_DOWN:
            self._stage_current_prefix()
            self._move_cursor(1, skip_excluded=False)
            vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")

        elif key == 27:
            # Escape: cancel prefix mode and clear all staged prefixes
            vs.prefix_mode = False
            vs.prefix_input = ""
            vs.message = ""
            self.prefix_area._pending.clear()
            self.prefix_area.cancel_open_block()

        elif key == ord('\t'):
            # Tab: prefix(N) -> text(N)
            self._stage_current_prefix()
            vs.prefix_mode = False
            vs.prefix_input = ""
            vs.message = ""

        elif key == curses.KEY_BTAB:
            # Shift+Tab: prefix(N) -> text(N-1)
            self._stage_current_prefix()
            vs.prefix_mode = False
            vs.prefix_input = ""
            vs.message = ""
            self._move_cursor(-1, skip_excluded=False)

        elif key == curses.KEY_HOME:
            vs.prefix_mode = False
            vs.prefix_input = ""
            vs.message = ""
            if not vs.show_command:
                vs.show_command = True
            vs.command_mode = True

        elif key == curses.KEY_RIGHT:
            self._stage_current_prefix()
            vs.prefix_mode = False
            vs.prefix_input = ""
            vs.message = ""
            vs.cursor_col = 0

        elif key == curses.KEY_BACKSPACE or key == 127:
            vs.prefix_input = vs.prefix_input[:-1]

        elif 32 <= key <= 126 and len(vs.prefix_input) < 6:
            vs.prefix_input += chr(key)

        return False

    def _stage_current_prefix(self) -> None:
        """Save the current prefix input into the pending dict without executing."""
        vs = self.vs
        raw = vs.prefix_input.strip()
        if raw:
            self.prefix_area._pending[vs.cursor_line] = raw
        else:
            self.prefix_area._pending.pop(vs.cursor_line, None)

    def _execute_staged_prefixes(self) -> None:
        """Execute all pending prefix commands.

        Two passes: source commands (MM, CC, D, I, R, C, M) first so the
        clipboard is populated before paste commands (A, B) run.
        """
        vs = self.vs
        last_message = ""
        pending = dict(self.prefix_area._pending)
        paste_cmds = {"A", "B", "O", "OO"}
        # If a block command is already waiting for its partner, skip re-entering
        # that line — calling enter_prefix on it again would pair it with itself.
        open_block_line = self.prefix_area._open_block.line_idx \
            if self.prefix_area._open_block else None

        # Pass 1: everything except A/B, in line order
        for line_idx in sorted(pending.keys()):
            if line_idx == open_block_line:
                continue
            raw = pending[line_idx]
            cmd_name, _ = self.prefix_area.registry.normalize(raw)
            if cmd_name in paste_cmds:
                continue
            result = self.prefix_area.enter_prefix(line_idx, raw)
            if result is not None:
                if result.message:
                    last_message = result.message
                if result.cursor_hint is not None:
                    vs.cursor_line = max(0, min(result.cursor_hint, len(self.buffer) - 1))
                    self._scroll_to_cursor()
            else:
                last_message = "Waiting for block partner..."

        # Pass 2: paste commands (A/B), in line order
        for line_idx in sorted(pending.keys()):
            raw = pending[line_idx]
            cmd_name, _ = self.prefix_area.registry.normalize(raw)
            if cmd_name not in paste_cmds:
                continue
            result = self.prefix_area.enter_prefix(line_idx, raw)
            if result is not None:
                if result.message:
                    last_message = result.message
                if result.cursor_hint is not None:
                    vs.cursor_line = max(0, min(result.cursor_hint, len(self.buffer) - 1))
                    self._scroll_to_cursor()

        vs.message = last_message

    def _save_and_quit(self) -> None:
        if self.buffer.modified and self.buffer.filepath:
            try:
                self.buffer.save_file()
            except Exception as e:
                self.vs.message = f"Save failed: {e}"
                self._render()
                self._quit_flag = False  # prevent quit so user sees the error

    # ------------------------------------------------------------------
    # Text editing helpers (basic, Phase 6 will flesh these out)
    # ------------------------------------------------------------------

    def _content_rows(self) -> int:
        """Visible text rows, accounting for the command bar and column ruler."""
        rows, _ = self.display.stdscr.getmaxyx()
        vs = self.vs
        return rows - 3 - (1 if vs.show_cols else 0) - (1 if vs.show_command else 0)

    def _scroll_col_to_cursor(self) -> None:
        """Adjust col_offset so cursor_col is always visible in the text area."""
        vs = self.vs
        text_width = max(1, vs.screen_cols - TEXT_OFFSET)
        if vs.cursor_col < vs.col_offset:
            vs.col_offset = vs.cursor_col
        elif vs.cursor_col >= vs.col_offset + text_width:
            vs.col_offset = vs.cursor_col - text_width + 1

    def _insert_char(self, ch: str) -> None:
        self.buffer.begin_edit_group()
        vs = self.vs
        if not self.buffer.lines:
            self.buffer.lines.append(Line(text=""))
        line = self.buffer.lines[vs.cursor_line]
        new_text = line.text[:vs.cursor_col] + ch + line.text[vs.cursor_col:]
        self.buffer.replace_line(vs.cursor_line, new_text)
        vs.cursor_col += 1
        self._scroll_col_to_cursor()

    def _backspace(self) -> None:
        self.buffer.begin_edit_group()
        vs = self.vs
        if not self.buffer.lines:
            return
        if vs.cursor_col > 0:
            line = self.buffer.lines[vs.cursor_line]
            new_text = line.text[:vs.cursor_col - 1] + line.text[vs.cursor_col:]
            self.buffer.replace_line(vs.cursor_line, new_text)
            vs.cursor_col -= 1
            self._scroll_col_to_cursor()
        elif vs.cursor_line > 0:
            # Join with previous line
            prev = self.buffer.lines[vs.cursor_line - 1].text
            curr = self.buffer.lines[vs.cursor_line].text
            new_col = len(prev)
            self.buffer.replace_line(vs.cursor_line - 1, prev + curr)
            self.buffer.delete_lines(vs.cursor_line, 1)
            vs.cursor_line -= 1
            vs.cursor_col = new_col
            self._scroll_to_cursor()
            self._scroll_col_to_cursor()

    def _delete_char(self) -> None:
        self.buffer.begin_edit_group()
        vs = self.vs
        if not self.buffer.lines:
            return
        line = self.buffer.lines[vs.cursor_line]
        if vs.cursor_col < len(line.text):
            new_text = line.text[:vs.cursor_col] + line.text[vs.cursor_col + 1:]
            self.buffer.replace_line(vs.cursor_line, new_text)
        elif vs.cursor_line < len(self.buffer) - 1:
            # At end of line — join with next line
            curr = line.text
            nxt = self.buffer.lines[vs.cursor_line + 1].text
            self.buffer.replace_line(vs.cursor_line, curr + nxt)
            self.buffer.delete_lines(vs.cursor_line + 1, 1)

    def _enter_key(self) -> None:
        self.buffer.begin_edit_group()
        vs = self.vs
        if not self.buffer.lines:
            self.buffer.lines.append(Line(text=""))
            return
        line = self.buffer.lines[vs.cursor_line]
        before = line.text[:vs.cursor_col]
        after = line.text[vs.cursor_col:]
        self.buffer.replace_line(vs.cursor_line, before)
        self.buffer.insert_lines(vs.cursor_line, [after])
        vs.cursor_line += 1
        vs.cursor_col = 0
        self._scroll_to_cursor()

    # ------------------------------------------------------------------
    # Cursor / scroll helpers
    # ------------------------------------------------------------------

    def _move_cursor(self, delta: int, skip_excluded: bool = True) -> None:
        vs = self.vs
        buf_len = max(len(self.buffer), 1)
        new_line = max(0, min(vs.cursor_line + delta, buf_len - 1))
        if skip_excluded:
            direction = 1 if delta >= 0 else -1
            new_line = self.buffer.next_visible(new_line, direction)
        vs.cursor_line = new_line
        if self.buffer.lines:
            vs.cursor_col = min(vs.cursor_col,
                                len(self.buffer.lines[vs.cursor_line].text))
        self._scroll_to_cursor()

    def _scroll_to_cursor(self) -> None:
        vs = self.vs
        content_rows = self._content_rows() - (1 if vs.show_command else 0)
        if vs.cursor_line < vs.top_line:
            vs.top_line = vs.cursor_line
        elif vs.cursor_line >= vs.top_line + content_rows:
            vs.top_line = vs.cursor_line - content_rows + 1
