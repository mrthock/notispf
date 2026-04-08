"""Curses rendering engine — the only file that touches curses."""
from __future__ import annotations
import curses
from dataclasses import dataclass, field


# Color pair IDs
_CP_STATUS   = 1   # status bar
_CP_PREFIX   = 2   # prefix column (line numbers)
_CP_SEP      = 3   # separator between prefix and text
_CP_TEXT     = 4   # normal text
_CP_MODIFIED = 5   # modified-line indicator in prefix
_CP_MSG      = 6   # message line
_CP_CMD      = 7   # command input line
_CP_CURSOR   = 8   # current line highlight


@dataclass
class ViewState:
    top_line: int               # index of first visible line
    cursor_line: int            # absolute buffer line index
    cursor_col: int             # column within the text area
    screen_rows: int
    screen_cols: int
    pending_prefixes: dict[int, str] = field(default_factory=dict)
    open_block_line: int | None = None
    open_block_cmd: str = ""
    message: str = ""
    command_input: str = ""
    command_mode: bool = False  # True when cursor is in command line


# Layout constants
PREFIX_WIDTH = 6
SEP_WIDTH = 1                   # the "|" separator
TEXT_OFFSET = PREFIX_WIDTH + SEP_WIDTH


class Display:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self._init_curses()

    def _init_curses(self):
        curses.curs_set(1)
        curses.start_color()
        curses.use_default_colors()

        curses.init_pair(_CP_STATUS,   curses.COLOR_BLACK,  curses.COLOR_CYAN)
        curses.init_pair(_CP_PREFIX,   curses.COLOR_CYAN,   -1)
        curses.init_pair(_CP_SEP,      curses.COLOR_CYAN,   -1)
        curses.init_pair(_CP_TEXT,     -1,                  -1)
        curses.init_pair(_CP_MODIFIED, curses.COLOR_YELLOW, -1)
        curses.init_pair(_CP_MSG,      curses.COLOR_BLACK,  curses.COLOR_YELLOW)
        curses.init_pair(_CP_CMD,      curses.COLOR_BLACK,  curses.COLOR_WHITE)
        curses.init_pair(_CP_CURSOR,   -1,                  curses.COLOR_BLUE)

        self.stdscr.keypad(True)

    def render(self, buffer, prefix_area, vs: ViewState) -> None:
        self.stdscr.erase()
        rows, cols = self.stdscr.getmaxyx()
        vs.screen_rows = rows
        vs.screen_cols = cols

        self._render_status(buffer, vs, cols)
        self._render_content(buffer, prefix_area, vs, rows, cols)
        self._render_bottom(vs, rows, cols)
        self._place_cursor(vs, rows)

        self.stdscr.noutrefresh()
        curses.doupdate()

    # ------------------------------------------------------------------
    # Status bar (row 0)
    # ------------------------------------------------------------------

    def _render_status(self, buffer, vs: ViewState, cols: int) -> None:
        filename = buffer.filepath or "[No File]"
        modified = " [+]" if buffer.modified else ""
        position = f"  Line {vs.cursor_line + 1}/{len(buffer)}"
        left = f" notispf  {filename}{modified}"
        right = position + "  "
        padding = cols - len(left) - len(right)
        if padding < 0:
            padding = 0
        line = left + " " * padding + right
        self._addstr_clipped(0, 0, line[:cols], curses.color_pair(_CP_STATUS))

    # ------------------------------------------------------------------
    # Content area (rows 1..rows-2)
    # ------------------------------------------------------------------

    def _render_content(self, buffer, prefix_area, vs: ViewState,
                        rows: int, cols: int) -> None:
        content_rows = rows - 2   # row 0 = status, last row = message/cmd
        text_width = cols - TEXT_OFFSET

        for screen_row in range(content_rows):
            buf_idx = vs.top_line + screen_row
            row = screen_row + 1   # offset past status bar

            if buf_idx >= len(buffer):
                # Past end of file — render empty prefix + tilde
                self._addstr_clipped(row, 0, " " * PREFIX_WIDTH,
                                     curses.color_pair(_CP_PREFIX))
                self._addstr_clipped(row, PREFIX_WIDTH, "|",
                                     curses.color_pair(_CP_SEP))
                self._addstr_clipped(row, TEXT_OFFSET, "~",
                                     curses.color_pair(_CP_PREFIX))
                continue

            # Prefix column
            prefix_content = self._get_prefix_display(
                buf_idx, buf_idx + 1, prefix_area, vs)
            is_cursor_line = (buf_idx == vs.cursor_line)
            prefix_attr = curses.color_pair(_CP_MODIFIED) \
                if buffer.lines[buf_idx].modified \
                else curses.color_pair(_CP_PREFIX)
            self._addstr_clipped(row, 0, f"{prefix_content:>6}"[:6], prefix_attr)

            # Separator
            self._addstr_clipped(row, PREFIX_WIDTH, "|",
                                 curses.color_pair(_CP_SEP))

            # Text
            text = buffer.lines[buf_idx].text
            display_text = text[vs.cursor_col - (vs.cursor_col % text_width)
                                if False else 0:]  # horizontal scroll: future
            display_text = display_text[:text_width]
            text_attr = curses.color_pair(_CP_CURSOR) if is_cursor_line \
                else curses.color_pair(_CP_TEXT)

            # Pad to fill the row so the highlight covers the full line
            display_text = display_text.ljust(text_width)[:text_width]
            self._addstr_clipped(row, TEXT_OFFSET, display_text, text_attr)

    def _get_prefix_display(self, buf_idx: int, line_number: int,
                             prefix_area, vs: ViewState) -> str:
        if buf_idx in vs.pending_prefixes:
            return vs.pending_prefixes[buf_idx][:6]
        if vs.open_block_line == buf_idx:
            return vs.open_block_cmd[:6]
        return prefix_area.get_display_content(buf_idx, line_number)

    # ------------------------------------------------------------------
    # Bottom row: message or command input
    # ------------------------------------------------------------------

    def _render_bottom(self, vs: ViewState, rows: int, cols: int) -> None:
        row = rows - 1
        if vs.command_mode:
            prompt = "===> "
            content = (prompt + vs.command_input)[:cols]
            content = content.ljust(cols)[:cols]
            self._addstr_clipped(row, 0, content, curses.color_pair(_CP_CMD))
        else:
            msg = vs.message[:cols].ljust(cols)[:cols]
            attr = curses.color_pair(_CP_MSG) if vs.message \
                else curses.color_pair(_CP_TEXT)
            self._addstr_clipped(row, 0, msg, attr)

    # ------------------------------------------------------------------
    # Cursor placement
    # ------------------------------------------------------------------

    def _place_cursor(self, vs: ViewState, rows: int) -> None:
        if vs.command_mode:
            prompt_len = len("===> ")
            col = min(prompt_len + len(vs.command_input), vs.screen_cols - 1)
            try:
                self.stdscr.move(rows - 1, col)
            except curses.error:
                pass
        else:
            screen_row = vs.cursor_line - vs.top_line + 1
            screen_col = TEXT_OFFSET + vs.cursor_col
            if 0 < screen_row < rows - 1 and screen_col < vs.screen_cols:
                try:
                    self.stdscr.move(screen_row, screen_col)
                except curses.error:
                    pass

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _addstr_clipped(self, row: int, col: int, text: str,
                        attr: int = 0) -> None:
        rows, cols = self.stdscr.getmaxyx()
        if row < 0 or row >= rows or col >= cols:
            return
        available = cols - col
        if available <= 0:
            return
        text = text[:available]
        try:
            self.stdscr.addstr(row, col, text, attr)
        except curses.error:
            pass   # writing to last cell of last row raises harmlessly

    def close(self) -> None:
        curses.endwin()
