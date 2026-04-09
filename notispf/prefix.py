"""Prefix area state machine."""
from __future__ import annotations
from dataclasses import dataclass
from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry, EditorResult


@dataclass
class PrefixEntry:
    line_idx: int
    raw_input: str
    cmd_name: str
    numeric_arg: int
    is_block: bool
    pair_idx: int | None = None


class PrefixArea:
    def __init__(self, buffer: Buffer, registry: CommandRegistry):
        self.buffer = buffer
        self.registry = registry
        self._pending: dict[int, str] = {}       # line_idx -> raw input
        self._open_block: PrefixEntry | None = None  # waiting for partner

    def enter_prefix(self, line_idx: int, raw: str) -> EditorResult | None:
        """Called when user commits a prefix entry. Returns result or None if
        the entry is being held (e.g. first half of a block command)."""
        raw = raw.strip().upper()
        if not raw:
            self._pending.pop(line_idx, None)
            return None

        self._pending[line_idx] = raw
        cmd_name, numeric_arg = self.registry.normalize(raw)
        spec = self.registry.get_line_cmd(cmd_name)

        if spec is None:
            self._pending.pop(line_idx, None)
            return EditorResult(success=False, message=f"Unknown prefix command: {raw}")

        entry = PrefixEntry(
            line_idx=line_idx,
            raw_input=raw,
            cmd_name=cmd_name,
            numeric_arg=numeric_arg,
            is_block=spec.is_block,
        )

        if spec.is_block:
            return self._handle_block(entry)

        # Single-line command — execute immediately
        self._pending.pop(line_idx, None)
        result = spec.handler(self.buffer, line_idx, numeric_arg)
        result.cleared_prefixes.append(line_idx)
        return result

    def _handle_block(self, entry: PrefixEntry) -> EditorResult | None:
        if self._open_block is None:
            # First marker
            self._open_block = entry
            return None  # Waiting for partner

        open = self._open_block

        if open.cmd_name != entry.cmd_name:
            # Mismatched block commands
            self._open_block = None
            self._pending.pop(open.line_idx, None)
            self._pending.pop(entry.line_idx, None)
            return EditorResult(
                success=False,
                message=f"Mismatched block commands: {open.cmd_name} and {entry.cmd_name}",
                cleared_prefixes=[open.line_idx, entry.line_idx],
            )

        start_idx = min(open.line_idx, entry.line_idx)
        end_idx = max(open.line_idx, entry.line_idx)
        self._open_block = None
        self._pending.pop(open.line_idx, None)
        self._pending.pop(entry.line_idx, None)

        spec = self.registry.get_line_cmd(entry.cmd_name)
        result = spec.handler(self.buffer, start_idx, end_idx, open.numeric_arg)
        result.cleared_prefixes.extend([open.line_idx, entry.line_idx])
        return result

    def cancel_open_block(self) -> None:
        if self._open_block:
            self._pending.pop(self._open_block.line_idx, None)
            self._open_block = None

    def get_display_content(self, line_idx: int, line_number: int) -> str:
        """Return the 6-char string to render in the prefix column for this line."""
        if line_idx in self._pending:
            return self._pending[line_idx].ljust(6)[:6]
        if self._open_block and self._open_block.line_idx == line_idx:
            return self._open_block.cmd_name.ljust(6)[:6]
        line = self.buffer.lines[line_idx]
        if line.label:
            return f".{line.label:<5}"[:6]
        return f"{line_number:>6}"
