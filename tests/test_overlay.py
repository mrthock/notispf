import pytest
from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry
from notispf.commands import line_cmds, block_cmds, overlay_cmds
from notispf.commands.line_cmds import _overlay_text
from notispf.prefix import PrefixArea


@pytest.fixture
def registry():
    r = CommandRegistry()
    line_cmds.register(r)
    block_cmds.register(r)
    overlay_cmds.register(r)
    return r


@pytest.fixture
def buf(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text(
        "Hello     World\n"   # 0 — source candidate
        "     there     \n"   # 1 — dest candidate
        "abc def ghi    \n"   # 2
        "               \n"   # 3 — all spaces
    )
    return Buffer(str(f))


@pytest.fixture
def prefix(buf, registry):
    return PrefixArea(buf, registry)


# --- _overlay_text ---

def test_overlay_fills_spaces():
    assert _overlay_text("Hello", "  X  ") == "HeXlo"


def test_overlay_source_shorter():
    assert _overlay_text("Hi", "     World") == "Hi   World"


def test_overlay_dest_shorter():
    # 'H' and 'i' are non-space in dest — kept; remaining positions filled from source
    assert _overlay_text("Hello World", "Hi") == "Hillo World"


def test_overlay_no_spaces_in_dest():
    assert _overlay_text("Hello", "ABCDE") == "ABCDE"


def test_overlay_all_spaces_in_dest():
    assert _overlay_text("Hello", "     ") == "Hello"


def test_overlay_empty_source():
    assert _overlay_text("", "Hello") == "Hello"


# --- O prefix command ---

def test_o_sets_overlay_flag(prefix, buf):
    result = prefix.enter_prefix(0, "O")
    assert result.success
    assert buf.clipboard_is_overlay is True
    assert buf.pop_clipboard() == ["Hello     World"]


def test_o_with_count(prefix, buf):
    result = prefix.enter_prefix(0, "O2")
    assert result.success
    assert buf.pop_clipboard() == ["Hello     World", "     there     "]


def test_c_clears_overlay_flag(prefix, buf):
    prefix.enter_prefix(0, "O")
    assert buf.clipboard_is_overlay is True
    prefix.enter_prefix(0, "C")
    assert buf.clipboard_is_overlay is False


# --- OO block command ---

def test_oo_block(prefix, buf):
    prefix.enter_prefix(0, "OO")
    result = prefix.enter_prefix(1, "OO")
    assert result.success
    assert buf.clipboard_is_overlay is True
    assert buf.pop_clipboard() == ["Hello     World", "     there     "]


# --- Overlay paste via A ---

def test_overlay_paste_after(prefix, buf):
    # source: "Hello     World"  (spaces at pos 5-9)
    # dest:   "     there     "  (non-space 'there' at pos 5-9)
    # dest non-space chars win → no gap between Hello and there
    prefix.enter_prefix(0, "O")
    result = prefix.enter_prefix(0, "A")
    assert result.success
    assert buf.lines[1].text == "HellothereWorld"


def test_overlay_paste_before(prefix, buf):
    # source: "Hello     World"
    # dest:   "abc def ghi    "
    # pos 3 in dest is space → filled with 'l' from source
    # pos 7 in dest is space, source pos 7 is also space → stays space
    # trailing spaces in dest filled by source's "Worl"
    prefix.enter_prefix(0, "O")
    result = prefix.enter_prefix(2, "B")
    assert result.success
    assert buf.lines[2].text == "abcldef ghiorld"


def test_overlay_does_not_insert_lines(prefix, buf):
    original_len = len(buf)
    prefix.enter_prefix(0, "O")
    prefix.enter_prefix(1, "A")
    assert len(buf) == original_len   # no new lines added


def test_overlay_multi_line(prefix, buf):
    # OO lines 0-1: clipboard = ["Hello     World", "     there     "]
    # paste after line 1 → overlays onto lines 2 and 3
    prefix.enter_prefix(0, "OO")
    prefix.enter_prefix(1, "OO")
    result = prefix.enter_prefix(1, "A")
    assert result.success
    assert len(buf) == 4   # still 4 lines, no insertion
    assert buf.lines[2].text == "abcldef ghiorld"   # pos 10 'i' kept; 11-14 filled by 'o','r','l','d'
    assert buf.lines[3].text == "     there"   # trailing spaces stripped by rstrip()


def test_regular_copy_still_inserts(prefix, buf):
    prefix.enter_prefix(0, "C")
    prefix.enter_prefix(1, "A")
    assert len(buf) == 5   # new line inserted
