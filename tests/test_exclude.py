import pytest
from notispf.buffer import Buffer
from notispf.commands.registry import CommandRegistry
from notispf.commands import line_cmds, block_cmds, exclude_cmds
from notispf.prefix import PrefixArea
from notispf.display import Display


@pytest.fixture
def buf(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("alpha\nbeta\ngamma\ndelta\nepsilon\nzeta\n")
    return Buffer(str(f))


@pytest.fixture
def registry():
    r = CommandRegistry()
    line_cmds.register(r)
    block_cmds.register(r)
    exclude_cmds.register(r)
    return r


@pytest.fixture
def prefix(buf, registry):
    return PrefixArea(buf, registry)


# --- Buffer exclude/show ---

def test_exclude_single(buf):
    buf.exclude_lines(1)
    assert buf.lines[1].excluded is True
    assert buf.lines[0].excluded is False
    assert buf.lines[2].excluded is False


def test_exclude_multiple(buf):
    buf.exclude_lines(1, 3)
    assert all(buf.lines[i].excluded for i in range(1, 4))
    assert buf.lines[0].excluded is False
    assert buf.lines[4].excluded is False


def test_show_single(buf):
    buf.exclude_lines(1, 3)
    buf.show_lines(2, count=1)
    assert buf.lines[2].excluded is False
    assert buf.lines[1].excluded is True
    assert buf.lines[3].excluded is True


def test_show_full_fold(buf):
    buf.exclude_lines(1, 3)
    buf.show_lines(2, count=None)   # un-exclude whole run
    assert not any(buf.lines[i].excluded for i in range(1, 4))


def test_show_all(buf):
    buf.exclude_lines(0, 6)
    buf.show_all()
    assert not any(line.excluded for line in buf.lines)


def test_next_visible_forward(buf):
    buf.exclude_lines(1, 3)
    assert buf.next_visible(1, 1) == 4


def test_next_visible_backward(buf):
    buf.exclude_lines(1, 3)
    assert buf.next_visible(3, -1) == 0


def test_next_visible_not_excluded(buf):
    assert buf.next_visible(2, 1) == 2


# --- Prefix commands ---

def test_x_command(prefix, buf):
    result = prefix.enter_prefix(2, "X")
    assert result.success
    assert buf.lines[2].excluded is True


def test_x_with_count(prefix, buf):
    result = prefix.enter_prefix(1, "X3")
    assert result.success
    assert all(buf.lines[i].excluded for i in range(1, 4))


def test_s_command_shows_fold(prefix, buf):
    buf.exclude_lines(1, 3)
    result = prefix.enter_prefix(2, "S")
    assert result.success
    assert not any(buf.lines[i].excluded for i in range(1, 4))


def test_xx_block(prefix, buf):
    prefix.enter_prefix(1, "XX")
    result = prefix.enter_prefix(3, "XX")
    assert result.success
    assert all(buf.lines[i].excluded for i in range(1, 4))


def test_ss_block(prefix, buf):
    buf.exclude_lines(1, 4)
    prefix.enter_prefix(1, "SS")
    result = prefix.enter_prefix(3, "SS")
    assert result.success
    assert not any(buf.lines[i].excluded for i in range(1, 4))
    assert buf.lines[4].excluded is True  # outside range, still excluded


# --- View building ---

def test_build_view_no_excluded(buf):
    view = Display.build_view(buf, 0, 10)
    assert all(e[0] == 'line' for e in view)
    assert len(view) == 6


def test_build_view_fold(buf):
    buf.exclude_lines(1, 3)
    view = Display.build_view(buf, 0, 10)
    assert view[0] == ('line', 0)
    assert view[1][0] == 'fold'
    assert view[1][3] == 3       # count of excluded lines
    assert view[2] == ('line', 4)
    assert view[3] == ('line', 5)


def test_build_view_fold_at_start(buf):
    buf.exclude_lines(0, 2)
    view = Display.build_view(buf, 0, 10)
    assert view[0][0] == 'fold'
    assert view[0][3] == 2
    assert view[1] == ('line', 2)


def test_build_view_respects_top_line(buf):
    view = Display.build_view(buf, 2, 10)
    assert view[0] == ('line', 2)


def test_build_view_content_rows_limit(buf):
    view = Display.build_view(buf, 0, 3)
    assert len(view) == 3
