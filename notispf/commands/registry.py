from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class EditorResult:
    success: bool
    message: str = ""
    cursor_hint: int | None = None
    cleared_prefixes: list[int] = field(default_factory=list)


@dataclass
class CommandSpec:
    name: str
    handler: Callable
    is_block: bool = False
    description: str = ""


class CommandRegistry:
    def __init__(self):
        self._line_cmds: dict[str, CommandSpec] = {}

    def register_line_cmd(self, spec: CommandSpec) -> None:
        self._line_cmds[spec.name.upper()] = spec

    def get_line_cmd(self, name: str) -> CommandSpec | None:
        return self._line_cmds.get(name.upper())

    def normalize(self, raw: str) -> tuple[str, int]:
        """Parse a prefix entry into (command_name, numeric_arg).

        Examples:
            'D'   -> ('D', 1)
            'D3'  -> ('D', 3)
            'DD'  -> ('DD', 1)
            'RR'  -> ('RR', 1)
            'I5'  -> ('I', 5)
        """
        raw = raw.strip().upper()
        if not raw:
            return ("", 1)

        # Block indent/dedent: >> or <<
        if len(raw) >= 2 and raw[:2] in (">>", "<<"):
            suffix = raw[2:]
            count = int(suffix) if suffix.isdigit() else 1
            return (raw[:2], count)

        # Single indent/dedent: > or <
        if raw[0] in (">", "<"):
            suffix = raw[1:]
            count = int(suffix) if suffix.isdigit() else 1
            return (raw[0], count)

        # Block commands: repeated letter (DD, CC, MM, RR)
        if len(raw) >= 2 and raw[0] == raw[1] and raw[1].isalpha():
            return (raw[:2], 1)

        # Single letter + optional digits
        cmd = ""
        for ch in raw:
            if ch.isalpha():
                cmd += ch
            else:
                break
        suffix = raw[len(cmd):]
        count = int(suffix) if suffix.isdigit() else 1
        return (cmd, count)
