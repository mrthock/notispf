"""FIND and CHANGE engine."""
from __future__ import annotations
from notispf.buffer import Buffer


class FindChangeEngine:
    def __init__(self, buffer: Buffer):
        self.buffer = buffer
        self._last_find: str | None = None
        self._last_pos: tuple[int, int] = (0, 0)

    def find_next(self, pattern: str, from_pos: tuple[int, int] | None = None,
                  case_sensitive: bool = False,
                  col: int | None = None) -> tuple[int, int] | None:
        """Find pattern, optionally restricted to a specific column.

        col is 1-based (ISPF convention). When given, the pattern must begin
        at exactly that column — lines where it appears elsewhere are skipped.
        """
        self._last_find = pattern
        start_line, start_col = from_pos or self._last_pos
        needle = pattern if case_sensitive else pattern.lower()
        # Convert 1-based col to 0-based index
        required_col = (col - 1) if col is not None else None

        for i in range(len(self.buffer)):
            line_idx = (start_line + i) % len(self.buffer)
            if self.buffer.lines[line_idx].excluded:
                continue
            text = self.buffer.lines[line_idx].text
            haystack = text if case_sensitive else text.lower()

            if required_col is not None:
                # Pattern must start at exactly the required column
                if haystack[required_col:required_col + len(needle)] == needle:
                    self._last_pos = (line_idx, required_col + len(pattern))
                    return (line_idx, required_col)
            else:
                search_from = start_col if i == 0 else 0
                found_col = haystack.find(needle, search_from)
                if found_col != -1:
                    self._last_pos = (line_idx, found_col + len(pattern))
                    return (line_idx, found_col)
        return None

    def change_next(self, old: str, new: str,
                    case_sensitive: bool = False,
                    col: int | None = None) -> int:
        pos = self.find_next(old, self._last_pos, case_sensitive, col=col)
        if pos is None:
            return 0
        line_idx, match_col = pos
        text = self.buffer.lines[line_idx].text
        new_text = text[:match_col] + new + text[match_col + len(old):]
        self.buffer.replace_line(line_idx, new_text)
        return 1

    def change_all(self, old: str, new: str,
                   case_sensitive: bool = False,
                   col: int | None = None) -> int:
        """Replace all occurrences. If col is given (1-based), only replace
        occurrences that start at exactly that column."""
        count = 0
        needle = old if case_sensitive else old.lower()
        required_col = (col - 1) if col is not None else None

        self.buffer.begin_edit_group()
        for i, line in enumerate(self.buffer.lines):
            if line.excluded:
                continue
            text = line.text
            haystack = text if case_sensitive else text.lower()
            if required_col is not None:
                if haystack[required_col:required_col + len(needle)] == needle:
                    new_text = text[:required_col] + new + text[required_col + len(old):]
                    self.buffer.replace_line(i, new_text)
                    count += 1
            else:
                if needle in haystack:
                    new_text = _replace_all_nocase(text, old, new) if not case_sensitive \
                        else text.replace(old, new)
                    self.buffer.replace_line(i, new_text)
                    count += haystack.count(needle)
        self.buffer.end_edit_group()
        return count

    def change_in_range(self, old: str, new: str,
                        label_start: str, label_end: str,
                        case_sensitive: bool = False,
                        col: int | None = None) -> int:
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
        required_col = (col - 1) if col is not None else None

        self.buffer.begin_edit_group()
        for i in range(start_idx, end_idx + 1):
            if self.buffer.lines[i].excluded:
                continue
            text = self.buffer.lines[i].text
            haystack = text if case_sensitive else text.lower()
            if required_col is not None:
                if haystack[required_col:required_col + len(needle)] == needle:
                    new_text = text[:required_col] + new + text[required_col + len(old):]
                    self.buffer.replace_line(i, new_text)
                    count += 1
            else:
                if needle in haystack:
                    new_text = _replace_all_nocase(text, old, new) if not case_sensitive \
                        else text.replace(old, new)
                    self.buffer.replace_line(i, new_text)
                    count += haystack.count(needle)
        self.buffer.end_edit_group()
        return count


    def exclude_matching(self, pattern: str, limit: int | None = None,
                         case_sensitive: bool = False) -> int:
        """Exclude lines containing pattern from display.
        limit=None means exclude all matches. Returns count excluded."""
        needle = pattern if case_sensitive else pattern.lower()
        count = 0
        for i, line in enumerate(self.buffer.lines):
            if line.excluded:
                continue
            haystack = line.text if case_sensitive else line.text.lower()
            if needle in haystack:
                self.buffer.lines[i].excluded = True
                count += 1
                if limit is not None and count >= limit:
                    break
        return count

    def delete_excluded(self) -> int:
        """Delete all excluded lines. Returns count of lines deleted."""
        to_delete = [i for i, line in enumerate(self.buffer.lines) if line.excluded]
        self.buffer.begin_edit_group()
        for i in reversed(to_delete):
            self.buffer.delete_lines(i, 1)
        self.buffer.end_edit_group()
        return len(to_delete)

    def delete_non_excluded(self) -> int:
        """Delete all non-excluded lines. Returns count of lines deleted."""
        to_delete = [i for i, line in enumerate(self.buffer.lines) if not line.excluded]
        self.buffer.begin_edit_group()
        for i in reversed(to_delete):
            self.buffer.delete_lines(i, 1)
        self.buffer.end_edit_group()
        return len(to_delete)

    def delete_matching(self, pattern: str, limit: int | None = None,
                        case_sensitive: bool = False) -> int:
        """Delete lines containing pattern. limit=None means delete all matches.
        Excluded lines are never deleted. Returns count of lines deleted."""
        needle = pattern if case_sensitive else pattern.lower()
        to_delete = []
        for i, line in enumerate(self.buffer.lines):
            if line.excluded:
                continue
            haystack = line.text if case_sensitive else line.text.lower()
            if needle in haystack:
                to_delete.append(i)
                if limit is not None and len(to_delete) >= limit:
                    break

        # Delete in reverse order so indices stay valid
        self.buffer.begin_edit_group()
        for i in reversed(to_delete):
            self.buffer.delete_lines(i, 1)
        self.buffer.end_edit_group()
        return len(to_delete)


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
