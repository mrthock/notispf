"""Overlay prefix command implementations: O, OO."""
from __future__ import annotations
from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry, CommandSpec, EditorResult


def cmd_overlay(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    count = min(count, len(buffer) - line_idx)
    texts = [buffer.lines[i].text for i in range(line_idx, line_idx + count)]
    buffer.push_clipboard(texts, overlay=True)
    return EditorResult(success=True, message=f"{len(texts)} line(s) copied for overlay — place with A or B")


def cmd_overlay_block(buffer: Buffer, start_idx: int, end_idx: int) -> EditorResult:
    texts = [buffer.lines[i].text for i in range(start_idx, end_idx + 1)]
    buffer.push_clipboard(texts, overlay=True)
    return EditorResult(success=True, message=f"{len(texts)} line(s) copied for overlay — place with A or B")


def register(registry: CommandRegistry) -> None:
    registry.register_line_cmd(CommandSpec("O",  cmd_overlay,       description="Copy line(s) to overlay clipboard"))
    registry.register_line_cmd(CommandSpec("OO", cmd_overlay_block,  is_block=True, description="Copy block to overlay clipboard"))
