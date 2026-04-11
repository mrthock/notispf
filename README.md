# notispf

A terminal text editor for Linux and macOS inspired by the ISPF editor from z/OS mainframes.
Runs in your terminal like vim or nano, with the prefix command area that ISPF users know and love.

## Installation

### Download a binary (no Python required)

Go to the [Releases page](https://github.com/mrthock/notispf/releases) and download the binary for your platform:

| Platform | File |
|----------|------|
| Linux    | `notispf-linux` |
| macOS    | `notispf-macos` |
| Windows  | `notispf-windows.exe` |

**Linux / macOS:**
```bash
chmod +x notispf-linux   # or notispf-macos
./notispf-linux myfile.txt
```

Optionally move it somewhere on your PATH:
```bash
mv notispf-linux ~/.local/bin/notispf
```

**macOS note:** macOS will warn that the binary is from an unidentified developer. To clear the warning:
```bash
xattr -d com.apple.quarantine ./notispf-macos
```
Then run it normally.

### Via pip

```bash
pip install notispf
```

### From source

```bash
git clone https://github.com/mrthock/notispf
cd notispf
pip install -e .
```

## Usage

```bash
notispf <file>
```

## Screen Layout

```
 notispf  filename.txt                              Line 1/42
000001|This is the first line of your file
000002|Second line here
000003|Third line
      |~
      |~
Type prefix command, Enter to execute, Esc to cancel
```

- **Status bar** (top) — filename, modified flag `[+]`, current line/total
- **Prefix column** (left, 6 chars) — shows line numbers; type commands here
- **Text area** (right of `|`) — edit your file
- **Message/command line** (bottom) — status messages and command input

## Navigation

| Key | Action |
|-----|--------|
| Arrow keys | Move cursor |
| Page Up / Page Down | Scroll |
| Home / Ctrl+A | Beginning of line |
| End / Ctrl+E | End of line |

## Switching Between Text and Prefix Area

| Key | Action |
|-----|--------|
| Tab | text(N) → prefix(N+1) |
| Tab | prefix(N) → text(N) |
| Shift+Tab | text(N) → prefix(N) |
| Shift+Tab | prefix(N) → text(N-1) |

## Prefix Commands

Type a command into the prefix column, then press **Enter** to execute.
You can stage commands on multiple lines before pressing Enter — they all execute at once.

### Single-Line Commands

| Command | Action |
|---------|--------|
| `D` | Delete line |
| `Dn` | Delete n lines (e.g. `D5` deletes 5) |
| `I` | Insert blank line after |
| `In` | Insert n blank lines |
| `R` | Repeat line |
| `Rn` | Repeat line n times |
| `C` | Copy line to clipboard |
| `Cn` | Copy n lines to clipboard |
| `M` | Move line (cut to clipboard) |
| `Mn` | Move n lines |
| `A` | Paste clipboard **after** this line |
| `B` | Paste clipboard **before** this line |
| `>n` | Indent right n columns (e.g. `>4` adds 4 spaces) |
| `<n` | Indent left n columns (removes up to n leading spaces) |
| `HEX` | Replace this line with its hex representation |
| `HEXB` | Insert a hex copy of this line below it |

### Block Commands

Type the command on the **first** line of the block, then again on the **last** line.

| Command | Action |
|---------|--------|
| `DD` | Delete block |
| `CC` | Copy block to clipboard |
| `MM` | Move block (cut to clipboard) |
| `RR` | Repeat block (insert a copy below) |
| `>>n` | Indent block right n columns |
| `<<n` | Indent block left n columns |

Use `A` or `B` on a third line to place the clipboard after copying or moving.

**Example — move lines 3–6 to after line 10:**
1. Tab to line 3 prefix → type `MM`
2. Arrow down to line 6 → type `MM`
3. Arrow down to line 10 → type `A`
4. Press Enter

### Prefix Mode Controls

| Key | Action |
|-----|--------|
| Enter | Execute all staged prefix commands |
| Escape | Cancel all staged commands and exit prefix mode |
| ↑ / ↓ | Move between lines (keeps staged commands) |

## Command Line

Press **F6** to open the command line, then type a command and press Enter.

### File Commands

| Command | Action |
|---------|--------|
| `SAVE` | Save file |
| `FILE` | Save and exit |
| `CANCEL` or `QUIT` or `CAN` | Exit without saving |

### Undo / Redo

| Command | Action |
|---------|--------|
| `UNDO` | Undo last change |
| `REDO` | Redo last undone change |

### Hex Mode

| Command | Action |
|---------|--------|
| `HEX ON` | Convert entire file to hex (e.g. `Hello` → `48 65 6C 6C 6F`) |
| `HEX OFF` | Convert hex back to text |

`[HEX]` appears in the status bar while hex mode is active. `HEX ON` and `HEX OFF` each count as a single undo step.

### Find and Change

```
FIND "text"
CHANGE "old" "new"
CHANGE "old" "new" ALL
CHANGE "old" "new" ALL .labelA .labelB
```

Aliases: `F` for `FIND`, `C` for `CHANGE`.

- `FIND` — locate next occurrence (case-insensitive by default)
- `CHANGE` — replace next occurrence
- `CHANGE ... ALL` — replace all occurrences in file
- `CHANGE ... ALL .A .B` — replace all occurrences between labeled lines

### Labels

Type `.A`, `.B` etc. in the prefix column to assign a label to a line.
Labels are used to define ranges for `CHANGE ... ALL .A .B`.

## Function Keys

| Key | Action |
|-----|--------|
| F1 | Help |
| F3 | Save and exit |
| F5 | Repeat last FIND (RFIND) |
| F6 | Open command line |
| F12 | Exit without saving |
| Ctrl+Z | Undo last change |
| Ctrl+Y | Redo last undone change |

## Contributing

notispf is designed to be easy to extend. Adding a new prefix command takes three steps:

1. Write a handler function in `notispf/commands/line_cmds.py`:

```python
def cmd_trim(buffer: Buffer, line_idx: int, count: int) -> EditorResult:
    for i in range(line_idx, min(line_idx + count, len(buffer))):
        buffer.replace_line(i, buffer.lines[i].text.rstrip())
    return EditorResult(success=True)
```

2. Register it in the same file's `register()` function:

```python
registry.register_line_cmd(CommandSpec("T", cmd_trim, description="Trim trailing whitespace"))
```

3. Add tests in `tests/test_line_cmds.py`.

That's it — no changes to the prefix state machine, display, or app controller needed.

See [ARCHITECTURE.md](ARCHITECTURE.md) for a deeper overview of the codebase.

## License

MIT
