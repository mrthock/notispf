"""Block prefix command implementations: DD, CC, MM, RR."""
from __future__ import annotations
from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry, CommandSpec, EditorResult


def cmd_delete_block(buffer: Buffer, start_idx: int, end_idx: int) -> EditorResult:
    count = end_idx - start_idx + 1
    buffer.delete_lines(start_idx, count)
    return EditorResult(success=True, cursor_hint=min(start_idx, len(buffer) - 1))


def cmd_copy_block(buffer: Buffer, start_idx: int, end_idx: int) -> EditorResult:
    texts = [buffer.lines[i].text for i in range(start_idx, end_idx + 1)]
    buffer.push_clipboard(texts)
    return EditorResult(success=True, message=f"{len(texts)} line(s) copied — place with A or B")


def cmd_move_block(buffer: Buffer, start_idx: int, end_idx: int) -> EditorResult:
    texts = [buffer.lines[i].text for i in range(start_idx, end_idx + 1)]
    buffer.push_clipboard(texts)
    count = end_idx - start_idx + 1
    buffer.delete_lines(start_idx, count)
    return EditorResult(success=True, message=f"{len(texts)} line(s) moved — place with A or B",
                        cursor_hint=min(start_idx, len(buffer) - 1))


def cmd_repeat_block(buffer: Buffer, start_idx: int, end_idx: int) -> EditorResult:
    count = end_idx - start_idx + 1
    buffer.repeat_lines(start_idx, count, 1)
    return EditorResult(success=True, cursor_hint=start_idx)


def register(registry: CommandRegistry) -> None:
    registry.register_line_cmd(CommandSpec("DD", cmd_delete_block, is_block=True, description="Delete block"))
    registry.register_line_cmd(CommandSpec("CC", cmd_copy_block, is_block=True, description="Copy block to clipboard"))
    registry.register_line_cmd(CommandSpec("MM", cmd_move_block, is_block=True, description="Move block to clipboard"))
    registry.register_line_cmd(CommandSpec("RR", cmd_repeat_block, is_block=True, description="Repeat block"))
