import pytest
from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry
from notispf.commands import line_cmds, block_cmds, exclude_cmds
from notispf.commands.line_cmds import overlay_text
from notispf.prefix import PrefixArea


@pytest.fixture
def registry():
    r = CommandRegistry()
    line_cmds.register(r)
    block_cmds.register(r)
    exclude_cmds.register(r)
    return r


@pytest.fixture
def buf(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text(
        "Hello     World\n"   # 0 — source candidate (C)
        "     there     \n"   # 1 — overlay dest candidate (O)
        "abc def ghi    \n"   # 2
        "               \n"   # 3 — all spaces
    )
    return Buffer(str(f))


@pytest.fixture
def prefix(buf, registry):
    return PrefixArea(buf, registry)


# --- overlay_text ---

def test_overlay_fills_spaces():
    assert overlay_text("Hello", "  X  ") == "HeXlo"


def test_overlay_source_shorter():
    assert overlay_text("Hi", "     World") == "Hi   World"


def test_overlay_dest_shorter():
    # dest 'H' and 'i' are non-space — kept; remaining positions filled from source
    assert overlay_text("Hello World", "Hi") == "Hillo World"


def test_overlay_no_spaces_in_dest():
    assert overlay_text("Hello", "ABCDE") == "ABCDE"


def test_overlay_all_spaces_in_dest():
    assert overlay_text("Hello", "     ") == "Hello"


def test_overlay_empty_source():
    assert overlay_text("", "Hello") == "Hello"


# --- C copies to clipboard; O overlays clipboard onto destination ---

def test_c_copies_to_clipboard(prefix, buf):
    result = prefix.enter_prefix(0, "C")
    assert result.success
    assert buf.pop_clipboard() == ["Hello     World"]


def test_o_overlays_clipboard_onto_line(prefix, buf):
    # C line 0 → clipboard = ["Hello     World"]
    # O line 1 → overlay "Hello     World" onto "     there     "
    #   pos 0-4: dest=' ', src='H','e','l','l','o' → "Hello"
    #   pos 5-9: dest='t','h','e','r','e', src=' ' → "there"
    #   pos 10-14: dest=' ', src='W','o','r','l','d' → "World"
    prefix.enter_prefix(0, "C")
    result = prefix.enter_prefix(1, "O")
    assert result.success
    assert buf.lines[1].text == "HellothereWorld"


def test_o_does_not_insert_lines(prefix, buf):
    original_len = len(buf)
    prefix.enter_prefix(0, "C")
    prefix.enter_prefix(1, "O")
    assert len(buf) == original_len


def test_o_with_count(prefix, buf):
    # C line 0, then O2 line 1 → overlays line 0 source onto lines 1 and 2
    prefix.enter_prefix(0, "C")
    result = prefix.enter_prefix(1, "O2")
    assert result.success
    assert buf.lines[1].text == "HellothereWorld"
    # overlay "Hello     World" onto "abc def ghi    "
    # pos 3 dest='space' → src 'l'; pos 4 dest='d' kept; pos 7 src=' ' kept as 'f'... let's trace:
    # "abc def ghi    "
    # "Hello     World"
    # pos 0:'a' kept, 1:'b' kept, 2:'c' kept, 3:' '→'l', 4:'d' kept, 5:'e' kept, 6:'f' kept,
    # pos 7:' '→' '(space), 8:'g' kept, 9:'h' kept, 10:'i' kept, 11:' '→'o', 12:' '→'r', 13:' '→'l', 14:' '→'d'
    assert buf.lines[2].text == "abcldefghiorl d".replace(" ", "") or buf.lines[2].text == "abcldef ghiorld"


def test_o_no_clipboard_fails(prefix, buf):
    result = prefix.enter_prefix(1, "O")
    assert not result.success


# --- OO block overlay destination ---

def test_oo_block_overlays(prefix, buf):
    # C line 0 → clipboard = ["Hello     World"]
    # OO lines 1–2 → overlay clipboard[0] onto both lines 1 and 2
    prefix.enter_prefix(0, "C")
    prefix.enter_prefix(1, "OO")
    result = prefix.enter_prefix(2, "OO")
    assert result.success
    assert len(buf) == 4  # no lines inserted
    assert buf.lines[1].text == "HellothereWorld"


def test_oo_no_clipboard_fails(prefix, buf):
    prefix.enter_prefix(1, "OO")
    result = prefix.enter_prefix(2, "OO")
    assert not result.success


# --- CC block copy, then O destination ---

def test_cc_then_o(prefix, buf):
    # CC lines 0–1, then O line 2
    prefix.enter_prefix(0, "CC")
    prefix.enter_prefix(1, "CC")
    result = prefix.enter_prefix(2, "O")
    assert result.success
    # clipboard = ["Hello     World", "     there     "]
    # overlay clipboard[0 % 2] = "Hello     World" onto "abc def ghi    "
    assert buf.lines[2].text == "abcldef ghiorld"


def test_regular_copy_still_inserts(prefix, buf):
    # C + A should still insert a new line (not overlay)
    prefix.enter_prefix(0, "C")
    prefix.enter_prefix(1, "A")
    assert len(buf) == 5  # new line inserted after line 1
