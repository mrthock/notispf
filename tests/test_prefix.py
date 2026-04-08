import pytest
from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry
from notispf.commands import line_cmds, block_cmds
from notispf.prefix import PrefixArea


@pytest.fixture
def registry():
    r = CommandRegistry()
    line_cmds.register(r)
    block_cmds.register(r)
    return r


@pytest.fixture
def buf(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("alpha\nbeta\ngamma\ndelta\nepsilon\n")
    return Buffer(str(f))


@pytest.fixture
def prefix(buf, registry):
    return PrefixArea(buf, registry)


# --- Single-line commands via prefix area ---

def test_delete_via_prefix(prefix, buf):
    result = prefix.enter_prefix(1, "D")
    assert result.success
    assert len(buf) == 4
    assert buf.lines[1].text == "gamma"


def test_delete_with_count_via_prefix(prefix, buf):
    result = prefix.enter_prefix(0, "D3")
    assert result.success
    assert len(buf) == 2
    assert buf.lines[0].text == "delta"


def test_insert_via_prefix(prefix, buf):
    result = prefix.enter_prefix(2, "I2")
    assert result.success
    assert len(buf) == 7


def test_unknown_command(prefix, buf):
    result = prefix.enter_prefix(0, "Z")
    assert not result.success
    assert "unknown" in result.message.lower()


def test_empty_prefix_returns_none(prefix, buf):
    result = prefix.enter_prefix(0, "")
    assert result is None


# --- Block commands state machine ---

def test_block_delete(prefix, buf):
    # First DD — should return None (waiting for partner)
    result = prefix.enter_prefix(1, "DD")
    assert result is None

    # Second DD — should execute
    result = prefix.enter_prefix(3, "DD")
    assert result is not None
    assert result.success
    assert len(buf) == 2
    assert buf.lines[0].text == "alpha"
    assert buf.lines[1].text == "epsilon"


def test_block_delete_order_independent(prefix, buf):
    """DD on higher line first, then lower line — should still delete correct range."""
    prefix.enter_prefix(3, "DD")
    result = prefix.enter_prefix(1, "DD")
    assert result.success
    assert len(buf) == 2


def test_block_copy_paste(prefix, buf):
    prefix.enter_prefix(0, "CC")
    prefix.enter_prefix(1, "CC")
    # Paste after line 4
    result = prefix.enter_prefix(4, "A")
    assert result.success
    assert len(buf) == 7
    assert buf.lines[5].text == "alpha"
    assert buf.lines[6].text == "beta"


def test_block_repeat(prefix, buf):
    prefix.enter_prefix(0, "RR")
    result = prefix.enter_prefix(1, "RR")
    assert result.success
    assert len(buf) == 7
    assert buf.lines[0].text == "alpha"
    assert buf.lines[1].text == "beta"
    assert buf.lines[2].text == "alpha"
    assert buf.lines[3].text == "beta"


def test_mismatched_block_commands(prefix, buf):
    prefix.enter_prefix(0, "DD")
    result = prefix.enter_prefix(2, "CC")
    assert not result.success
    assert "mismatch" in result.message.lower()
    assert len(buf) == 5  # nothing deleted


def test_single_cmd_while_block_open(prefix, buf):
    """A single-line command should execute immediately even while a block is open."""
    prefix.enter_prefix(4, "DD")   # open block on line 4
    result = prefix.enter_prefix(0, "D")  # delete line 0 immediately
    assert result.success
    assert len(buf) == 4
    assert buf.lines[0].text == "beta"
    # Block is still open on line 4 (now line 3)
    assert prefix._open_block is not None


def test_cancel_open_block(prefix, buf):
    prefix.enter_prefix(2, "DD")
    assert prefix._open_block is not None
    prefix.cancel_open_block()
    assert prefix._open_block is None


# --- Display content ---

def test_display_shows_line_number(prefix, buf):
    content = prefix.get_display_content(0, 1)
    assert content.strip() == "1"


def test_display_shows_pending_input(prefix, buf):
    prefix._pending[2] = "D3"
    content = prefix.get_display_content(2, 3)
    assert "D3" in content


def test_display_shows_open_block_marker(prefix, buf):
    prefix.enter_prefix(2, "DD")
    content = prefix.get_display_content(2, 3)
    assert "DD" in content


def test_display_shows_label(prefix, buf):
    buf.set_label(1, ".A")
    content = prefix.get_display_content(1, 2)
    assert ".A" in content
