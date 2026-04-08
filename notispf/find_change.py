"""FIND and CHANGE engine."""
from __future__ import annotations
from notispf.buffer import Buffer


class FindChangeEngine:
    def __init__(self, buffer: Buffer):
        self.buffer = buffer
        self._last_find: str | None = None
        self._last_pos: tuple[int, int] = (0, 0)

    def find_next(self, pattern: str, from_pos: tuple[int, int] | None = None,
                  case_sensitive: bool = False) -> tuple[int, int] | None:
        self._last_find = pattern
        start_line, start_col = from_pos or self._last_pos
        needle = pattern if case_sensitive else pattern.lower()

        for i in range(len(self.buffer)):
            line_idx = (start_line + i) % len(self.buffer)
            text = self.buffer.lines[line_idx].text
            haystack = text if case_sensitive else text.lower()
            search_from = start_col if i == 0 else 0
            col = haystack.find(needle, search_from)
            if col != -1:
                self._last_pos = (line_idx, col + len(pattern))
                return (line_idx, col)
        return None

    def change_next(self, old: str, new: str,
                    case_sensitive: bool = False) -> int:
        pos = self.find_next(old, self._last_pos, case_sensitive)
        if pos is None:
            return 0
        line_idx, col = pos
        text = self.buffer.lines[line_idx].text
        new_text = text[:col] + new + text[col + len(old):]
        self.buffer.replace_line(line_idx, new_text)
        return 1

    def change_all(self, old: str, new: str,
                   case_sensitive: bool = False) -> int:
        count = 0
        needle = old if case_sensitive else old.lower()
        for i, line in enumerate(self.buffer.lines):
            text = line.text
            haystack = text if case_sensitive else text.lower()
            if needle in haystack:
                # Use proper case replacement
                new_text = (text if case_sensitive else text.lower()).replace(needle, new)
                if not case_sensitive:
                    # Rebuild preserving original case outside matches
                    new_text = _replace_all_nocase(text, old, new)
                self.buffer.replace_line(i, new_text)
                count += text.lower().count(needle)
        return count

    def change_in_range(self, old: str, new: str,
                        label_start: str, label_end: str,
                        case_sensitive: bool = False) -> int:
        start_idx = self.buffer.get_label_index(label_start)
        end_idx = self.buffer.get_label_index(label_end)
        if start_idx is None:
            raise ValueError(f"Label not found: {label_start}")
        if end_idx is None:
            raise ValueError(f"Label not found: {label_end}")
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        count = 0
        needle = old if case_sensitive else old.lower()
        for i in range(start_idx, end_idx + 1):
            text = self.buffer.lines[i].text
            haystack = text if case_sensitive else text.lower()
            if needle in haystack:
                new_text = _replace_all_nocase(text, old, new) if not case_sensitive else text.replace(old, new)
                self.buffer.replace_line(i, new_text)
                count += haystack.count(needle)
        return count


def _replace_all_nocase(text: str, old: str, new: str) -> str:
    result = []
    lower_text = text.lower()
    lower_old = old.lower()
    i = 0
    while i < len(text):
        if lower_text[i:i + len(old)] == lower_old:
            result.append(new)
            i += len(old)
        else:
            result.append(text[i])
            i += 1
    return "".join(result)
