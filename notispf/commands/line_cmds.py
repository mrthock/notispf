"""Single-line prefix command implementations: D, I, R, C, M, A, B."""
from __future__ import annotations
from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry, CommandSpec, EditorResult


def cmd_delete(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    if line_idx >= len(buffer):
        return EditorResult(success=False, message="Invalid line")
    count = min(count, len(buffer) - line_idx)
    buffer.delete_lines(line_idx, count)
    return EditorResult(success=True, cursor_hint=min(line_idx, len(buffer) - 1))


def cmd_insert(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    buffer.insert_lines(line_idx, [""] * count)
    return EditorResult(success=True, cursor_hint=line_idx + 1)


def cmd_repeat(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    buffer.repeat_lines(line_idx, 1, count)
    return EditorResult(success=True, cursor_hint=line_idx)


def cmd_copy(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    texts = [buffer.lines[i].text for i in range(line_idx, min(line_idx + count, len(buffer)))]
    buffer.push_clipboard(texts)
    return EditorResult(success=True, message=f"{len(texts)} line(s) copied — place with A or B")


def cmd_move(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    count = min(count, len(buffer) - line_idx)
    texts = [buffer.lines[i].text for i in range(line_idx, line_idx + count)]
    buffer.push_clipboard(texts)
    buffer.delete_lines(line_idx, count)
    return EditorResult(success=True, message=f"{len(texts)} line(s) moved — place with A or B",
                        cursor_hint=min(line_idx, len(buffer) - 1))


def _overlay_text(source: str, dest: str) -> str:
    """Merge source onto dest: source chars replace spaces in dest."""
    result = []
    for i in range(max(len(source), len(dest))):
        d = dest[i] if i < len(dest) else ' '
        s = source[i] if i < len(source) else ' '
        result.append(d if d != ' ' else s)
    return ''.join(result).rstrip()


def cmd_after(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    clipboard = buffer.pop_clipboard()
    if not clipboard:
        return EditorResult(success=False, message="Nothing in clipboard")
    if buffer.clipboard_is_overlay:
        return _do_overlay(buffer, line_idx + 1, clipboard)
    buffer.insert_lines(line_idx, clipboard)
    return EditorResult(success=True, cursor_hint=line_idx + 1)


def cmd_before(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    clipboard = buffer.pop_clipboard()
    if not clipboard:
        return EditorResult(success=False, message="Nothing in clipboard")
    if buffer.clipboard_is_overlay:
        return _do_overlay(buffer, line_idx, clipboard)
    buffer.insert_lines(line_idx - 1, clipboard)
    return EditorResult(success=True, cursor_hint=line_idx)


def _do_overlay(buffer: Buffer, start_idx: int, clipboard: list[str]) -> EditorResult:
    """Overlay clipboard lines onto existing lines starting at start_idx."""
    for i, src in enumerate(clipboard):
        dest_idx = start_idx + i
        if dest_idx >= len(buffer):
            break
        dest = buffer.lines[dest_idx].text
        buffer.replace_line(dest_idx, _overlay_text(src, dest))
    return EditorResult(success=True, cursor_hint=start_idx)


def register(registry: CommandRegistry) -> None:
    registry.register_line_cmd(CommandSpec("D", cmd_delete, description="Delete line(s)"))
    registry.register_line_cmd(CommandSpec("I", cmd_insert, description="Insert blank line(s)"))
    registry.register_line_cmd(CommandSpec("R", cmd_repeat, description="Repeat line(s)"))
    registry.register_line_cmd(CommandSpec("C", cmd_copy, description="Copy line(s) to clipboard"))
    registry.register_line_cmd(CommandSpec("M", cmd_move, description="Move line(s) to clipboard"))
    registry.register_line_cmd(CommandSpec("A", cmd_after, description="Paste clipboard after this line"))
    registry.register_line_cmd(CommandSpec("B", cmd_before, description="Paste clipboard before this line"))
