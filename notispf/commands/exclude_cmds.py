"""Exclude/show prefix command implementations: X, XX, S, SS."""
from __future__ import annotations
from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry, CommandSpec, EditorResult


def cmd_exclude(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    count = min(count, len(buffer) - line_idx)
    buffer.exclude_lines(line_idx, count)
    return EditorResult(success=True, message=f"{count} line(s) excluded")


def cmd_show(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    # If count==1 and the line is excluded, show the full fold group
    if count == 1 and line_idx < len(buffer) and buffer.lines[line_idx].excluded:
        buffer.show_lines(line_idx, count=None)
    else:
        buffer.show_lines(line_idx, count)
    return EditorResult(success=True, message="Line(s) shown")


def cmd_exclude_block(buffer: Buffer, start_idx: int, end_idx: int, numeric_arg: int = 1) -> EditorResult:
    count = end_idx - start_idx + 1
    buffer.exclude_lines(start_idx, count)
    return EditorResult(success=True, message=f"{count} line(s) excluded")


def cmd_show_block(buffer: Buffer, start_idx: int, end_idx: int, numeric_arg: int = 1) -> EditorResult:
    count = end_idx - start_idx + 1
    buffer.show_lines(start_idx, count)
    return EditorResult(success=True, message=f"{count} line(s) shown")


def register(registry: CommandRegistry) -> None:
    registry.register_line_cmd(CommandSpec("X",  cmd_exclude,       description="Exclude line(s) from display"))
    registry.register_line_cmd(CommandSpec("S",  cmd_show,          description="Show (un-exclude) line(s)"))
    registry.register_line_cmd(CommandSpec("XX", cmd_exclude_block,  is_block=True, description="Exclude block"))
    registry.register_line_cmd(CommandSpec("SS", cmd_show_block,     is_block=True, description="Show block"))
