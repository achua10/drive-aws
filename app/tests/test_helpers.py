import pytest

from helpers import clean_file_name, validate_size

MAX = 5 * 1024 * 1024  # 5 MB, use the limit from your design doc

def test_normal_name_unchanged():
    assert clean_file_name("report.pdf") == "report.pdf"


def test_unix_path_keeps_last_part():
    assert clean_file_name("../../x.txt") == "x.txt"


def test_windows_path_keeps_last_part():
    assert clean_file_name(r"C:\Users\me\photo.png") == "photo.png"


def test_trailing_slash_gives_default():
    assert clean_file_name("folder/") == "file"


def test_empty_gives_default():
    assert clean_file_name("") == "file"


def test_spaces_only_gives_default():
    assert clean_file_name("   ") == "file"


def test_dots_only_gives_default():
    assert clean_file_name("..") == "file"


def test_none_gives_default():
    assert clean_file_name(None) == "file"


def test_control_characters_removed():
    assert clean_file_name("bad\nname.txt") == "badname.txt"


def test_long_name_is_capped_and_keeps_extension():
    result = clean_file_name("a" * 300 + ".txt")
    assert len(result) == 100
    assert result.endswith(".txt")

    # Test the validate_size function
def test_size_at_limit_passes():
    assert validate_size(MAX, MAX) is None


def test_size_one_byte_over_fails():
    assert validate_size(MAX + 1, MAX) is not None


def test_smallest_valid_size_passes():
    assert validate_size(1, MAX) is None


def test_zero_size_fails():
    assert validate_size(0, MAX) is not None


def test_negative_size_fails():
    assert validate_size(-5, MAX) is not None


@pytest.mark.parametrize("bad", ["abc", "100", None, 5.5, True])
def test_wrong_type_fails(bad):
    assert validate_size(bad, MAX) is not None