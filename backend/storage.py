import os
import mimetypes
from portable import GALERI_DIR


def init_storage():
    GALERI_DIR.mkdir(parents=True, exist_ok=True)
    return "local"


def put_object(path: str, data: bytes, content_type: str) -> dict:
    target = GALERI_DIR / path
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    return {"path": path, "size": len(data)}


def get_object(path: str):
    fp = GALERI_DIR / path
    if not fp.exists():
        raise FileNotFoundError(path)
    ctype = mimetypes.guess_type(str(fp))[0] or "application/octet-stream"
    return fp.read_bytes(), ctype
