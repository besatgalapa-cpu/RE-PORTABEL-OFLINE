import mimetypes
from portable import GALERI_DIR


def init_storage():
    GALERI_DIR.mkdir(parents=True, exist_ok=True)
    return "local"


def put_object(path: str, data: bytes, content_type: str) -> dict:
    fp = GALERI_DIR / path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_bytes(data)
    return {"path": path, "size": len(data)}


def get_object(path: str):
    fp = GALERI_DIR / path
    if not fp.exists():
        raise FileNotFoundError(path)
    ctype = mimetypes.guess_type(str(fp))[0] or "application/octet-stream"
    return fp.read_bytes(), ctype
