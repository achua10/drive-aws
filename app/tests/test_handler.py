import json
from decimal import Decimal

import pytest

import handler
from handler import get_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("BUCKET_NAME", "TABLE_NAME", "URL_EXPIRY_SECONDS", "MAX_FILE_BYTES"):
        monkeypatch.delenv(name, raising=False)


def set_required(monkeypatch):
    monkeypatch.setenv("BUCKET_NAME", "my-bucket")
    monkeypatch.setenv("TABLE_NAME", "my-table")


# ---------- config tests ----------

def test_defaults_are_used(monkeypatch):
    set_required(monkeypatch)
    config = get_config()
    assert config.bucket_name == "my-bucket"
    assert config.table_name == "my-table"
    assert config.url_expiry_seconds == 300
    assert config.max_file_bytes == 5 * 1024 * 1024


def test_overrides_are_used(monkeypatch):
    set_required(monkeypatch)
    monkeypatch.setenv("URL_EXPIRY_SECONDS", "60")
    monkeypatch.setenv("MAX_FILE_BYTES", "1000")
    config = get_config()
    assert config.url_expiry_seconds == 60
    assert config.max_file_bytes == 1000


def test_missing_bucket_raises(monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "my-table")
    with pytest.raises(RuntimeError, match="BUCKET_NAME"):
        get_config()


def test_missing_table_raises(monkeypatch):
    monkeypatch.setenv("BUCKET_NAME", "my-bucket")
    with pytest.raises(RuntimeError, match="TABLE_NAME"):
        get_config()


@pytest.mark.parametrize("bad", ["abc", "1.5", "0", "-3"])
def test_bad_number_raises(monkeypatch, bad):
    set_required(monkeypatch)
    monkeypatch.setenv("URL_EXPIRY_SECONDS", bad)
    with pytest.raises(RuntimeError, match="URL_EXPIRY_SECONDS"):
        get_config()


# ---------- upload action tests ----------

class FakeS3:
    def __init__(self):
        self.calls = []

    def generate_presigned_url(self, operation, Params, ExpiresIn, HttpMethod):
        self.calls.append(
            {"operation": operation, "params": Params, "expires": ExpiresIn, "method": HttpMethod}
        )
        return "https://example.test/upload"


class FakeTable:
    def __init__(self):
        self.items = []

    def put_item(self, Item):
        self.items.append(Item)


@pytest.fixture
def aws(monkeypatch):
    set_required(monkeypatch)
    s3, table = FakeS3(), FakeTable()
    monkeypatch.setattr(handler, "get_s3_client", lambda: s3)
    monkeypatch.setattr(handler, "get_table", lambda: table)
    return s3, table


VALID_UPLOAD = {"file_name": "report.pdf", "size": 1024, "content_type": "application/pdf"}


def upload_event(body):
    return {"body": json.dumps(body)}


def test_upload_returns_201_with_link(aws):
    response = handler.create_upload(upload_event(VALID_UPLOAD))
    body = json.loads(response["body"])
    assert response["statusCode"] == 201
    assert body["upload_url"] == "https://example.test/upload"
    assert body["file_name"] == "report.pdf"
    assert body["expires_in"] == 300
    assert body["required_headers"] == {"Content-Type": "application/pdf"}


def test_upload_saves_one_record(aws):
    _, table = aws
    response = handler.create_upload(upload_event(VALID_UPLOAD))
    file_id = json.loads(response["body"])["file_id"]
    assert len(table.items) == 1
    item = table.items[0]
    assert item["file_id"] == file_id
    assert item["s3_key"] == f"uploads/{file_id}"
    assert item["size"] == 1024
    assert item["content_type"] == "application/pdf"
    assert "uploaded_at" in item


def test_upload_link_is_tied_to_key_type_and_size(aws):
    s3, _ = aws
    response = handler.create_upload(upload_event(VALID_UPLOAD))
    file_id = json.loads(response["body"])["file_id"]
    call = s3.calls[0]
    assert call["operation"] == "put_object"
    assert call["method"] == "PUT"
    assert call["expires"] == 300
    assert call["params"] == {
        "Bucket": "my-bucket",
        "Key": f"uploads/{file_id}",
        "ContentType": "application/pdf",
        "ContentLength": 1024,
    }


def test_upload_cleans_file_name(aws):
    _, table = aws
    handler.create_upload(upload_event({**VALID_UPLOAD, "file_name": "../../x.txt"}))
    assert table.items[0]["file_name"] == "x.txt"


def test_invalid_request_returns_400_and_saves_nothing(aws):
    s3, table = aws
    response = handler.create_upload(upload_event({}))
    body = json.loads(response["body"])
    assert response["statusCode"] == 400
    assert len(body["problems"]) == 3
    assert table.items == []
    assert s3.calls == []


def test_oversized_file_returns_400(aws):
    response = handler.create_upload(upload_event({**VALID_UPLOAD, "size": 5 * 1024 * 1024 + 1}))
    assert response["statusCode"] == 400


def test_invalid_json_returns_400(aws):
    response = handler.create_upload({"body": "{nope"})
    assert response["statusCode"] == 400

# ---------- list action tests ----------

class FakeScanTable:
    def __init__(self, pages):
        self.pages = list(pages)
        self.scan_calls = []

    def scan(self, **kwargs):
        self.scan_calls.append(kwargs)
        return self.pages.pop(0)


def make_item(file_id, uploaded_at):
    return {
        "file_id": file_id,
        "file_name": f"{file_id}.txt",
        "size": Decimal("10"),
        "content_type": "text/plain",
        "s3_key": f"uploads/{file_id}",
        "uploaded_at": uploaded_at,
    }


def use_table(monkeypatch, pages):
    table = FakeScanTable(pages)
    monkeypatch.setattr(handler, "get_table", lambda: table)
    return table


def test_list_returns_newest_first(monkeypatch):
    use_table(monkeypatch, [{"Items": [
        make_item("old", "2026-01-01T00:00:00+00:00"),
        make_item("new", "2026-02-01T00:00:00+00:00"),
    ]}])
    response = handler.list_files({})
    body = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert [f["file_id"] for f in body["files"]] == ["new", "old"]
    assert body["count"] == 2


def test_list_hides_s3_key_and_converts_size(monkeypatch):
    use_table(monkeypatch, [{"Items": [make_item("a", "2026-01-01T00:00:00+00:00")]}])
    file = json.loads(handler.list_files({})["body"])["files"][0]
    assert "s3_key" not in file
    assert file["size"] == 10
    assert isinstance(file["size"], int)


def test_list_empty_table(monkeypatch):
    use_table(monkeypatch, [{"Items": []}])
    body = json.loads(handler.list_files({})["body"])
    assert body == {"files": [], "count": 0}


def test_list_follows_pagination(monkeypatch):
    table = use_table(monkeypatch, [
        {"Items": [make_item("a", "2026-01-01T00:00:00+00:00")], "LastEvaluatedKey": {"file_id": "a"}},
        {"Items": [make_item("b", "2026-01-02T00:00:00+00:00")]},
    ])
    body = json.loads(handler.list_files({})["body"])
    assert body["count"] == 2
    assert len(table.scan_calls) == 2
    assert table.scan_calls[1] == {"ExclusiveStartKey": {"file_id": "a"}}

# ---------- download action tests ----------

FILE_ID = "123e4567-e89b-12d3-a456-426614174000"


class FakeS3Download(FakeS3):
    def generate_presigned_url(self, operation, Params, ExpiresIn, HttpMethod):
        super().generate_presigned_url(operation, Params, ExpiresIn, HttpMethod)
        return "https://example.test/download"


class FakeLookupTable:
    def __init__(self, items=None):
        self.items = {item["file_id"]: item for item in (items or [])}
        self.get_calls = []

    def get_item(self, Key):
        self.get_calls.append(Key)
        item = self.items.get(Key["file_id"])
        return {"Item": item} if item else {}


def use_download(monkeypatch, items):
    set_required(monkeypatch)
    s3, table = FakeS3Download(), FakeLookupTable(items)
    monkeypatch.setattr(handler, "get_s3_client", lambda: s3)
    monkeypatch.setattr(handler, "get_table", lambda: table)
    return s3, table


def download_event(file_id=FILE_ID):
    return {"pathParameters": {"id": file_id}}


def test_download_returns_200_with_link(monkeypatch):
    use_download(monkeypatch, [make_item(FILE_ID, "2026-01-01T00:00:00+00:00")])
    response = handler.download_file(download_event())
    body = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert body["download_url"] == "https://example.test/download"
    assert body["file_id"] == FILE_ID
    assert body["expires_in"] == 300


def test_download_link_is_tied_to_key_and_name(monkeypatch):
    s3, _ = use_download(monkeypatch, [make_item(FILE_ID, "2026-01-01T00:00:00+00:00")])
    handler.download_file(download_event())
    call = s3.calls[0]
    assert call["operation"] == "get_object"
    assert call["method"] == "GET"
    assert call["expires"] == 300
    assert call["params"]["Bucket"] == "my-bucket"
    assert call["params"]["Key"] == f"uploads/{FILE_ID}"
    assert "attachment" in call["params"]["ResponseContentDisposition"]


def test_download_missing_file_returns_404(monkeypatch):
    s3, _ = use_download(monkeypatch, [])
    response = handler.download_file(download_event())
    assert response["statusCode"] == 404
    assert s3.calls == []


@pytest.mark.parametrize("bad_event", [
    {},
    {"pathParameters": None},
    {"pathParameters": {"id": ""}},
    {"pathParameters": {"id": "../x"}},
    {"pathParameters": {"id": "a/b"}},
])
def test_download_bad_id_returns_400(monkeypatch, bad_event):
    s3, table = use_download(monkeypatch, [])
    response = handler.download_file(bad_event)
    assert response["statusCode"] == 400
    assert table.get_calls == []
    assert s3.calls == []

# ---------- delete action tests ----------

class FakeDeleteS3:
    def __init__(self, events):
        self.events = events

    def delete_object(self, Bucket, Key):
        self.events.append(("s3_delete", Bucket, Key))


class FakeDeleteTable(FakeLookupTable):
    def __init__(self, events, items=None):
        super().__init__(items)
        self.events = events

    def delete_item(self, Key):
        self.events.append(("table_delete", Key["file_id"]))
        self.items.pop(Key["file_id"], None)


def use_delete(monkeypatch, items):
    set_required(monkeypatch)
    events = []
    table = FakeDeleteTable(events, items)
    monkeypatch.setattr(handler, "get_s3_client", lambda: FakeDeleteS3(events))
    monkeypatch.setattr(handler, "get_table", lambda: table)
    return events, table


def test_delete_removes_object_then_record(monkeypatch):
    events, table = use_delete(monkeypatch, [make_item(FILE_ID, "2026-01-01T00:00:00+00:00")])
    response = handler.delete_file(download_event())
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"file_id": FILE_ID, "deleted": True}
    assert events == [
        ("s3_delete", "my-bucket", f"uploads/{FILE_ID}"),
        ("table_delete", FILE_ID),
    ]
    assert FILE_ID not in table.items


def test_delete_missing_file_returns_404(monkeypatch):
    events, _ = use_delete(monkeypatch, [])
    response = handler.delete_file(download_event())
    assert response["statusCode"] == 404
    assert events == []


@pytest.mark.parametrize("bad_event", [
    {},
    {"pathParameters": None},
    {"pathParameters": {"id": ""}},
    {"pathParameters": {"id": "../x"}},
    {"pathParameters": {"id": "a/b"}},
])
def test_delete_bad_id_returns_400(monkeypatch, bad_event):
    events, table = use_delete(monkeypatch, [])
    response = handler.delete_file(bad_event)
    assert response["statusCode"] == 400
    assert events == []
    assert table.get_calls == []


def test_delete_keeps_record_if_s3_delete_fails(monkeypatch):
    events, table = use_delete(monkeypatch, [make_item(FILE_ID, "2026-01-01T00:00:00+00:00")])

    class BrokenS3:
        def delete_object(self, Bucket, Key):
            raise RuntimeError("s3 down")

    monkeypatch.setattr(handler, "get_s3_client", lambda: BrokenS3())
    with pytest.raises(RuntimeError):
        handler.delete_file(download_event())
    assert FILE_ID in table.items
    assert events == []