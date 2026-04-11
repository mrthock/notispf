"""Single-line prefix command implementations: D, I, R, C, M, A, B, HEX, HEXB."""
from __future__ import annotations
from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry, CommandSpec, EditorResult


# ---------------------------------------------------------------------------
# Hex utilities (used by prefix commands and HEX ON/OFF command line)
# ---------------------------------------------------------------------------

def line_to_hex(text: str) -> str:
    """Convert a text line to space-separated uppercase hex bytes."""
    return ' '.join(f'{ord(c):02X}' for c in text)


def hex_to_line(hex_str: str) -> str:
    """Convert a space-separated hex string back to text. Raises ValueError on bad input."""
    tokens = hex_str.split()
    if not tokens:
        return ''
    return ''.join(chr(int(t, 16)) for t in tokens)


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
    return EditorResult(success=True, message=f"{len(texts)} line(s) copied — place with A, B, or O/OO")


def cmd_move(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    count = min(count, len(buffer) - line_idx)
    texts = [buffer.lines[i].text for i in range(line_idx, line_idx + count)]
    buffer.push_clipboard(texts)
    buffer.delete_lines(line_idx, count)
    return EditorResult(success=True, message=f"{len(texts)} line(s) moved — place with A, B, or O/OO",
                        cursor_hint=min(line_idx, len(buffer) - 1))


def cmd_after(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    clipboard = buffer.pop_clipboard()
    if not clipboard:
        return EditorResult(success=False, message="Nothing in clipboard")
    buffer.insert_lines(line_idx, clipboard)
    return EditorResult(success=True, cursor_hint=line_idx + 1)


def cmd_before(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    clipboard = buffer.pop_clipboard()
    if not clipboard:
        return EditorResult(success=False, message="Nothing in clipboard")
    buffer.insert_lines(line_idx - 1, clipboard)
    return EditorResult(success=True, cursor_hint=line_idx)


def overlay_text(source: str, dest: str) -> str:
    """Merge source onto dest: source chars replace spaces in dest."""
    result = []
    for i in range(max(len(source), len(dest))):
        d = dest[i] if i < len(dest) else ' '
        s = source[i] if i < len(source) else ' '
        result.append(d if d != ' ' else s)
    return ''.join(result).rstrip()


def cmd_overlay(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    """O — overlay destination: merge clipboard into this line (and count-1 below)."""
    clipboard = buffer.pop_clipboard()
    if not clipboard:
        return EditorResult(success=False, message="Nothing in clipboard")
    for i in range(count):
        dest_idx = line_idx + i
        if dest_idx >= len(buffer):
            break
        src = clipboard[i % len(clipboard)]
        buffer.replace_line(dest_idx, overlay_text(src, buffer.lines[dest_idx].text))
    return EditorResult(success=True, cursor_hint=line_idx)


def cmd_indent_right(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    """Shift line right by count columns."""
    buffer.replace_line(line_idx, " " * count + buffer.lines[line_idx].text)
    return EditorResult(success=True)


def cmd_indent_left(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    """Shift line left by count columns, removing up to count leading spaces."""
    text = buffer.lines[line_idx].text
    leading = len(text) - len(text.lstrip(" "))
    buffer.replace_line(line_idx, text[min(count, leading):])
    return EditorResult(success=True)


def cmd_hex(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    """HEX — replace this line with its hex representation."""
    text = buffer.lines[line_idx].text
    buffer.replace_line(line_idx, line_to_hex(text))
    return EditorResult(success=True)


def cmd_hex_below(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    """HEXB — insert a hex copy of this line below it."""
    text = buffer.lines[line_idx].text
    buffer.insert_lines(line_idx, [line_to_hex(text)])
    return EditorResult(success=True, cursor_hint=line_idx)


def cmd_hex_to_ascii(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    """HEXA — convert a hex line back to its ASCII text representation."""
    text = buffer.lines[line_idx].text
    try:
        buffer.replace_line(line_idx, hex_to_line(text))
    except ValueError:
        return EditorResult(success=False, message="HEXA: line is not valid hex")
    return EditorResult(success=True)


def register(registry: CommandRegistry) -> None:
    registry.register_line_cmd(CommandSpec("D", cmd_delete, description="Delete line(s)"))
    registry.register_line_cmd(CommandSpec("I", cmd_insert, description="Insert blank line(s)"))
    registry.register_line_cmd(CommandSpec("R", cmd_repeat, description="Repeat line(s)"))
    registry.register_line_cmd(CommandSpec("C", cmd_copy, description="Copy line(s) to clipboard"))
    registry.register_line_cmd(CommandSpec("M", cmd_move, description="Move line(s) to clipboard"))
    registry.register_line_cmd(CommandSpec("A", cmd_after, description="Paste clipboard after this line"))
    registry.register_line_cmd(CommandSpec("B", cmd_before, description="Paste clipboard before this line"))
    registry.register_line_cmd(CommandSpec("O", cmd_overlay, description="Overlay clipboard onto this line"))
    registry.register_line_cmd(CommandSpec(">", cmd_indent_right, description="Indent line right n columns"))
    registry.register_line_cmd(CommandSpec("<", cmd_indent_left, description="Indent line left n columns"))
    registry.register_line_cmd(CommandSpec("HEX", cmd_hex, description="Replace line with hex representation"))
    registry.register_line_cmd(CommandSpec("HEXB", cmd_hex_below, description="Insert hex copy of line below"))
    registry.register_line_cmd(CommandSpec("HEXA", cmd_hex_to_ascii, description="Convert hex line back to ASCII"))
