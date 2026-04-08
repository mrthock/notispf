import pytest
from notispf.buffer import Buffer
from notispf.find_change import FindChangeEngine


@pytest.fixture
def buf(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text(
        "The quick brown fox\n"
        "jumps over the lazy dog\n"
        "The fox said hello\n"
        "HELLO WORLD\n"
        "no match here\n"
    )
    return Buffer(str(f))


@pytest.fixture
def engine(buf):
    return FindChangeEngine(buf)


# --- find_next ---

def test_find_basic(engine):
    pos = engine.find_next("fox")
    assert pos == (0, 16)


def test_find_second_occurrence(engine):
    engine.find_next("fox")
    pos = engine.find_next("fox")
    assert pos == (2, 4)


def test_find_case_insensitive(engine):
    pos = engine.find_next("hello")
    assert pos == (2, 13)


def test_find_case_sensitive(engine):
    # "Hello" (mixed case) does not appear — only "hello" and "HELLO" do
    pos = engine.find_next("Hello", case_sensitive=True)
    assert pos is None


def test_find_case_sensitive_exact(engine):
    pos = engine.find_next("HELLO", case_sensitive=True)
    assert pos == (3, 0)


def test_find_wraps_around(engine, buf):
    # Start near end, should wrap to beginning
    pos = engine.find_next("quick", from_pos=(4, 0))
    assert pos == (0, 4)


def test_find_no_match(engine):
    pos = engine.find_next("zzznomatch")
    assert pos is None


def test_find_from_pos(engine):
    pos = engine.find_next("the", from_pos=(1, 0))
    assert pos == (1, 11)


# --- change_next ---

def test_change_next(engine, buf):
    count = engine.change_next("fox", "cat")
    assert count == 1
    assert buf.lines[0].text == "The quick brown cat"


def test_change_next_advances(engine, buf):
    engine.change_next("fox", "cat")
    engine.change_next("fox", "cat")
    assert buf.lines[2].text == "The cat said hello"


def test_change_next_no_match(engine, buf):
    count = engine.change_next("zzznomatch", "x")
    assert count == 0


# --- change_all ---

def test_change_all(engine, buf):
    count = engine.change_all("fox", "cat")
    assert count == 2
    assert buf.lines[0].text == "The quick brown cat"
    assert buf.lines[2].text == "The cat said hello"


def test_change_all_case_insensitive(engine, buf):
    count = engine.change_all("hello", "hi")
    assert count == 2
    assert buf.lines[2].text == "The fox said hi"
    assert buf.lines[3].text == "hi WORLD"


def test_change_all_case_sensitive(engine, buf):
    count = engine.change_all("HELLO", "HI", case_sensitive=True)
    assert count == 1
    assert buf.lines[3].text == "HI WORLD"
    assert buf.lines[2].text == "The fox said hello"


def test_change_all_no_match(engine, buf):
    count = engine.change_all("zzznomatch", "x")
    assert count == 0


# --- change_in_range ---

def test_change_in_range(engine, buf):
    buf.set_label(0, ".A")
    buf.set_label(2, ".B")
    count = engine.change_in_range("fox", "wolf", ".A", ".B")
    assert count == 2
    assert buf.lines[0].text == "The quick brown wolf"
    assert buf.lines[2].text == "The wolf said hello"
    # line 4 outside range — unchanged
    assert "fox" not in buf.lines[3].text


def test_change_in_range_reversed_labels(engine, buf):
    """Labels given in reverse order should still work."""
    buf.set_label(0, ".A")
    buf.set_label(2, ".B")
    count = engine.change_in_range("fox", "wolf", ".B", ".A")
    assert count == 2


def test_change_in_range_missing_label(engine, buf):
    buf.set_label(0, ".A")
    with pytest.raises(ValueError, match="Label not found"):
        engine.change_in_range("fox", "wolf", ".A", ".Z")


def test_change_in_range_single_line(engine, buf):
    # Range of exactly one line — label .A and .B on adjacent lines,
    # but only line 0 contains "fox"
    buf.set_label(0, ".A")
    buf.set_label(1, ".B")
    count = engine.change_in_range("fox", "wolf", ".A", ".B")
    assert count == 1
    assert buf.lines[0].text == "The quick brown wolf"
