import pytest
from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry
from notispf.commands import line_cmds


@pytest.fixture
def registry():
    r = CommandRegistry()
    line_cmds.register(r)
    return r


@pytest.fixture
def buf(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("alpha\nbeta\ngamma\ndelta\nepsilon\n")
    return Buffer(str(f))


def cmd(registry, name, buf, idx, count=1):
    spec = registry.get_line_cmd(name)
    return spec.handler(buf, idx, count)


# --- D (delete) ---

def test_delete_single(registry, buf):
    result = cmd(registry, "D", buf, 1)
    assert result.success
    assert len(buf) == 4
    assert buf.lines[1].text == "gamma"


def test_delete_multiple(registry, buf):
    result = cmd(registry, "D", buf, 0, count=3)
    assert result.success
    assert len(buf) == 2
    assert buf.lines[0].text == "delta"


def test_delete_clamps_to_end(registry, buf):
    result = cmd(registry, "D", buf, 3, count=99)
    assert result.success
    assert len(buf) == 3


def test_delete_invalid_idx(registry, buf):
    result = cmd(registry, "D", buf, 99)
    assert not result.success


# --- I (insert) ---

def test_insert_single(registry, buf):
    result = cmd(registry, "I", buf, 1)
    assert result.success
    assert len(buf) == 6
    assert buf.lines[2].text == ""
    assert buf.lines[1].text == "beta"


def test_insert_multiple(registry, buf):
    cmd(registry, "I", buf, 0, count=3)
    assert len(buf) == 8
    assert buf.lines[1].text == ""
    assert buf.lines[2].text == ""
    assert buf.lines[3].text == ""


# --- R (repeat) ---

def test_repeat_once(registry, buf):
    result = cmd(registry, "R", buf, 0, count=1)
    assert result.success
    assert len(buf) == 6
    assert buf.lines[0].text == "alpha"
    assert buf.lines[1].text == "alpha"


def test_repeat_multiple(registry, buf):
    cmd(registry, "R", buf, 2, count=3)
    assert len(buf) == 8
    assert buf.lines[2].text == "gamma"
    assert buf.lines[3].text == "gamma"
    assert buf.lines[4].text == "gamma"
    assert buf.lines[5].text == "gamma"


# --- C (copy) and A/B (paste) ---

def test_copy_then_paste_after(registry, buf):
    cmd(registry, "C", buf, 0)
    result = cmd(registry, "A", buf, 2)
    assert result.success
    assert len(buf) == 6
    assert buf.lines[3].text == "alpha"


def test_copy_then_paste_before(registry, buf):
    cmd(registry, "C", buf, 4)
    result = cmd(registry, "B", buf, 2)
    assert result.success
    assert len(buf) == 6
    assert buf.lines[2].text == "epsilon"


def test_copy_multiple_lines(registry, buf):
    # Copy 2 lines, paste after line 4
    spec = registry.get_line_cmd("C")
    spec.handler(buf, 0, 2)
    spec = registry.get_line_cmd("A")
    spec.handler(buf, 4, 1)
    assert len(buf) == 7
    assert buf.lines[5].text == "alpha"
    assert buf.lines[6].text == "beta"


def test_paste_without_clipboard(registry, buf):
    result = cmd(registry, "A", buf, 0)
    assert not result.success
    assert "clipboard" in result.message.lower()


# --- M (move) ---

def test_move_then_paste(registry, buf):
    cmd(registry, "M", buf, 0)
    assert len(buf) == 4          # line deleted immediately
    assert buf.lines[0].text == "beta"
    cmd(registry, "A", buf, 3)   # paste after last line
    assert len(buf) == 5
    assert buf.lines[4].text == "alpha"


# --- registry normalize ---

def test_normalize_plain(registry):
    assert registry.normalize("D") == ("D", 1)


def test_normalize_with_count(registry):
    assert registry.normalize("D3") == ("D", 3)


def test_normalize_block(registry):
    assert registry.normalize("DD") == ("DD", 1)
    assert registry.normalize("CC") == ("CC", 1)


def test_normalize_case_insensitive(registry):
    assert registry.normalize("d3") == ("D", 3)
