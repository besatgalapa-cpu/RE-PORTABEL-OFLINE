import os
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from bson import json_util
from pymongo import MongoClient

ROOT_DIR = Path(__file__).resolve().parent


def resolve_dir(env_key: str, default: str) -> Path:
    p = Path(os.environ.get(env_key) or default)
    return p if p.is_absolute() else (ROOT_DIR / p).resolve()


GALERI_DIR = resolve_dir("LOCAL_STORAGE_DIR", "local_storage")
BACKUP_DIR = resolve_dir("BACKUP_DIR", "backups")
FRONTEND_BUILD_DIR = resolve_dir("FRONTEND_BUILD_DIR", "../frontend/build")
BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "5"))
PORTABLE_MODE = os.environ.get("PORTABLE_MODE", "false").strip().lower() == "true"


def _client() -> MongoClient:
    return MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)


def backup_path(name: str) -> Path:
    safe = Path(name).name
    if not safe.endswith(".zip"):
        raise FileNotFoundError(name)
    p = BACKUP_DIR / safe
    if not p.exists():
        raise FileNotFoundError(name)
    return p


def backup_info(p: Path) -> dict:
    st = p.stat()
    return {
        "name": p.name, "size": st.st_size, "kind": p.name.split("_")[0],
        "created_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
    }


def list_backups() -> list:
    if not BACKUP_DIR.exists():
        return []
    return sorted((backup_info(p) for p in BACKUP_DIR.glob("*.zip")), key=lambda b: b["name"], reverse=True)


def prune_backups(kind: str):
    files = sorted(BACKUP_DIR.glob(f"{kind}_*.zip"))
    for f in files[:-BACKUP_KEEP] if BACKUP_KEEP > 0 else []:
        f.unlink(missing_ok=True)


def create_backup(kind: str = "manual") -> dict:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"{kind}_{stamp}.zip"
    client = _client()
    db = client[os.environ["DB_NAME"]]
    payload = {"created_at": datetime.now(timezone.utc).isoformat(), "db_name": db.name, "collections": {}}
    for coll in db.list_collection_names():
        if not coll.startswith("system."):
            payload["collections"][coll] = list(db[coll].find())
    client.close()
    tmp = target.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("db.json", json_util.dumps(payload))
        if GALERI_DIR.exists():
            for fp in GALERI_DIR.rglob("*"):
                if fp.is_file():
                    zf.write(fp, "galeri/" + fp.relative_to(GALERI_DIR).as_posix())
    tmp.replace(target)
    prune_backups(kind)
    return backup_info(target)


def restore_backup(name: str) -> dict:
    target = backup_path(name)
    with zipfile.ZipFile(target) as zf:
        payload = json_util.loads(zf.read("db.json").decode("utf-8"))
        client = _client()
        db = client[os.environ["DB_NAME"]]
        for coll, docs in payload["collections"].items():
            db[coll].drop()
            if docs:
                db[coll].insert_many(docs)
        db.users.create_index("username", unique=True)
        client.close()
        for member in zf.namelist():
            if member.startswith("galeri/") and not member.endswith("/"):
                dest = GALERI_DIR / member[len("galeri/"):]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(member))
    return {"name": target.name, "collections": {k: len(v) for k, v in payload["collections"].items()}}


def delete_backup(name: str):
    backup_path(name).unlink()
