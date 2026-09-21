import os
import uuid
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

import boto3
from botocore.config import Config

from helpers import (
    FILE_ID_PATTERN,
    BadRequestError,
    build_content_disposition,
    build_s3_key,
    clean_file_name,
    make_response,
    read_json_body,
    validate_upload_request,
)
DEFAULT_URL_EXPIRY_SECONDS = 300
DEFAULT_MAX_FILE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class AppConfig:
    bucket_name: str
    table_name: str
    url_expiry_seconds: int
    max_file_bytes: int


def _required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _positive_int_env(name, default):
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be a whole number, got {raw!r}")
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


def get_config():
    """Read settings from environment variables (set by Terraform on Lambda)."""
    return AppConfig(
        bucket_name=_required_env("BUCKET_NAME"),
        table_name=_required_env("TABLE_NAME"),
        url_expiry_seconds=_positive_int_env("URL_EXPIRY_SECONDS", DEFAULT_URL_EXPIRY_SECONDS),
        max_file_bytes=_positive_int_env("MAX_FILE_BYTES", DEFAULT_MAX_FILE_BYTES),
    )


@lru_cache(maxsize=None)
def get_s3_client():
    """Create the S3 client once and reuse it on warm Lambda calls."""
    return boto3.client(
        "s3",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


@lru_cache(maxsize=None)
def get_table():
    """Create the DynamoDB table handle once and reuse it."""
    return boto3.resource("dynamodb").Table(get_config().table_name)

def create_upload(event):
    """POST /upload: validate, save a record, and return a temporary upload link."""
    config = get_config()

    try:
        body = read_json_body(event)
    except BadRequestError as error:
        return make_response(400, {"error": str(error)})

    problems = validate_upload_request(body, config.max_file_bytes)
    if problems:
        return make_response(400, {"error": "invalid upload request", "problems": problems})

    file_id = str(uuid.uuid4())
    s3_key = build_s3_key(file_id)
    file_name = clean_file_name(body["file_name"])

    # Signing happens locally (no network call), so do it before touching the table.
    upload_url = get_s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": config.bucket_name,
            "Key": s3_key,
            "ContentType": body["content_type"],
            "ContentLength": body["size"],
        },
        ExpiresIn=config.url_expiry_seconds,
        HttpMethod="PUT",
    )

    get_table().put_item(
        Item={
            "file_id": file_id,
            "file_name": file_name,
            "size": body["size"],
            "content_type": body["content_type"],
            "s3_key": s3_key,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    return make_response(
        201,
        {
            "file_id": file_id,
            "file_name": file_name,
            "upload_url": upload_url,
            "expires_in": config.url_expiry_seconds,
            "required_headers": {"Content-Type": body["content_type"]},
        },
    )

def list_files(event):
    """GET /files: return all file records, newest first."""
    table = get_table()

    items = []
    scan_kwargs = {}
    while True:
        result = table.scan(**scan_kwargs)
        items.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    items.sort(key=lambda item: item.get("uploaded_at", ""), reverse=True)

    files = [
        {
            "file_id": item["file_id"],
            "file_name": item.get("file_name"),
            "size": item.get("size"),
            "content_type": item.get("content_type"),
            "uploaded_at": item.get("uploaded_at"),
        }
        for item in items
    ]
    return make_response(200, {"files": files, "count": len(files)})

def parse_file_id(event):
    """Read and validate the {id} from the URL path."""
    params = event.get("pathParameters") or {}
    file_id = params.get("id")
    if not isinstance(file_id, str) or not FILE_ID_PATTERN.fullmatch(file_id):
        raise BadRequestError("invalid file id")
    return file_id


def download_file(event):
    """GET /files/{id}/download: return a temporary download link."""
    config = get_config()

    try:
        file_id = parse_file_id(event)
    except BadRequestError as error:
        return make_response(400, {"error": str(error)})

    record = get_table().get_item(Key={"file_id": file_id}).get("Item")
    if record is None:
        return make_response(404, {"error": "file not found"})

    file_name = clean_file_name(record.get("file_name"))
    download_url = get_s3_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": config.bucket_name,
            "Key": build_s3_key(file_id),
            "ResponseContentDisposition": build_content_disposition(file_name),
        },
        ExpiresIn=config.url_expiry_seconds,
        HttpMethod="GET",
    )

    return make_response(
        200,
        {
            "file_id": file_id,
            "file_name": file_name,
            "download_url": download_url,
            "expires_in": config.url_expiry_seconds,
        },
    )

def delete_file(event):
    """DELETE /files/{id}: remove the S3 object first, then the record."""
    config = get_config()

    try:
        file_id = parse_file_id(event)
    except BadRequestError as error:
        return make_response(400, {"error": str(error)})

    table = get_table()
    record = table.get_item(Key={"file_id": file_id}).get("Item")
    if record is None:
        return make_response(404, {"error": "file not found"})

    get_s3_client().delete_object(Bucket=config.bucket_name, Key=build_s3_key(file_id))
    table.delete_item(Key={"file_id": file_id})

    return make_response(200, {"file_id": file_id, "deleted": True})

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ROUTES = {
    "POST /upload": create_upload,
    "GET /files": list_files,
    "GET /files/{id}/download": download_file,
    "DELETE /files/{id}": delete_file,
}


def lambda_handler(event, context):
    """Entry point: pick the action for this route, and never leak error details."""
    route_key = event.get("routeKey") if isinstance(event, dict) else None
    action = ROUTES.get(route_key) if isinstance(route_key, str) else None

    if action is None:
        return make_response(404, {"error": "route not found"})

    try:
        return action(event)
    except Exception:
        # Full details go to CloudWatch; the caller only sees a generic message.
        logger.exception("Unhandled error on route %s", route_key)
        return make_response(500, {"error": "internal server error"})