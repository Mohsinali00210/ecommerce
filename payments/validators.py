"""Upload checks shared by the shop: type is decided by the file's bytes, not its name."""

MAX_RECEIPT = 5 * 1024 * 1024
MAX_IMAGE = 3 * 1024 * 1024

SIGNATURES = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"%PDF-": "pdf",
}


def sniff(f):
    pos = f.tell() if hasattr(f, "tell") else 0
    head = f.read(16)
    f.seek(pos)
    for sig, kind in SIGNATURES.items():
        if head.startswith(sig):
            return kind
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _check(f, allowed, max_bytes, what):
    if not f:
        raise ValueError(f"Choose a {what} to upload.")
    if f.size > max_bytes:
        raise ValueError(f"The {what} must be {max_bytes // (1024 * 1024)} MB or smaller.")
    kind = sniff(f)
    if kind not in allowed:
        raise ValueError(f"Upload a {', '.join(sorted(a.upper() for a in allowed))} file.")
    ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
    if ext in ("html", "htm", "svg", "js", "xml", "xhtml", "php", "exe", "sh", "bat"):
        raise ValueError("That file type isn't allowed.")
    return kind


def validate_receipt(f):
    return _check(f, {"jpg", "png", "webp", "pdf"}, MAX_RECEIPT, "receipt")


def validate_image(f, max_bytes=MAX_IMAGE):
    return _check(f, {"jpg", "png", "webp", "gif"}, max_bytes, "image")


def validate_attachment(f, max_bytes=MAX_RECEIPT):
    return _check(f, {"jpg", "png", "webp", "gif", "pdf"}, max_bytes, "attachment")
