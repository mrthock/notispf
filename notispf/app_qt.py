"""PyQt6 application controller — subclasses App, replaces the curses I/O layer."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

from notispf.app import App
from notispf.display import Display, TEXT_OFFSET


class AppQt(App):
    """App subclass that runs a PyQt6 window instead of a curses terminal."""

    # Assigned in run() before any key handlers are called.
    window: "NotispfWindow"  # noqa: F821 — forward ref, imported lazily

    def run(self) -> None:
        from notispf.display_qt import NotispfWindow
        qt_app = QApplication.instance() or QApplication(sys.argv)
        self.window = NotispfWindow(self)
        self.window.show()
        self._render()
        qt_app.exec()

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def _render(self) -> None:
        from notispf.display_qt import PREFIX_WIDTH, SEP_WIDTH
        vs  = self.vs
        buf = self.buffer

        vs.screen_rows   = self.window.editor.content_rows() + 2
        vs.screen_cols   = self.window.editor.content_cols() + PREFIX_WIDTH + SEP_WIDTH
        vs.pending_prefixes = dict(self.prefix_area._pending)

        if vs.prefix_mode:
            if vs.prefix_input:
                vs.pending_prefixes[vs.cursor_line] = vs.prefix_input
            else:
                vs.pending_prefixes.pop(vs.cursor_line, None)

        if self.prefix_area._open_block:
            vs.open_block_line = self.prefix_area._open_block.line_idx
            vs.open_block_cmd  = self.prefix_area._open_block.cmd_name
        else:
            vs.open_block_line = None
            vs.open_block_cmd  = ""

        if self._quit_flag:
            QApplication.instance().quit()
            return

        self.window.refresh()

    def _content_rows(self) -> int:
        return self.window.editor.content_rows()

    def _save_and_quit(self) -> None:
        if self.buffer.modified and self.buffer.filepath:
            try:
                self.buffer.save_file()
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self.window,
                    "Save Failed",
                    f"Could not save '{self.buffer.filepath}':\n{e}\n\nYour file has NOT been saved.",
                )
                self._quit_flag = False  # prevent quit so user can retry or cancel

    # ------------------------------------------------------------------
    # Qt key handling (called from EditorViewport.keyPressEvent)
    # ------------------------------------------------------------------

    def _handle_key_qt(self, event: QKeyEvent) -> None:
        vs   = self.vs
        key  = event.key()
        mods = event.modifiers()

        if vs.help_mode:
            self.buffer.end_edit_group()
            self._handle_help_key_qt(event)
            self._render()
            return

        if vs.prefix_mode:
            self.buffer.end_edit_group()
            self._handle_prefix_key_qt(event)
            self._render()
            return

        # Command mode keys are handled by NotispfWindow.eventFilter.
        if vs.command_mode:
            return

        # End edit group for non-typing keys
        _typing = {Qt.Key.Key_Backspace, Qt.Key.Key_Delete,
                   Qt.Key.Key_Return, Qt.Key.Key_Enter}
        if key not in _typing:
            ch = event.text()
            if not (ch and len(ch) == 1 and 32 <= ord(ch) <= 126
                    and mods in (Qt.KeyboardModifier.NoModifier,
                                 Qt.KeyboardModifier.ShiftModifier)):
                self.buffer.end_edit_group()

        content_rows = self._content_rows()

        if key == Qt.Key.Key_Up:
            if vs.show_command and vs.cursor_line <= vs.top_line:
                vs.command_mode = True
                vs.message = ""
            else:
                self._move_cursor(-1)

        elif key == Qt.Key.Key_Down:
            self._move_cursor(1)

        elif key in (Qt.Key.Key_PageUp, Qt.Key.Key_F7):
            self._move_cursor(-content_rows)

        elif key in (Qt.Key.Key_PageDown, Qt.Key.Key_F8):
            self._move_cursor(content_rows)

        elif key == Qt.Key.Key_F10:
            vs.col_offset = max(0, vs.col_offset - (vs.screen_cols - TEXT_OFFSET))

        elif key == Qt.Key.Key_F11:
            vs.col_offset += vs.screen_cols - TEXT_OFFSET

        elif key == Qt.Key.Key_Home:                # Home — focus command bar
            if not vs.show_command:
                vs.show_command = True
            vs.command_mode = True
            vs.message = ""
            self.window.cmd_input.setFocus()

        elif key == Qt.Key.Key_A and mods & Qt.KeyboardModifier.ControlModifier:
            vs.cursor_col = 0
            self._scroll_col_to_cursor()

        elif key == Qt.Key.Key_End or (
                key == Qt.Key.Key_E and mods & Qt.KeyboardModifier.ControlModifier):
            if self.buffer.lines:
                vs.cursor_col = len(self.buffer.lines[vs.cursor_line].text)
            self._scroll_col_to_cursor()

        elif key == Qt.Key.Key_Left:
            vs.cursor_col = max(0, vs.cursor_col - 1)
            self._scroll_col_to_cursor()

        elif key == Qt.Key.Key_Right:
            if self.buffer.lines:
                vs.cursor_col = min(
                    len(self.buffer.lines[vs.cursor_line].text),
                    vs.cursor_col + 1)
            self._scroll_col_to_cursor()

        elif key == Qt.Key.Key_F6:
            if not vs.show_command:
                vs.show_command = True
            vs.command_mode = True
            vs.message = ""

        elif key == Qt.Key.Key_F1:
            vs.help_mode   = True
            vs.help_scroll = 0
            vs.message     = ""

        elif key == Qt.Key.Key_F3:
            self._save_and_quit()
            self._quit_flag = True

        elif key == Qt.Key.Key_F12:
            self._quit_flag = True

        elif key == Qt.Key.Key_F5:
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

        elif key == Qt.Key.Key_Tab:
            self._move_cursor(1, skip_excluded=False)
            vs.prefix_mode  = True
            vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")
            vs.message = "Type prefix command, Enter to execute, Esc to cancel"

        elif key == Qt.Key.Key_Backtab:  # Shift+Tab
            if vs.show_command and vs.cursor_line <= vs.top_line:
                vs.command_mode = True
                vs.message = ""
            else:
                self._move_cursor(-1, skip_excluded=False)
                vs.prefix_mode  = True
                vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")
                vs.message = "Type prefix command, Enter to execute, Esc to cancel"

        elif key == Qt.Key.Key_Z and mods & Qt.KeyboardModifier.ControlModifier:
            vs.message = "Undone" if self.buffer.undo() else "Nothing to undo"

        elif key == Qt.Key.Key_Y and mods & Qt.KeyboardModifier.ControlModifier:
            vs.message = "Redone" if self.buffer.redo() else "Nothing to redo"

        elif key == Qt.Key.Key_Backspace:
            self._backspace()

        elif key == Qt.Key.Key_Delete:
            self._delete_char()

        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._enter_key()

        else:
            ch = event.text()
            if ch and len(ch) == 1 and 32 <= ord(ch) <= 126:
                self._insert_char(ch)

        self._render()

    def _handle_help_key_qt(self, event: QKeyEvent) -> None:
        vs           = self.vs
        key          = event.key()
        content_rows = self._content_rows()
        max_scroll   = max(0, len(Display._HELP_LINES) - content_rows)

        if key in (Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_F8):
            step = content_rows if key != Qt.Key.Key_Down else 1
            vs.help_scroll = min(vs.help_scroll + step, max_scroll)
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_F7):
            step = content_rows if key != Qt.Key.Key_Up else 1
            vs.help_scroll = max(vs.help_scroll - step, 0)
        else:
            vs.help_mode   = False
            vs.help_scroll = 0

    def _handle_prefix_key_qt(self, event: QKeyEvent) -> None:
        vs  = self.vs
        key = event.key()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._stage_current_prefix()
            vs.prefix_input = ""
            vs.message      = ""
            self._execute_staged_prefixes()
            # Stay in prefix mode at the current line so the user can chain commands.
            vs.prefix_mode  = True
            vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")

        elif key == Qt.Key.Key_Up:
            self._stage_current_prefix()
            self._move_cursor(-1, skip_excluded=False)
            vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")

        elif key == Qt.Key.Key_Down:
            self._stage_current_prefix()
            self._move_cursor(1, skip_excluded=False)
            vs.prefix_input = self.prefix_area._pending.get(vs.cursor_line, "")

        elif key == Qt.Key.Key_Escape:
            vs.prefix_mode  = False
            vs.prefix_input = ""
            vs.message      = ""
            self.prefix_area._pending.clear()
            self.prefix_area.cancel_open_block()

        elif key == Qt.Key.Key_Tab:
            self._stage_current_prefix()
            vs.prefix_mode  = False
            vs.prefix_input = ""
            vs.message      = ""

        elif key == Qt.Key.Key_Backtab:
            self._stage_current_prefix()
            vs.prefix_mode  = False
            vs.prefix_input = ""
            vs.message      = ""
            self._move_cursor(-1, skip_excluded=False)

        elif key == Qt.Key.Key_Home:
            vs.prefix_mode  = False
            vs.prefix_input = ""
            vs.message      = ""
            if not vs.show_command:
                vs.show_command = True
            vs.command_mode = True
            self.window.cmd_input.setFocus()

        elif key == Qt.Key.Key_Backspace:
            vs.prefix_input = vs.prefix_input[:-1]

        else:
            ch = event.text()
            if ch and len(ch) == 1 and 32 <= ord(ch) <= 126 and len(vs.prefix_input) < 6:
                vs.prefix_input += ch
