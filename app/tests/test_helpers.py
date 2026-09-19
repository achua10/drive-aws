from helpers import clean_file_name


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