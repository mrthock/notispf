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
_CP_RULER    = 9   # column ruler
_CP_HIGHLIGHT = 10  # found pattern highlight


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
    prefix_mode: bool = False   # True when cursor is in prefix column
    prefix_input: str = ""      # what user has typed in prefix column so far
    show_cols: bool = False     # True when column ruler is visible
    col_offset: int = 0        # horizontal scroll offset (columns shifted left)
    highlight_pattern: str = "" # pattern to highlight (empty = none)
    help_mode: bool = False     # True when help screen is visible
    help_scroll: int = 0        # top line of help screen
    hex_mode: bool = False      # True when HEX ON is active


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
        curses.init_pair(_CP_RULER,    curses.COLOR_BLACK,  curses.COLOR_WHITE)
        curses.init_pair(_CP_HIGHLIGHT, curses.COLOR_BLACK,  curses.COLOR_YELLOW)

        self.stdscr.keypad(True)

    def render(self, buffer, prefix_area, vs: ViewState) -> None:
        self.stdscr.erase()
        rows, cols = self.stdscr.getmaxyx()
        vs.screen_rows = rows
        vs.screen_cols = cols

        self._render_status(buffer, vs, cols)
        if vs.help_mode:
            self._render_help(vs, rows, cols)
            self._render_bottom(vs, rows, cols)
        else:
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
        hex_ind = " [HEX]" if vs.hex_mode else ""
        position = f"  Line {vs.cursor_line + 1}/{len(buffer)}  Col {vs.cursor_col + 1}"
        left = f" notispf  {filename}{modified}{hex_ind}"
        right = position + "  "
        padding = cols - len(left) - len(right)
        if padding < 0:
            padding = 0
        line = left + " " * padding + right
        self._addstr_clipped(0, 0, line[:cols], curses.color_pair(_CP_STATUS))

    # ------------------------------------------------------------------
    # Content area (rows 1..rows-2)
    # ------------------------------------------------------------------

    @staticmethod
    def build_view(buffer, top_line: int, content_rows: int) -> list:
        """Build a view list from top_line filling up to content_rows entries.

        Each entry is one of:
          ('line', buf_idx)
          ('fold', start_idx, end_idx, count)
        """
        entries = []
        i = top_line
        while i < len(buffer) and len(entries) < content_rows:
            if not buffer.lines[i].excluded:
                entries.append(('line', i))
                i += 1
            else:
                start = i
                while i < len(buffer) and buffer.lines[i].excluded:
                    i += 1
                entries.append(('fold', start, i - 1, i - start))
        return entries

    @staticmethod
    def _build_ruler(width: int) -> str:
        """Build an ISPF-style column ruler for the given text width."""
        ruler = []
        for col in range(1, width + 1):
            if col % 10 == 0:
                ruler.append(str(col // 10 % 10))
            elif col % 5 == 0:
                ruler.append('+')
            else:
                ruler.append('-')
        return ''.join(ruler)

    def _render_content(self, buffer, prefix_area, vs: ViewState,
                        rows: int, cols: int) -> None:
        content_rows = rows - 2
        text_width = cols - TEXT_OFFSET
        ruler_offset = 1 if vs.show_cols else 0
        view = self.build_view(buffer, vs.top_line, content_rows - ruler_offset)

        if vs.show_cols:
            ruler = self._build_ruler(vs.col_offset + text_width)
            ruler_slice = ruler[vs.col_offset:vs.col_offset + text_width]
            self._addstr_clipped(1, 0, "COLS  ", curses.color_pair(_CP_RULER))
            self._addstr_clipped(1, PREFIX_WIDTH, "|", curses.color_pair(_CP_RULER))
            self._addstr_clipped(1, TEXT_OFFSET, ruler_slice, curses.color_pair(_CP_RULER))

        for screen_row in range(content_rows - ruler_offset):
            row = screen_row + 1 + ruler_offset

            if screen_row >= len(view):
                # Past end of file
                self._addstr_clipped(row, 0, " " * PREFIX_WIDTH,
                                     curses.color_pair(_CP_PREFIX))
                self._addstr_clipped(row, PREFIX_WIDTH, "|",
                                     curses.color_pair(_CP_SEP))
                self._addstr_clipped(row, TEXT_OFFSET, "~",
                                     curses.color_pair(_CP_PREFIX))
                continue

            entry = view[screen_row]

            if entry[0] == 'fold':
                _, start_idx, end_idx, count = entry
                # Prefix shows fold count
                fold_prefix = f"-{count}-".center(6)[:6]
                self._addstr_clipped(row, 0, fold_prefix,
                                     curses.color_pair(_CP_MODIFIED))
                self._addstr_clipped(row, PREFIX_WIDTH, "|",
                                     curses.color_pair(_CP_SEP))
                fold_text = f" - - - {count} line(s) not displayed - - -"
                fold_text = fold_text.ljust(text_width)[:text_width]
                self._addstr_clipped(row, TEXT_OFFSET, fold_text,
                                     curses.color_pair(_CP_MODIFIED))
                continue

            # Normal line
            _, buf_idx = entry
            is_cursor_line = (buf_idx == vs.cursor_line)
            prefix_content = self._get_prefix_display(buf_idx, buf_idx + 1,
                                                       prefix_area, vs)
            prefix_attr = curses.color_pair(_CP_MODIFIED) \
                if buffer.lines[buf_idx].modified \
                else curses.color_pair(_CP_PREFIX)
            self._addstr_clipped(row, 0, f"{prefix_content:>6}"[:6], prefix_attr)

            self._addstr_clipped(row, PREFIX_WIDTH, "|",
                                 curses.color_pair(_CP_SEP))

            text = buffer.lines[buf_idx].text
            base_attr = curses.color_pair(_CP_CURSOR) if is_cursor_line \
                else curses.color_pair(_CP_TEXT)
            self._render_line_text(row, text, vs.col_offset, text_width,
                                   base_attr, vs.highlight_pattern)

    def _render_line_text(self, row: int, text: str, col_offset: int,
                         text_width: int, base_attr: int,
                         highlight_pattern: str) -> None:
        """Render one line's text area, highlighting all pattern occurrences."""
        # Build the padded display string for the visible window
        visible = text[col_offset:col_offset + text_width].ljust(text_width)

        if not highlight_pattern:
            self._addstr_clipped(row, TEXT_OFFSET, visible, base_attr)
            return

        # Find all match spans within the full text, clipped to visible window
        needle = highlight_pattern.lower()
        haystack = text.lower()
        matches: list[tuple[int, int]] = []
        start = 0
        while True:
            idx = haystack.find(needle, start)
            if idx == -1:
                break
            matches.append((idx, idx + len(highlight_pattern)))
            start = idx + len(highlight_pattern)

        if not matches:
            self._addstr_clipped(row, TEXT_OFFSET, visible, base_attr)
            return

        hi_attr = curses.color_pair(_CP_HIGHLIGHT)
        sc = 0  # screen column within text area
        for match_start, match_end in matches:
            # Characters before this match
            before_start = match_start - col_offset
            before_end = match_end - col_offset
            seg_start = max(sc, 0)
            seg_end = min(before_start, text_width)
            if seg_start < seg_end:
                self._addstr_clipped(row, TEXT_OFFSET + seg_start,
                                     visible[seg_start:seg_end], base_attr)
            sc = max(sc, before_start)
            # Highlighted match characters
            hi_start = max(sc, 0)
            hi_end = min(before_end, text_width)
            if hi_start < hi_end:
                self._addstr_clipped(row, TEXT_OFFSET + hi_start,
                                     visible[hi_start:hi_end], hi_attr)
            sc = max(sc, before_end)
            if sc >= text_width:
                break

        # Remaining text after last match
        if sc < text_width:
            self._addstr_clipped(row, TEXT_OFFSET + sc, visible[sc:], base_attr)

    def _get_prefix_display(self, buf_idx: int, line_number: int,
                             prefix_area, vs: ViewState) -> str:
        if buf_idx in vs.pending_prefixes:
            return vs.pending_prefixes[buf_idx][:6]
        if vs.open_block_line == buf_idx:
            return vs.open_block_cmd[:6]
        return prefix_area.get_display_content(buf_idx, line_number)

    # ------------------------------------------------------------------
    # Help screen
    # ------------------------------------------------------------------

    _HELP_LINES = [
        "  notispf — Help                                          Press any key to exit",
        "",
        "  COMMAND LINE  (press F6 to open)",
        "  " + "─" * 60,
        "  SAVE                   Save file",
        "  FILE                   Save and exit",
        "  CANCEL / QUIT          Exit without saving",
        "  COPY filename          Copy buffer to another file",
        "  FIND \"pat\" [col]       Find next occurrence (col = start column)",
        "  CHANGE \"o\" \"n\" [opts]  Change text  (opts: ALL, col, .lbl .lbl)",
        "  EXCLUDE \"pat\" [ALL|n]  Exclude matching lines from view",
        "  SHOW ALL               Un-exclude all lines",
        "  DELETE \"pat\" [ALL|n]   Delete lines matching pattern",
        "  DELETE X ALL           Delete all excluded lines",
        "  DELETE NX ALL          Delete all non-excluded lines",
        "  UNDO                   Undo last change",
        "  REDO                   Redo last undone change",
        "  HEX ON                 Convert entire file to hex display",
        "  HEX OFF                Convert hex display back to text",
        "  COLS                   Toggle column ruler",
        "  CLEAR                  Clear search/change highlighting",
        "  HELP                   Show this screen",
        "",
        "  PREFIX COMMANDS  (Tab to reach prefix area)",
        "  " + "─" * 60,
        "  D / Dn    Delete line(s)          DD        Delete block",
        "  I / In    Insert blank line(s)",
        "  R / Rn    Repeat line             RR        Repeat block",
        "  C / Cn    Copy line(s)            CC        Copy block",
        "  M / Mn    Move line(s)            MM        Move block",
        "  A         Paste after this line",
        "  B         Paste before this line",
        "  O / On    Overlay clipboard       OO        Overlay block",
        "  X / Xn    Exclude line(s)         XX        Exclude block",
        "  S / Sn    Show (un-exclude)       SS        Show block",
        "  >n        Indent right n cols     >>n       Indent block right n cols",
        "  <n        Indent left n cols      <<n       Indent block left n cols",
        "  HEX       Replace line with hex   HEXB      Insert hex copy below",
        "  HEXA      Convert hex line to ASCII",
        "  UC / UCn  Uppercase line(s)        LC / LCn  Lowercase line(s)",
        "",
        "  FUNCTION KEYS",
        "  " + "─" * 60,
        "  F1          Help                  F3        Save and exit",
        "  F5          Repeat last FIND",
        "  F6          Open command line     F12       Exit without saving",
        "  Ctrl+Z      Undo                  Ctrl+Y    Redo",
        "  F7  / PgUp  Scroll up             F8/PgDn   Scroll down",
        "  F10         Scroll left           F11       Scroll right",
        "  Tab         Move to prefix area",
        "  Shift+Tab   Move to previous line",
        "",
        "  NAVIGATION",
        "  " + "─" * 60,
        "  Arrow keys  Move cursor           Home/End  Start/end of line",
        "  Ctrl-A      Start of line         Ctrl-E    End of line",
        "",
    ]

    def _render_help(self, vs: ViewState, rows: int, cols: int) -> None:
        content_rows = rows - 2
        lines = self._HELP_LINES
        for screen_row in range(content_rows):
            row = screen_row + 1
            line_idx = vs.help_scroll + screen_row
            if line_idx < len(lines):
                text = lines[line_idx][:cols].ljust(cols)[:cols]
                attr = curses.color_pair(_CP_STATUS) if screen_row == 0 \
                    else curses.color_pair(_CP_TEXT)
                self._addstr_clipped(row, 0, text, attr)
            else:
                self._addstr_clipped(row, 0, " " * cols,
                                     curses.color_pair(_CP_TEXT))

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
        elif vs.prefix_mode:
            ruler_offset = 1 if vs.show_cols else 0
            screen_row = vs.cursor_line - vs.top_line + 1 + ruler_offset
            screen_col = min(len(vs.prefix_input), PREFIX_WIDTH - 1)
            if 0 < screen_row < rows - 1:
                try:
                    self.stdscr.move(screen_row, screen_col)
                except curses.error:
                    pass
        else:
            ruler_offset = 1 if vs.show_cols else 0
            screen_row = vs.cursor_line - vs.top_line + 1 + ruler_offset
            screen_col = TEXT_OFFSET + vs.cursor_col - vs.col_offset
            if 0 < screen_row < rows - 1 and TEXT_OFFSET <= screen_col < vs.screen_cols:
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
        pass  # curses.wrapper handles endwin() on exit
