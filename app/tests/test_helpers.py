import uuid

import pytest

from helpers import (
    build_s3_key,
    clean_file_name,
    validate_size,
    validate_upload_request,
)


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

VALID = {"file_name": "report.pdf", "size": 1024, "content_type": "application/pdf"}


def test_valid_request_has_no_problems():
    assert validate_upload_request(VALID, MAX) == []


def test_empty_body_lists_all_problems():
    assert len(validate_upload_request({}, MAX)) == 3


@pytest.mark.parametrize("bad_body", [None, [], "text", 5])
def test_body_that_is_not_a_dict_gives_one_problem(bad_body):
    assert len(validate_upload_request(bad_body, MAX)) == 1


def test_zero_size_gives_exactly_one_problem():
    assert len(validate_upload_request({**VALID, "size": 0}, MAX)) == 1


def test_blank_file_name_is_reported():
    problems = validate_upload_request({**VALID, "file_name": "   "}, MAX)
    assert any("file_name" in p for p in problems)


@pytest.mark.parametrize("bad_type", ["pdf", "application/", "/pdf", "a b/c", 5, "", "application/pdf\n"])
def test_bad_content_type_is_reported(bad_type):
    problems = validate_upload_request({**VALID, "content_type": bad_type}, MAX)
    assert any("content_type" in p for p in problems)

def test_key_follows_pattern():
    assert build_s3_key("abc-123") == "uploads/abc-123"


def test_real_uuid_works():
    file_id = str(uuid.uuid4())
    assert build_s3_key(file_id) == f"uploads/{file_id}"


@pytest.mark.parametrize("bad", ["", "a/b", "../x", "a\\b", "abc\n", "a b", None, 5])
def test_unsafe_ids_raise(bad):
    with pytest.raises(ValueError):
        build_s3_key(bad)