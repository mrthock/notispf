from __future__ import annotations
import copy
from dataclasses import dataclass, field


@dataclass
class Line:
    text: str
    label: str | None = None
    modified: bool = False


class Buffer:
    def __init__(self, filepath: str | None = None):
        self.lines: list[Line] = []
        self.filepath: str | None = filepath
        self.modified: bool = False
        self._undo_stack: list[list[Line]] = []
        self._redo_stack: list[list[Line]] = []
        self._clipboard: list[str] = []

        if filepath:
            self.load_file(filepath)

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def load_file(self, filepath: str) -> None:
        with open(filepath, "r", encoding="utf-8") as f:
            self.lines = [Line(text=line.rstrip("\n")) for line in f]
        self.filepath = filepath
        self.modified = False
        self._undo_stack.clear()
        self._redo_stack.clear()

    def save_file(self, filepath: str | None = None) -> None:
        target = filepath or self.filepath
        if target is None:
            raise ValueError("No filepath specified")
        with open(target, "w", encoding="utf-8") as f:
            for line in self.lines:
                f.write(line.text + "\n")
        self.filepath = target
        self.modified = False

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def _snapshot(self) -> None:
        self._undo_stack.append(copy.deepcopy(self.lines))
        self._redo_stack.clear()

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(copy.deepcopy(self.lines))
        self.lines = self._undo_stack.pop()
        self.modified = True
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(copy.deepcopy(self.lines))
        self.lines = self._redo_stack.pop()
        self.modified = True
        return True

    # ------------------------------------------------------------------
    # Mutations — all push an undo snapshot first
    # ------------------------------------------------------------------

    def insert_lines(self, after_idx: int, texts: list[str]) -> None:
        """Insert lines after after_idx. Use -1 to insert at the beginning."""
        self._snapshot()
        new_lines = [Line(text=t, modified=True) for t in texts]
        insert_pos = after_idx + 1
        self.lines[insert_pos:insert_pos] = new_lines
        self.modified = True

    def delete_lines(self, start_idx: int, count: int = 1) -> None:
        self._snapshot()
        del self.lines[start_idx:start_idx + count]
        self.modified = True

    def replace_line(self, idx: int, text: str) -> None:
        self._snapshot()
        self.lines[idx] = Line(text=text, label=self.lines[idx].label, modified=True)
        self.modified = True

    def repeat_lines(self, start_idx: int, count: int, times: int) -> None:
        """Repeat `count` lines starting at start_idx, inserting `times` copies after."""
        self._snapshot()
        block = [Line(text=l.text, modified=True) for l in self.lines[start_idx:start_idx + count]]
        insert_pos = start_idx + count
        for _ in range(times):
            self.lines[insert_pos:insert_pos] = copy.deepcopy(block)
            insert_pos += count
        self.modified = True

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def push_clipboard(self, lines: list[str]) -> None:
        self._clipboard = list(lines)

    def pop_clipboard(self) -> list[str]:
        return list(self._clipboard)

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------

    def set_label(self, idx: int, label: str) -> None:
        # Remove any existing line with this label first
        for line in self.lines:
            if line.label == label:
                line.label = None
        self.lines[idx].label = label

    def get_label_index(self, label: str) -> int | None:
        for i, line in enumerate(self.lines):
            if line.label == label:
                return i
        return None

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.lines)

    def is_empty(self) -> bool:
        return len(self.lines) == 0
