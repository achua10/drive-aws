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