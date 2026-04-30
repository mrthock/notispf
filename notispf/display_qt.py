"""PyQt6 display layer — replaces display.py for the Qt frontend."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QAbstractScrollArea, QApplication,
)
from PyQt6.QtCore import Qt, QRect, QTimer, QEvent
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPalette, QKeyEvent, QAction, QKeySequence

from notispf.display import Display, PREFIX_WIDTH, SEP_WIDTH, TOP_SENTINEL, BOT_SENTINEL

# ── Colour palette ────────────────────────────────────────────────────────────
_BG           = QColor("#1e1e1e")
_TEXT         = QColor("#d4d4d4")
_PREFIX       = QColor("#00cccc")
_SEP          = QColor("#00cccc")
_MODIFIED     = QColor("#ffff00")
_FOLD         = QColor("#ffff00")
_HI_BG        = QColor("#b8860b")   # dark goldenrod
_HI_FG        = QColor("#ffffff")
_TILDE        = QColor("#404040")
_RULER_BG     = QColor("#2d2d2d")
_RULER_FG     = QColor("#888888")
_PFX_MODE_BG  = QColor("#1a3300")   # prefix-active row tint
_HELP_HDR_BG  = QColor("#007acc")
_HELP_HDR_FG  = QColor("#ffffff")


# ── Editor viewport ───────────────────────────────────────────────────────────

class EditorViewport(QAbstractScrollArea):
    """Paints the prefix column, text area, ruler, and help screen."""

    def __init__(self, app_qt: "AppQt"):
        super().__init__()
        self.app = app_qt

        self._font = QFont("Monospace")
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self._font.setFixedPitch(True)
        self._font.setPointSize(10)
        self.setFont(self._font)
        fm = QFontMetrics(self._font)
        self._cw  = fm.horizontalAdvance("M")   # char width (fixed-pitch)
        self._lh  = fm.lineSpacing()             # line height
        self._asc = fm.ascent()                  # baseline offset

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Dark background for the viewport
        pal = self.viewport().palette()
        pal.setColor(QPalette.ColorRole.Base, _BG)
        self.viewport().setPalette(pal)
        self.viewport().setAutoFillBackground(True)

        # Cursor blink
        self._blink_on = True
        t = QTimer(self)
        t.timeout.connect(self._blink)
        t.start(530)

        # Scrollbar drives top_line
        self.verticalScrollBar().valueChanged.connect(self._on_vscroll)

    # ── Sizing ────────────────────────────────────────────────────────────────

    def content_rows(self) -> int:
        return max(1, self.viewport().height() // self._lh)

    def content_cols(self) -> int:
        text_px = self.viewport().width() - (PREFIX_WIDTH + SEP_WIDTH) * self._cw
        return max(1, text_px // self._cw)

    def _text_x(self) -> int:
        return (PREFIX_WIDTH + SEP_WIDTH) * self._cw

    # ── Events ────────────────────────────────────────────────────────────────

    def _blink(self):
        self._blink_on = not self._blink_on
        self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.app.vs.screen_rows = self.content_rows() + 2
        self.app.vs.screen_cols = self.content_cols() + PREFIX_WIDTH + SEP_WIDTH
        self._sync_scrollbar()

    def wheelEvent(self, event):
        delta = -event.angleDelta().y() // 40
        self.app._move_cursor(delta)
        self.app._render()

    def event(self, event):
        if (event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)):
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent):
        self.app._handle_key_qt(event)
        self._sync_scrollbar()
        self.viewport().update()

    def mousePressEvent(self, event):
        vs = self.app.vs
        if vs.help_mode:
            vs.help_mode = False
            self.app._render()
            return

        ruler_offset = 1 if vs.show_cols else 0
        lh, cw = self._lh, self._cw
        prefix_w = PREFIX_WIDTH * cw
        text_x = self._text_x()

        sr = int(event.position().y() // lh) - ruler_offset
        if sr < 0:
            return

        rows = self.content_rows()
        view = Display.build_view(self.app.buffer, vs.top_line, rows - ruler_offset)
        if sr >= len(view):
            return

        entry = view[sr]
        if entry[0] in ("top", "bot"):
            sentinel_key = TOP_SENTINEL if entry[0] == "top" else BOT_SENTINEL
            vs.cursor_line = sentinel_key
            vs.prefix_mode = True
            vs.prefix_input = self.app.prefix_area._pending.get(sentinel_key, "")
            vs.message = "Type I to insert — Enter to execute, Esc to cancel"
            self.app._render()
            self.setFocus()
            return

        if entry[0] != "line":
            return

        _, buf_idx = entry
        vs.cursor_line = buf_idx

        if event.position().x() < prefix_w:
            vs.prefix_mode = True
            vs.command_mode = False
            vs.prefix_input = self.app.prefix_area._pending.get(buf_idx, "")
            vs.message = "Type prefix command, Enter to execute, Esc to cancel"
        else:
            vs.prefix_mode = False
            col = int((event.position().x() - text_x) // cw) + vs.col_offset
            if self.app.buffer.lines:
                col = min(col, len(self.app.buffer.lines[buf_idx].text))
            vs.cursor_col = max(0, col)

        self.app._render()
        self.setFocus()

    # ── Scrollbar sync ────────────────────────────────────────────────────────

    def _on_vscroll(self, value: int):
        self.app.vs.top_line = value
        self.viewport().update()

    def _sync_scrollbar(self):
        vs = self.app.vs
        buf_len = max(len(self.app.buffer), 1)
        sb = self.verticalScrollBar()
        sb.blockSignals(True)
        sb.setRange(0, max(0, buf_len - 1))
        sb.setPageStep(self.content_rows())
        sb.setValue(vs.top_line)
        sb.blockSignals(False)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self.viewport())
        p.setFont(self._font)
        vs  = self.app.vs
        buf = self.app.buffer
        vw  = self.viewport().width()
        vh  = self.viewport().height()
        cw, lh, asc = self._cw, self._lh, self._asc
        prefix_w = PREFIX_WIDTH * cw
        sep_x    = prefix_w
        sep_w    = SEP_WIDTH * cw
        text_x   = prefix_w + sep_w
        text_w   = vw - text_x

        p.fillRect(0, 0, vw, vh, _BG)

        if vs.help_mode:
            self._paint_help(p, vs, vw, lh, asc)
            p.end()
            return

        rows = self.content_rows()
        ruler_offset = 1 if vs.show_cols else 0
        view = Display.build_view(buf, vs.top_line, rows - ruler_offset)

        # Column ruler
        if vs.show_cols:
            ruler = self._build_ruler(vs.col_offset, text_w // cw)
            p.fillRect(0, 0, vw, lh, _RULER_BG)
            p.setPen(_PREFIX)
            p.drawText(0, asc, "COLS  ")
            p.setPen(_SEP)
            p.drawText(sep_x, asc, "|")
            p.setPen(_RULER_FG)
            p.drawText(text_x, asc, ruler)

        sentinel_offset = 1 if vs.top_line == 0 else 0

        for sr in range(rows - ruler_offset):
            y        = (sr + ruler_offset) * lh
            baseline = y + asc

            # Past end of file
            if sr >= len(view):
                p.setPen(_SEP)
                p.drawText(sep_x, baseline, "|")
                p.setPen(_TILDE)
                p.drawText(text_x, baseline, "~")
                continue

            entry = view[sr]

            # Sentinel rows (top / bottom of data)
            if entry[0] in ("top", "bot"):
                is_top = entry[0] == "top"
                sentinel_key = TOP_SENTINEL if is_top else BOT_SENTINEL
                label = "- - - TOP OF DATA - - -" if is_top \
                    else "- - - BOTTOM OF DATA - - -"
                pfx = vs.pending_prefixes.get(sentinel_key, "")
                overlay = (pfx + "******"[len(pfx):])[:PREFIX_WIDTH] \
                    if pfx else "******"
                p.setPen(_FOLD)
                p.drawText(0, baseline, overlay)
                p.setPen(_SEP)
                p.drawText(sep_x, baseline, "|")
                p.setPen(_FOLD)
                p.drawText(text_x, baseline, label)
                continue

            # Fold row
            if entry[0] == "fold":
                _, _, _, count = entry
                fold_pfx = f"-{count}-".center(PREFIX_WIDTH)[:PREFIX_WIDTH]
                p.setPen(_FOLD)
                p.drawText(0, baseline, fold_pfx)
                p.setPen(_SEP)
                p.drawText(sep_x, baseline, "|")
                p.setPen(_FOLD)
                p.drawText(text_x, baseline,
                           f" - - - {count} line(s) not displayed - - -")
                continue

            # Normal line
            _, buf_idx = entry
            line = buf.lines[buf_idx]

            # Prefix-mode tint on active line
            if vs.prefix_mode and buf_idx == vs.cursor_line:
                p.fillRect(0, y, prefix_w, lh, _PFX_MODE_BG)

            # Prefix text (right-aligned)
            pfx = self._prefix_text(buf_idx)
            p.setPen(_MODIFIED if line.modified else _PREFIX)
            p.drawText(QRect(0, y, prefix_w, lh),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       pfx.strip())

            # Separator
            p.setPen(_SEP)
            p.drawText(sep_x, baseline, "|")

            # Text (with optional highlight)
            col0    = vs.col_offset
            visible = line.text[col0: col0 + (text_w // cw)]
            if vs.highlight_pattern:
                self._draw_highlighted(p, text_x, y, lh, asc, cw,
                                       visible, line.text[col0:],
                                       vs.highlight_pattern)
            else:
                p.setPen(_TEXT)
                p.drawText(text_x, baseline, visible)

        # Hardware cursor (underline bar)
        if self._blink_on and not vs.command_mode:
            if vs.cursor_line == TOP_SENTINEL:
                sr = ruler_offset
            elif vs.cursor_line == BOT_SENTINEL:
                sr = next((i + ruler_offset for i, e in enumerate(view)
                           if e[0] == "bot"), -1)
            else:
                sr = vs.cursor_line - vs.top_line + ruler_offset + sentinel_offset
            if 0 <= sr < rows:
                cy = sr * lh + lh - 2
                if vs.prefix_mode:
                    cx = len(vs.prefix_input) * cw
                else:
                    cx = text_x + (vs.cursor_col - vs.col_offset) * cw
                p.fillRect(cx, cy, cw, 2, QColor("#ffffff"))

        p.end()

    def _paint_help(self, p: QPainter, vs, vw: int, lh: int, asc: int):
        lines = Display._HELP_LINES
        rows  = self.content_rows()
        for sr in range(rows):
            y        = sr * lh
            baseline = y + asc
            li = vs.help_scroll + sr
            if li >= len(lines):
                break
            if sr == 0:
                p.fillRect(0, y, vw, lh, _HELP_HDR_BG)
                p.setPen(_HELP_HDR_FG)
            else:
                p.setPen(_TEXT)
            p.drawText(2, baseline, lines[li])

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _prefix_text(self, buf_idx: int) -> str:
        vs = self.app.vs
        pa = self.app.prefix_area
        if buf_idx in vs.pending_prefixes:
            return vs.pending_prefixes[buf_idx][:PREFIX_WIDTH]
        if buf_idx < 0:  # sentinel — rendered separately, guard just in case
            return "******"
        if vs.open_block_line == buf_idx:
            return vs.open_block_cmd[:PREFIX_WIDTH]
        return pa.get_display_content(buf_idx, buf_idx + 1)

    @staticmethod
    def _build_ruler(col_offset: int, width: int) -> str:
        ruler = []
        for col in range(1, col_offset + width + 1):
            if col % 10 == 0:
                ruler.append(str(col // 10 % 10))
            elif col % 5 == 0:
                ruler.append("+")
            else:
                ruler.append("-")
        return "".join(ruler)[col_offset: col_offset + width]

    def _draw_highlighted(self, p: QPainter, text_x: int, y: int, lh: int,
                          asc: int, cw: int, visible: str, text_from_offset: str,
                          pattern: str):
        needle   = pattern.lower()
        haystack = text_from_offset.lower()
        x        = text_x
        baseline = y + asc
        i = 0
        while i < len(visible):
            if haystack[i: i + len(needle)] == needle:
                hi_len = min(len(pattern), len(visible) - i)
                hi_w   = hi_len * cw
                p.fillRect(x, y, hi_w, lh, _HI_BG)
                p.setPen(_HI_FG)
                p.drawText(x, baseline, visible[i: i + hi_len])
                x += hi_w
                i += hi_len
            else:
                p.setPen(_TEXT)
                p.drawText(x, baseline, visible[i])
                x += cw
                i += 1


# ── Command bar input ─────────────────────────────────────────────────────────

class CommandInput(QLineEdit):
    """The ===> command bar. Special keys are intercepted via event filter
    installed by NotispfWindow. Tab/Backtab are handled here directly because
    Qt's focus-traversal system consumes them before the event filter sees them."""

    def __init__(self, app_qt: "AppQt"):
        super().__init__()
        self.app = app_qt
        self._syncing = False
        self.returnPressed.connect(self._on_enter)
        self.textChanged.connect(self._on_text)

    # Override event() so Tab/Backtab never reach Qt's focus-traversal machinery.
    def event(self, event):
        if (event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)):
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        vs  = self.app.vs
        if key == Qt.Key.Key_Tab:
            vs.command_mode  = False
            vs.command_input = ""
            self.sync_text("")
            vs.cursor_line   = 0
            vs.cursor_col    = 0
            vs.prefix_mode   = True
            vs.prefix_input  = self.app.prefix_area._pending.get(0, "")
            self.app._scroll_to_cursor()
            vs.message = "Type prefix command, Enter to execute, Esc to cancel"
            self.app._render()
            self.app.window.editor.setFocus()
        else:
            super().keyPressEvent(event)

    def _on_enter(self):
        vs = self.app.vs
        vs.message      = self.app._execute_command(self.text().strip())
        vs.command_input = ""
        self._syncing = True
        self.clear()
        self._syncing = False
        self.app._render()

    def _on_text(self, text: str):
        if not self._syncing:
            self.app.vs.command_input = text

    def sync_text(self, text: str):
        self._syncing = True
        self.setText(text)
        self._syncing = False


# ── Main window ───────────────────────────────────────────────────────────────

class NotispfWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self, app_qt: "AppQt"):
        super().__init__()
        self.app = app_qt
        self.setWindowTitle("notispf")
        self._build_ui()
        self.resize(900, 600)
        self.setMinimumSize(400, 200)
        # Intercept special keys in the command bar before QLineEdit eats them
        self.cmd_input.installEventFilter(self)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Status bar
        self.status_lbl = QLabel()
        self.status_lbl.setFixedHeight(22)
        self.status_lbl.setStyleSheet(
            "background:#00aaaa; color:#000000;"
            " font-family:Monospace; padding:2px 6px;")
        layout.addWidget(self.status_lbl)

        # Command bar row
        self.cmd_widget = QWidget()
        self.cmd_widget.setFixedHeight(24)
        cmd_row = QHBoxLayout(self.cmd_widget)
        cmd_row.setContentsMargins(0, 0, 0, 0)
        cmd_row.setSpacing(0)

        self.cmd_lbl = QLabel("===> ")
        self.cmd_lbl.setStyleSheet(
            "background:#2d4a1e; color:#ffffff;"
            " font-family:Monospace; padding:2px 4px;")

        self.cmd_input = CommandInput(self.app)
        self.cmd_input.setStyleSheet(
            "background:#2d4a1e; color:#ffffff;"
            " font-family:Monospace; border:none; padding:2px 0px;")
        self.cmd_input.setFrame(False)

        cmd_row.addWidget(self.cmd_lbl)
        cmd_row.addWidget(self.cmd_input, 1)
        layout.addWidget(self.cmd_widget)

        # Editor viewport
        self.editor = EditorViewport(self.app)
        layout.addWidget(self.editor, 1)

        # Function key bar
        fkey_items = [
            ("F1", "HELP"), ("F3", "SAVE"), ("F5", "RFIND"), ("F6", "CMD"),
            ("F7", "UP"), ("F8", "DOWN"), ("F10", "LEFT"), ("F11", "RIGHT"),
            ("F12", "QUIT"),
        ]
        fkey_text = "  ".join(f"{k}-{v}" for k, v in fkey_items)
        self.fkey_lbl = QLabel(fkey_text)
        self.fkey_lbl.setFixedHeight(20)
        self.fkey_lbl.setStyleSheet(
            "background:#2d2d2d; color:#aaaaaa;"
            " font-family:Monospace; padding:2px 6px;")
        layout.addWidget(self.fkey_lbl)

        # Message bar
        self.msg_lbl = QLabel()
        self.msg_lbl.setFixedHeight(20)
        self.msg_lbl.setStyleSheet(
            "font-family:Monospace; padding:2px 6px;")
        layout.addWidget(self.msg_lbl)

        self._build_menu()

    def _build_menu(self):
        self.menuBar().setStyleSheet(
            "QMenuBar { background:#2d2d2d; color:#d4d4d4; }"
            "QMenuBar::item:selected { background:#3d3d3d; }"
            "QMenu { background:#2d2d2d; color:#d4d4d4; border:1px solid #555; }"
            "QMenu::item:selected { background:#3d6b9a; }"
            "QMenu::separator { height:1px; background:#555; margin:3px 6px; }"
        )

        # ── File ──────────────────────────────────────────────────────────────
        file_menu = self.menuBar().addMenu("File")

        open_act = QAction("Open...", self)
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self.app._menu_open)
        file_menu.addAction(open_act)

        save_act = QAction("Save", self)
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.triggered.connect(self.app._menu_save)
        file_menu.addAction(save_act)

        save_as_act = QAction("Save As...", self)
        save_as_act.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_act.triggered.connect(self.app._menu_save_as)
        file_menu.addAction(save_as_act)

        file_menu.addSeparator()

        quit_act = QAction("Quit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.app._menu_quit)
        file_menu.addAction(quit_act)

        # ── Edit ──────────────────────────────────────────────────────────────
        edit_menu = self.menuBar().addMenu("Edit")

        undo_act = QAction("Undo\tCtrl+Z", self)
        undo_act.triggered.connect(self.app._menu_undo)
        edit_menu.addAction(undo_act)

        redo_act = QAction("Redo\tCtrl+Y", self)
        redo_act.triggered.connect(self.app._menu_redo)
        edit_menu.addAction(redo_act)

        edit_menu.addSeparator()

        find_act = QAction("Find...", self)
        find_act.setShortcut(QKeySequence.StandardKey.Find)
        find_act.triggered.connect(self.app._menu_find)
        edit_menu.addAction(find_act)

        rfind_act = QAction("Find Next\tF5", self)
        rfind_act.triggered.connect(self.app._menu_rfind)
        edit_menu.addAction(rfind_act)

        replace_act = QAction("Replace...", self)
        replace_act.setShortcut(QKeySequence.StandardKey.Replace)
        replace_act.triggered.connect(self.app._menu_replace)
        edit_menu.addAction(replace_act)

        # ── View ──────────────────────────────────────────────────────────────
        view_menu = self.menuBar().addMenu("View")

        self._cols_action = QAction("Column Ruler", self)
        self._cols_action.setCheckable(True)
        self._cols_action.triggered.connect(self.app._menu_cols)
        view_menu.addAction(self._cols_action)

        self._cmdbar_action = QAction("Command Bar", self)
        self._cmdbar_action.setCheckable(True)
        self._cmdbar_action.setChecked(True)
        self._cmdbar_action.triggered.connect(self.app._menu_cmdbar)
        view_menu.addAction(self._cmdbar_action)

        view_menu.addSeparator()

        help_act = QAction("Help\tF1", self)
        help_act.triggered.connect(self.app._menu_help)
        view_menu.addAction(help_act)

    # ── Event filter (command bar special keys) ───────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self.cmd_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            vs  = self.app.vs

            if key == Qt.Key.Key_Escape:
                vs.command_mode  = False
                vs.command_input = ""
                self.cmd_input.sync_text("")
                vs.message = ""
                self.app._render()
                self.editor.setFocus()
                return True

            if key == Qt.Key.Key_F6:
                vs.show_command  = False
                vs.command_mode  = False
                vs.command_input = ""
                self.cmd_input.sync_text("")
                vs.message = ""
                self.app._render()
                self.editor.setFocus()
                return True

            if key == Qt.Key.Key_Down:
                vs.command_mode = False
                vs.message      = ""
                self.app._render()
                self.editor.setFocus()
                return True

            if key == Qt.Key.Key_F3:
                self.app._save_and_quit()
                self.app._quit_flag = True
                self.app._render()
                return True

            if key == Qt.Key.Key_F5:
                vs    = self.app.vs
                pattern = self.app.find_engine._last_find
                if not pattern:
                    vs.message = "No previous FIND"
                else:
                    pos = self.app.find_engine.find_next(pattern)
                    if pos:
                        vs.cursor_line, vs.cursor_col = pos
                        self.app._scroll_to_cursor()
                        self.app._scroll_col_to_cursor()
                        vs.highlight_pattern = pattern
                        vs.message = f"Found: {pattern!r}"
                    else:
                        vs.highlight_pattern = ""
                        vs.message = f"Not found: {pattern!r}"
                self.app._render()
                return True

        return super().eventFilter(obj, event)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self):
        """Sync all widgets from current ViewState and Buffer."""
        vs  = self.app.vs
        buf = self.app.buffer

        # Window title
        name = buf.filepath or "[No File]"
        mod  = " [+]" if buf.modified else ""
        self.setWindowTitle(f"notispf — {name}{mod}")

        # Status bar
        hex_i = " [HEX]" if vs.hex_mode else ""
        pos   = f"  Line {vs.cursor_line + 1}/{len(buf)}  Col {vs.cursor_col + 1}"
        self.status_lbl.setText(f" notispf  {name}{mod}{hex_i}{pos}")

        # Command bar visibility and focus
        self.cmd_widget.setVisible(vs.show_command)
        if vs.command_mode and vs.show_command:
            if not self.cmd_input.hasFocus():
                self.cmd_input.setFocus()

        # Message bar
        if vs.message:
            self.msg_lbl.setStyleSheet(
                "background:#ffff00; color:#000000;"
                " font-family:Monospace; padding:2px 6px;")
            self.msg_lbl.setText(vs.message)
        else:
            self.msg_lbl.setStyleSheet(
                "background:transparent; color:#888888;"
                " font-family:Monospace; padding:2px 6px;")
            self.msg_lbl.setText("")

        self._cols_action.setChecked(vs.show_cols)
        self._cmdbar_action.setChecked(vs.show_command)

        self.editor._sync_scrollbar()
        self.editor.viewport().update()

    def content_rows(self) -> int:
        return self.editor.content_rows()

    def closeEvent(self, event):
        if self.app.buffer.modified:
            self.app._save_and_quit()
        QApplication.instance().quit()
        event.accept()
