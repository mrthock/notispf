"""Top-level application controller."""
from __future__ import annotations
import curses
import os

from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry
from notispf.commands import line_cmds, block_cmds
from notispf.display import Display, ViewState, TEXT_OFFSET
from notispf.find_change import FindChangeEngine
from notispf.prefix import PrefixArea


def _build_registry() -> CommandRegistry:
    r = CommandRegistry()
    line_cmds.register(r)
    block_cmds.register(r)
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
        buf.lines = []
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
        # Overlay the live input for the current line while the user is typing
        if self.vs.prefix_mode:
            if self.vs.prefix_input:
                self.vs.pending_prefixes[self.vs.cursor_line] = self.vs.prefix_input
            else:
                self.vs.pending_prefixes.pop(self.vs.cursor_line, None)
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
            return self._handle_command_key(key)

        if vs.prefix_mode:
            return self._handle_prefix_key(key)

        rows, _ = self.display.stdscr.getmaxyx()
        content_rows = rows - 2

        # Navigation
        if key == curses.KEY_UP:
            self._move_cursor(-1)
        elif key == curses.KEY_DOWN:
            self._move_cursor(1)
        elif key == curses.KEY_PPAGE:       # Page Up
            self._move_cursor(-content_rows)
        elif key == curses.KEY_NPAGE:       # Page Down
            self._move_cursor(content_rows)
        elif key == curses.KEY_HOME or key == ord('\x01'):  # Home / Ctrl-A
            vs.cursor_col = 0
        elif key == curses.KEY_END or key == ord('\x05'):   # End / Ctrl-E
            if self.buffer.lines:
                vs.cursor_col = len(self.buffer.lines[vs.cursor_line].text)
        elif key == curses.KEY_LEFT:
            vs.cursor_col = max(0, vs.cursor_col - 1)
        elif key == curses.KEY_RIGHT:
            if self.buffer.lines:
                vs.cursor_col = min(
                    len(self.buffer.lines[vs.cursor_line].text),
                    vs.cursor_col + 1)

        # Enter command mode
        elif key == ord('=') or key == curses.KEY_F6:
            vs.command_mode = True
            vs.command_input = ""
            vs.message = ""

        # F3 = FILE (save and quit)
        elif key == curses.KEY_F3:
            self._save_and_quit()
            return True

        # F12 = CANCEL (quit without saving)
        elif key == curses.KEY_F12:
            return True

        # F5 = save without quit
        elif key == curses.KEY_F5:
            try:
                self.buffer.save_file()
                vs.message = f"File saved: {self.buffer.filepath}"
            except Exception as e:
                vs.message = f"Save error: {e}"

        # Tab: prefix(N) -> text(N),  text(N) -> prefix(N+1)
        elif key == ord('\t'):
            if vs.prefix_mode:
                # Leave prefix area, stay on same line, go to text
                self._stage_current_prefix()
                vs.prefix_mode = False
                vs.prefix_input = ""
                vs.message = ""
            else:
                # Advance to next line and enter its prefix area
                self._move_cursor(1)
                vs.prefix_mode = True
                vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")
                vs.message = "Type prefix command, Enter to execute, Esc to cancel"

        # Shift+Tab: text(N) -> prefix(N),  prefix(N) -> text(N-1)
        elif key == curses.KEY_BTAB:
            if vs.prefix_mode:
                # Leave prefix area, go to previous line's text area
                self._stage_current_prefix()
                vs.prefix_mode = False
                vs.prefix_input = ""
                vs.message = ""
                self._move_cursor(-1)
            else:
                # Enter prefix area of current line
                vs.prefix_mode = True
                vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")
                vs.message = "Type prefix command, Enter to execute, Esc to cancel"

        # Text editing (Phase 6 — placeholder)
        elif key == curses.KEY_BACKSPACE or key == 127:
            self._backspace()
        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            self._enter_key()
        elif 32 <= key <= 126:
            self._insert_char(chr(key))

        return False

    def _handle_command_key(self, key: int) -> bool:
        vs = self.vs
        if key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            result_msg = self._execute_command(vs.command_input.strip())
            vs.command_mode = False
            vs.command_input = ""
            vs.message = result_msg
        elif key == 27:  # Escape
            vs.command_mode = False
            vs.command_input = ""
            vs.message = ""
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
        import shlex
        try:
            tokens = shlex.split(raw.upper())
        except ValueError:
            return f"Parse error: {raw}"

        cmd = tokens[0] if tokens else ""

        if cmd in ("CANCEL", "QUIT"):
            self._quit_flag = True
            return ""

        if cmd in ("SAVE", "FILE"):
            try:
                self.buffer.save_file()
                if cmd == "FILE":
                    self._quit_flag = True
                return f"Saved: {self.buffer.filepath}"
            except Exception as e:
                return f"Save error: {e}"

        if cmd == "FIND":
            if len(tokens) < 2:
                return "Usage: FIND <text>"
            # Re-parse preserving original case
            try:
                orig_tokens = shlex.split(raw)
            except ValueError:
                return f"Parse error: {raw}"
            pattern = orig_tokens[1] if len(orig_tokens) > 1 else ""
            pos = self.find_engine.find_next(pattern)
            if pos:
                self.vs.cursor_line, self.vs.cursor_col = pos
                self._scroll_to_cursor()
                return f"Found: {pattern!r}"
            return f"Not found: {pattern!r}"

        if cmd == "CHANGE":
            try:
                orig_tokens = shlex.split(raw)
            except ValueError:
                return f"Parse error: {raw}"
            if len(orig_tokens) < 3:
                return 'Usage: CHANGE "old" "new" [ALL] [.lbl1 .lbl2]'
            old, new = orig_tokens[1], orig_tokens[2]
            rest = [t.upper() for t in orig_tokens[3:]]
            try:
                if "ALL" in rest:
                    labels = [t for t in rest if t.startswith(".")]
                    if len(labels) >= 2:
                        n = self.find_engine.change_in_range(
                            old, new, labels[0], labels[1])
                    else:
                        n = self.find_engine.change_all(old, new)
                    return f"{n} change(s) made"
                else:
                    labels = [t for t in rest if t.startswith(".")]
                    if len(labels) >= 2:
                        n = self.find_engine.change_in_range(
                            old, new, labels[0], labels[1])
                        return f"{n} change(s) made"
                    n = self.find_engine.change_next(old, new)
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
            self._move_cursor(-1)
            vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")

        elif key == curses.KEY_DOWN:
            self._stage_current_prefix()
            self._move_cursor(1)
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
            self._move_cursor(-1)

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
        paste_cmds = {"A", "B"}

        # Pass 1: everything except A/B, in line order
        for line_idx in sorted(pending.keys()):
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
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Text editing helpers (basic, Phase 6 will flesh these out)
    # ------------------------------------------------------------------

    def _insert_char(self, ch: str) -> None:
        vs = self.vs
        if not self.buffer.lines:
            self.buffer.lines.append(__import__('notispf.buffer', fromlist=['Line']).Line(text=""))
        line = self.buffer.lines[vs.cursor_line]
        new_text = line.text[:vs.cursor_col] + ch + line.text[vs.cursor_col:]
        self.buffer.replace_line(vs.cursor_line, new_text)
        vs.cursor_col += 1

    def _backspace(self) -> None:
        vs = self.vs
        if not self.buffer.lines:
            return
        if vs.cursor_col > 0:
            line = self.buffer.lines[vs.cursor_line]
            new_text = line.text[:vs.cursor_col - 1] + line.text[vs.cursor_col:]
            self.buffer.replace_line(vs.cursor_line, new_text)
            vs.cursor_col -= 1
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

    def _enter_key(self) -> None:
        vs = self.vs
        if not self.buffer.lines:
            self.buffer.lines.append(__import__('notispf.buffer', fromlist=['Line']).Line(text=""))
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

    def _move_cursor(self, delta: int) -> None:
        vs = self.vs
        buf_len = max(len(self.buffer), 1)
        vs.cursor_line = max(0, min(vs.cursor_line + delta, buf_len - 1))
        if self.buffer.lines:
            vs.cursor_col = min(vs.cursor_col,
                                len(self.buffer.lines[vs.cursor_line].text))
        self._scroll_to_cursor()

    def _scroll_to_cursor(self) -> None:
        vs = self.vs
        rows, _ = self.display.stdscr.getmaxyx()
        content_rows = rows - 2
        if vs.cursor_line < vs.top_line:
            vs.top_line = vs.cursor_line
        elif vs.cursor_line >= vs.top_line + content_rows:
            vs.top_line = vs.cursor_line - content_rows + 1
