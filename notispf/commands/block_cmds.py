"""Block prefix command implementations: DD, CC, MM, RR, OO."""
from __future__ import annotations
from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry, CommandSpec, EditorResult
from notispf.commands.line_cmds import overlay_text


def cmd_delete_block(buffer: Buffer, start_idx: int, end_idx: int, numeric_arg: int = 1) -> EditorResult:
    count = end_idx - start_idx + 1
    buffer.delete_lines(start_idx, count)
    return EditorResult(success=True, cursor_hint=min(start_idx, len(buffer) - 1))


def cmd_copy_block(buffer: Buffer, start_idx: int, end_idx: int, numeric_arg: int = 1) -> EditorResult:
    texts = [buffer.lines[i].text for i in range(start_idx, end_idx + 1)]
    buffer.push_clipboard(texts)
    return EditorResult(success=True, message=f"{len(texts)} line(s) copied — place with A or B")


def cmd_move_block(buffer: Buffer, start_idx: int, end_idx: int, numeric_arg: int = 1) -> EditorResult:
    texts = [buffer.lines[i].text for i in range(start_idx, end_idx + 1)]
    buffer.push_clipboard(texts)
    count = end_idx - start_idx + 1
    buffer.delete_lines(start_idx, count)
    return EditorResult(success=True, message=f"{len(texts)} line(s) moved — place with A or B",
                        cursor_hint=min(start_idx, len(buffer) - 1))


def cmd_repeat_block(buffer: Buffer, start_idx: int, end_idx: int, numeric_arg: int = 1) -> EditorResult:
    count = end_idx - start_idx + 1
    buffer.repeat_lines(start_idx, count, 1)
    return EditorResult(success=True, cursor_hint=start_idx)


def cmd_overlay_block(buffer: Buffer, start_idx: int, end_idx: int, numeric_arg: int = 1) -> EditorResult:
    """OO — overlay destination block: merge clipboard into each line in the range."""
    clipboard = buffer.pop_clipboard()
    if not clipboard:
        return EditorResult(success=False, message="Nothing in clipboard")
    buffer.begin_edit_group()
    for i, dest_idx in enumerate(range(start_idx, end_idx + 1)):
        src = clipboard[i % len(clipboard)]
        buffer.replace_line(dest_idx, overlay_text(src, buffer.lines[dest_idx].text))
    buffer.end_edit_group()
    return EditorResult(success=True, cursor_hint=start_idx)


def cmd_indent_right_block(buffer: Buffer, start_idx: int, end_idx: int, numeric_arg: int = 1) -> EditorResult:
    """Shift all lines in block right by numeric_arg columns."""
    buffer.begin_edit_group()
    for i in range(start_idx, end_idx + 1):
        buffer.replace_line(i, " " * numeric_arg + buffer.lines[i].text)
    buffer.end_edit_group()
    return EditorResult(success=True)


def cmd_indent_left_block(buffer: Buffer, start_idx: int, end_idx: int, numeric_arg: int = 1) -> EditorResult:
    """Shift all lines in block left by numeric_arg columns, removing up to that many leading spaces."""
    buffer.begin_edit_group()
    for i in range(start_idx, end_idx + 1):
        text = buffer.lines[i].text
        leading = len(text) - len(text.lstrip(" "))
        buffer.replace_line(i, text[min(numeric_arg, leading):])
    buffer.end_edit_group()
    return EditorResult(success=True)


def register(registry: CommandRegistry) -> None:
    registry.register_line_cmd(CommandSpec("DD", cmd_delete_block, is_block=True, description="Delete block"))
    registry.register_line_cmd(CommandSpec("CC", cmd_copy_block, is_block=True, description="Copy block to clipboard"))
    registry.register_line_cmd(CommandSpec("MM", cmd_move_block, is_block=True, description="Move block to clipboard"))
    registry.register_line_cmd(CommandSpec("RR", cmd_repeat_block, is_block=True, description="Repeat block"))
    registry.register_line_cmd(CommandSpec("OO", cmd_overlay_block, is_block=True, description="Overlay clipboard onto block"))
    registry.register_line_cmd(CommandSpec(">>", cmd_indent_right_block, is_block=True, description="Indent block right n columns"))
    registry.register_line_cmd(CommandSpec("<<", cmd_indent_left_block, is_block=True, description="Indent block left n columns"))
