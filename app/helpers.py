import re
def clean_file_name(raw_name, max_length=100):
    """Return a safe file name, or "file" if nothing usable is left."""
    default = "file"

    # 1. Not text? Use the default.
    if not isinstance(raw_name, str):
        return default

    # 2. Keep only the last path part (works for both / and \)
    name = raw_name.replace("\\", "/").split("/")[-1]

    # 3. Remove control characters (newlines, tabs, etc.)
    name = "".join(ch for ch in name if ch.isprintable())

    # 4. Trim spaces
    name = name.strip()

    # 5. Nothing usable left (empty, or only dots like "." or "..")
    if not name or set(name) == {"."}:
        return default

    # 6. Cap the length, keeping a short extension if there is one
    if len(name) > max_length:
        base, dot, ext = name.rpartition(".")
        keep = max_length - len(ext) - 1
        if dot and base and len(ext) <= 10 and keep > 0:
            name = base[:keep] + "." + ext
        else:
            name = name[:max_length]

    return name

def validate_size(size, max_bytes):
    """Return an error message if size is invalid, or None if it's fine."""
    # bool is a subclass of int in Python, so reject it explicitly
    if isinstance(size, bool) or not isinstance(size, int):
        return "size must be a whole number"
    if size <= 0:
        return "size must be greater than zero"
    if size > max_bytes:
        return f"size must be at most {max_bytes} bytes"
    return None

CONTENT_TYPE_PATTERN = re.compile(r"^[\w.+-]+/[\w.+-]+$")


def validate_upload_request(body, max_bytes):
    """Return a list of problems with an upload request (empty list = valid)."""
    if not isinstance(body, dict):
        return ["request body must be a JSON object"]

    problems = []

    file_name = body.get("file_name")
    if not isinstance(file_name, str) or not file_name.strip():
        problems.append("file_name is required")

    size_problem = validate_size(body.get("size"), max_bytes)
    if size_problem:
        problems.append(size_problem)

    content_type = body.get("content_type")
    if not isinstance(content_type, str) or not CONTENT_TYPE_PATTERN.fullmatch(content_type):
        problems.append("content_type must look like type/subtype, e.g. application/pdf")

    return problems

FILE_ID_PATTERN = re.compile(r"[A-Za-z0-9-]+")


def build_s3_key(file_id):
    """Return the S3 key for a file ID, or raise ValueError if the ID is unsafe."""
    if not isinstance(file_id, str) or not FILE_ID_PATTERN.fullmatch(file_id):
        raise ValueError("file_id must contain only letters, digits and hyphens")
    return f"uploads/{file_id}"