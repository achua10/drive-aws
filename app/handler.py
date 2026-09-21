import os
from dataclasses import dataclass
from functools import lru_cache

import boto3
from botocore.config import Config

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