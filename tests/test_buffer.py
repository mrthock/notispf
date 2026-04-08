import pytest
from notispf.buffer import Buffer, Line


@pytest.fixture
def buf(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3\nline4\nline5\n")
    return Buffer(str(f))


def test_load(buf):
    assert len(buf) == 5
    assert buf.lines[0].text == "line1"
    assert buf.lines[4].text == "line5"


def test_insert_lines(buf):
    buf.insert_lines(1, ["new1", "new2"])
    assert len(buf) == 7
    assert buf.lines[2].text == "new1"
    assert buf.lines[3].text == "new2"


def test_insert_at_beginning(buf):
    buf.insert_lines(-1, ["first"])
    assert buf.lines[0].text == "first"
    assert len(buf) == 6


def test_delete_lines(buf):
    buf.delete_lines(1, 2)
    assert len(buf) == 3
    assert buf.lines[1].text == "line4"


def test_replace_line(buf):
    buf.replace_line(0, "replaced")
    assert buf.lines[0].text == "replaced"


def test_undo(buf):
    original = buf.lines[0].text
    buf.replace_line(0, "changed")
    assert buf.lines[0].text == "changed"
    buf.undo()
    assert buf.lines[0].text == original


def test_redo(buf):
    buf.replace_line(0, "changed")
    buf.undo()
    buf.redo()
    assert buf.lines[0].text == "changed"


def test_undo_past_beginning(buf):
    result = buf.undo()
    assert result is False


def test_clipboard(buf):
    buf.push_clipboard(["a", "b"])
    assert buf.pop_clipboard() == ["a", "b"]
    # clipboard is non-destructive
    assert buf.pop_clipboard() == ["a", "b"]


def test_labels(buf):
    buf.set_label(2, ".A")
    assert buf.get_label_index(".A") == 2
    # reassign label to different line
    buf.set_label(4, ".A")
    assert buf.get_label_index(".A") == 4
    assert buf.lines[2].label is None


def test_repeat_lines(buf):
    buf.repeat_lines(0, 1, 2)
    assert len(buf) == 7
    assert buf.lines[1].text == "line1"
    assert buf.lines[2].text == "line1"


def test_save_and_reload(buf, tmp_path):
    buf.replace_line(0, "saved")
    out = tmp_path / "out.txt"
    buf.save_file(str(out))
    buf2 = Buffer(str(out))
    assert buf2.lines[0].text == "saved"
