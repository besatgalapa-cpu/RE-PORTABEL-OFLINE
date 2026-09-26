from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Form, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import json
import logging
import uuid
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
from bson import ObjectId
from PIL import Image

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from auth import (hash_password, verify_password, create_access_token,
                  create_refresh_token, get_current_user, seed_admin)
from excel_parser import parse_re_workbook
from storage import init_storage, put_object, get_object
from portable import (create_backup, list_backups, restore_backup, delete_backup, backup_path,
                      GALERI_DIR, BACKUP_DIR, FRONTEND_BUILD_DIR, BACKUP_KEEP, PORTABLE_MODE)
import asyncio
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

mongo_url = os.environ['MONGO_URL']
uvicorn_server = None  # diisi oleh launcher.py pada mode portable
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Rasio Elektrifikasi Murung Raya")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def current_user(request: Request):
    return await get_current_user(request, db)


# ---------------- Authorization (RBAC, single-org) ----------------
ROLE_PERMS = {
    "Super Admin": {"user:manage", "data:write", "galeri:write"},
    "Verifikator Data": {"data:write", "galeri:write"},
    "Viewer Eksekutif": set(),
}


def perms_for(role: str) -> set:
    return ROLE_PERMS.get(role, set())


def require(action: str):
    """Deny-by-default dependency: authorizes `action` for the caller's role, returns the user."""
    async def dep(request: Request):
        user = await get_current_user(request, db)
        if action not in perms_for(user.get("role", "")):
            raise HTTPException(status_code=403, detail="Anda tidak memiliki izin untuk aksi ini")
        return user
    return dep


# ---------------- Models ----------------
class LoginInput(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    name: str
    password: str
    role: str = "Verifikator Data"
    email: Optional[str] = ""


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class PeriodCreate(BaseModel):
    triwulan: str
    tahun: int


class SettingsInput(BaseModel):
    instansi_nama: str
    provinsi: str
    kepala_dinas: str
    target_re: float
    target_tahun: int
    bobot_non_pln: float


class CommitInput(BaseModel):
    triwulan: str
    tahun: int
    rows: List[dict]
    set_active: bool = True
    archive: Optional[dict] = None


# ---------------- Auth ----------------
def _set_cookies(response: Response, access: str, refresh: str):
    response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none", max_age=604800, path="/")


def _clean_user(u: dict):
    u["id"] = str(u["_id"]) if "_id" in u else u.get("id")
    u.pop("_id", None)
    u.pop("password_hash", None)
    return u


@api_router.post("/auth/login")
async def login(payload: LoginInput, response: Response):
    username = payload.username.strip().lower()
    user = await db.users.find_one({"username": username})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Username atau password salah")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Akun dinonaktifkan")
    ver = user.get("token_version", 0)
    access = create_access_token(str(user["_id"]), username, ver)
    refresh = create_refresh_token(str(user["_id"]), ver)
    _set_cookies(response, access, refresh)
    return {"user": _clean_user(dict(user)), "access_token": access}


@api_router.post("/auth/logout")
async def logout(response: Response, user=Depends(current_user)):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logout berhasil"}


@api_router.get("/auth/me")
async def me(user=Depends(current_user)):
    return user


@api_router.post("/auth/avatar")
async def upload_avatar(file: UploadFile = File(...), user=Depends(current_user)):
    if file.content_type not in ALLOWED_IMG:
        raise HTTPException(status_code=400, detail="File harus berupa gambar (JPG/PNG/WEBP)")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=400, detail="Ukuran file maksimal 10 MB")
    uid = str(user["id"])
    try:
        avatar_bytes = make_thumbnail(data, max_w=256, quality=80)
    except Exception:
        raise HTTPException(status_code=400, detail="Gambar tidak valid")
    path = f"murung-raya-re/avatar/{uid}.jpg"
    result = put_object(path, avatar_bytes, "image/jpeg")
    avatar_ver = int(datetime.now(timezone.utc).timestamp())
    await db.users.update_one(
        {"_id": ObjectId(uid)},
        {"$set": {"avatar_path": result["path"], "avatar_ver": avatar_ver}},
    )
    return {"avatar_ver": avatar_ver}


@api_router.get("/auth/avatar/{user_id}")
async def get_avatar(user_id: str, v: str = Query(""), user=Depends(current_user)):
    rec = await db.users.find_one({"_id": ObjectId(user_id)})
    if not rec or not rec.get("avatar_path"):
        raise HTTPException(status_code=404, detail="Foto profil tidak ditemukan")
    try:
        data, _ = get_object(rec["avatar_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="Objek tidak ditemukan di storage")
    return Response(content=data, media_type="image/jpeg")


# ---------------- Users ----------------
@api_router.get("/users")
async def list_users(user=Depends(require("user:manage"))):
    docs = await db.users.find().sort("created_at", 1).to_list(500)
    return [_clean_user(d) for d in docs]


@api_router.post("/users")
async def create_user(payload: UserCreate, user=Depends(require("user:manage"))):
    username = payload.username.strip().lower()
    if await db.users.find_one({"username": username}):
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    doc = {
        "username": username, "name": payload.name.strip(), "email": payload.email or "",
        "password_hash": hash_password(payload.password), "role": payload.role,
        "is_active": True, "token_version": 0, "created_at": now_iso(),
    }
    res = await db.users.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _clean_user(doc)


@api_router.patch("/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, user=Depends(require("user:manage"))):
    updates = {}
    if payload.name is not None:
        updates["name"] = payload.name.strip()
    if payload.role is not None:
        updates["role"] = payload.role
    if payload.is_active is not None:
        updates["is_active"] = payload.is_active
    if payload.password:
        updates["password_hash"] = hash_password(payload.password)
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan")
    await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": updates, "$inc": {"token_version": 1} if payload.password else {}})
    doc = await db.users.find_one({"_id": ObjectId(user_id)})
    return _clean_user(doc)


@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, user=Depends(require("user:manage"))):
    if str(user.get("id")) == user_id:
        raise HTTPException(status_code=400, detail="Tidak dapat menghapus akun sendiri")
    await db.users.delete_one({"_id": ObjectId(user_id)})
    return {"message": "Pengguna dihapus"}


# ---------------- Periods ----------------
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}


@api_router.get("/periods")
async def list_periods(user=Depends(current_user)):
    docs = await db.periods.find({}, {"_id": 0}).to_list(200)
    docs.sort(key=lambda p: (p["tahun"], ROMAN.get(p["triwulan"], 0)))
    period_ids = [d["id"] for d in docs]
    counts = await db.kecamatan.aggregate([
        {"$match": {"period_id": {"$in": period_ids}}},
        {"$group": {"_id": "$period_id", "count": {"$sum": 1}}}
    ]).to_list(500)
    count_map = {c["_id"]: c["count"] for c in counts}
    for d in docs:
        d["kecamatan_count"] = count_map.get(d["id"], 0)
        d["has_excel"] = bool(d.get("excel_path"))
    return docs


@api_router.post("/periods")
async def create_period(payload: PeriodCreate, user=Depends(require("data:write"))):
    kode = f"TW{ROMAN.get(payload.triwulan, payload.triwulan)}-{payload.tahun}"
    if await db.periods.find_one({"kode": kode}):
        raise HTTPException(status_code=400, detail="Periode sudah ada")
    doc = {
        "id": str(uuid.uuid4()), "kode": kode, "triwulan": payload.triwulan,
        "tahun": payload.tahun, "label": f"Triwulan {payload.triwulan} {payload.tahun}",
        "is_active": False, "is_locked": False, "created_at": now_iso(),
    }
    await db.periods.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.patch("/periods/{period_id}/activate")
async def activate_period(period_id: str, user=Depends(require("data:write"))):
    if not await db.periods.find_one({"id": period_id}):
        raise HTTPException(status_code=404, detail="Periode tidak ditemukan")
    await db.periods.update_many({}, {"$set": {"is_active": False}})
    await db.periods.update_one({"id": period_id}, {"$set": {"is_active": True}})
    return {"message": "Periode diaktifkan"}


@api_router.patch("/periods/{period_id}/lock")
async def toggle_lock(period_id: str, user=Depends(require("data:write"))):
    p = await db.periods.find_one({"id": period_id})
    if not p:
        raise HTTPException(status_code=404, detail="Periode tidak ditemukan")
    await db.periods.update_one({"id": period_id}, {"$set": {"is_locked": not p.get("is_locked", False)}})
    return {"message": "Status kunci diperbarui"}


@api_router.delete("/periods/{period_id}")
async def delete_period(period_id: str, user=Depends(require("data:write"))):
    await db.periods.delete_one({"id": period_id})
    await db.kecamatan.delete_many({"period_id": period_id})
    return {"message": "Periode dihapus"}


# ---------------- Kecamatan ----------------
async def _resolve_period(period_id: Optional[str]):
    if period_id:
        return await db.periods.find_one({"id": period_id}, {"_id": 0})
    return await db.periods.find_one({"is_active": True}, {"_id": 0})


@api_router.get("/kecamatan")
async def get_kecamatan(period_id: Optional[str] = None, user=Depends(current_user)):
    p = await _resolve_period(period_id)
    if not p:
        return {"period": None, "data": []}
    data = await db.kecamatan.find({"period_id": p["id"]}, {"_id": 0}).sort("no", 1).to_list(200)
    return {"period": p, "data": data}


# ---------------- Desa ----------------
@api_router.get("/desa")
async def get_desa(kecamatan: Optional[str] = None, search: Optional[str] = None, user=Depends(current_user)):
    q = {}
    if kecamatan and kecamatan != "ALL":
        q["kecamatan"] = kecamatan
    if search:
        q["nama"] = {"$regex": search, "$options": "i"}
    data = await db.desa.find(q, {"_id": 0}).sort("no", 1).to_list(1000)
    kecs = await db.desa.distinct("kecamatan")
    return {"data": data, "kecamatan_list": sorted(kecs)}


# ---------------- Households ----------------
@api_router.get("/households")
async def get_households(search: Optional[str] = None, kecamatan: Optional[str] = None,
                         page: int = 1, limit: int = 25, user=Depends(current_user)):
    q = {}
    if kecamatan and kecamatan != "ALL":
        q["kecamatan"] = kecamatan
    if search:
        q["$or"] = [
            {"nama": {"$regex": search, "$options": "i"}},
            {"nik": {"$regex": search, "$options": "i"}},
            {"desa": {"$regex": search, "$options": "i"}},
        ]
    total = await db.households.count_documents(q)
    skip = (page - 1) * limit
    data = await db.households.find(q, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    kecs = await db.households.distinct("kecamatan")
    return {"data": data, "total": total, "page": page, "limit": limit, "kecamatan_list": sorted([k for k in kecs if k])}


# ---------------- Dashboard ----------------
@api_router.get("/dashboard")
async def dashboard(period_id: Optional[str] = None, user=Depends(current_user)):
    p = await _resolve_period(period_id)
    all_periods = await db.periods.find({}, {"_id": 0}).to_list(200)
    all_periods.sort(key=lambda x: (x["tahun"], ROMAN.get(x["triwulan"], 0)))
    if not p:
        return {"period": None, "periods": all_periods, "kpi": None, "per_kecamatan": [], "proporsi": [], "trend": []}

    data = await db.kecamatan.find({"period_id": p["id"]}, {"_id": 0}).sort("no", 1).to_list(200)
    total_rt = sum(r["total_rt"] for r in data)
    rt_pln = sum(r["rt_pln"] for r in data)
    rt_non = sum(r["rt_nonpln"] for r in data)
    rt_belum = sum(r["rt_belum"] for r in data)
    rt_listrik = rt_pln + rt_non
    re_total = round(rt_listrik / total_rt * 100, 2) if total_rt else 0

    # previous period for delta
    idx = next((i for i, x in enumerate(all_periods) if x["id"] == p["id"]), None)
    prev = all_periods[idx - 1] if idx and idx > 0 else None
    prev_re = None
    if prev:
        pdata = await db.kecamatan.find({"period_id": prev["id"]}, {"_id": 0}).to_list(200)
        ptot = sum(r["total_rt"] for r in pdata)
        plis = sum(r["rt_pln"] + r["rt_nonpln"] for r in pdata)
        prev_re = round(plis / ptot * 100, 2) if ptot else None

    kpi = {
        "total_rt": total_rt, "rt_pln": rt_pln, "rt_nonpln": rt_non,
        "rt_belum": rt_belum, "rt_berlistrik": rt_listrik, "re_total": re_total,
        "re_pln": round(rt_pln / total_rt * 100, 2) if total_rt else 0,
        "re_nonpln": round(rt_non / total_rt * 100, 2) if total_rt else 0,
        "pct_belum": round(rt_belum / total_rt * 100, 2) if total_rt else 0,
        "jumlah_kecamatan": len(data),
        "jumlah_desa_kel": sum(r.get("jumlah_desa_kel", 0) for r in data),
        "re_delta": round(re_total - prev_re, 2) if prev_re is not None else None,
        "prev_label": prev["label"] if prev else None,
    }
    per_kecamatan = [{
        "nama": r["nama"], "re_total": r["re_total"], "re_pln": r["re_pln"],
        "re_nonpln": r["re_nonpln"], "rt_pln": r["rt_pln"], "rt_nonpln": r["rt_nonpln"],
        "rt_belum": r["rt_belum"], "total_rt": r["total_rt"],
    } for r in sorted(data, key=lambda x: x["re_total"], reverse=True)]
    proporsi = [
        {"name": "PLN Grid", "value": rt_pln, "key": "pln"},
        {"name": "Non-PLN / EBT", "value": rt_non, "key": "nonpln"},
        {"name": "Belum Berlistrik", "value": rt_belum, "key": "belum"},
    ]
    # trend across all periods
    trend = []
    period_ids = [per["id"] for per in all_periods]
    all_kec = await db.kecamatan.find({"period_id": {"$in": period_ids}}, {"_id": 0}).to_list(10000)
    kec_by_period = {}
    for k in all_kec:
        kec_by_period.setdefault(k["period_id"], []).append(k)

    for per in all_periods:
        pd = kec_by_period.get(per["id"], [])
        t = sum(r["total_rt"] for r in pd)
        lis = sum(r["rt_pln"] + r["rt_nonpln"] for r in pd)
        pln = sum(r["rt_pln"] for r in pd)
        non = sum(r["rt_nonpln"] for r in pd)
        trend.append({
            "periode": f"TW{per['triwulan']} {per['tahun']}",
            "re": round(lis / t * 100, 2) if t else 0,
            "re_pln": round(pln / t * 100, 2) if t else 0,
            "re_nonpln": round(non / t * 100, 2) if t else 0,
        })
    return {"period": p, "periods": all_periods, "kpi": kpi,
            "per_kecamatan": per_kecamatan, "proporsi": proporsi, "trend": trend}


# ---------------- Settings ----------------
@api_router.get("/settings")
async def get_settings(user=Depends(current_user)):
    s = await db.settings.find_one({"key": "main"}, {"_id": 0})
    if not s:
        s = {
            "key": "main", "instansi_nama": "Dinas ESDM Kabupaten Murung Raya",
            "provinsi": "Kalimantan Tengah", "kepala_dinas": "-",
            "target_re": 92.50, "target_tahun": 2026, "bobot_non_pln": 100.0,
        }
        await db.settings.insert_one(dict(s))
    return s


@api_router.put("/settings")
async def update_settings(payload: SettingsInput, user=Depends(require("data:write"))):
    doc = payload.model_dump()
    doc["key"] = "main"
    doc["updated_at"] = now_iso()
    await db.settings.update_one({"key": "main"}, {"$set": doc}, upsert=True)
    doc.pop("_id", None)
    return doc


# ---------------- Upload ----------------
@api_router.post("/upload/preview")
async def upload_preview(file: UploadFile = File(...), user=Depends(require("data:write"))):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Format file harus .xlsx atau .xls")
    content = await file.read()
    try:
        rows, summary = parse_re_workbook(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("parse error")
        raise HTTPException(status_code=422, detail=f"Gagal membaca file: {e}")
    # Archive the raw file to object storage so it can be re-downloaded per period
    archive = None
    try:
        apath = f"murung-raya-re/excel/{uuid.uuid4()}.xlsx"
        r = put_object(apath, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        archive = {"path": r["path"], "filename": file.filename, "size": r.get("size", len(content))}
    except Exception as e:
        logger.error(f"Excel archive failed: {e}")
    return {"filename": file.filename, "rows": rows, "summary": summary, "archive": archive}


@api_router.post("/upload/commit")
async def upload_commit(payload: CommitInput, user=Depends(require("data:write"))):
    kode = f"TW{ROMAN.get(payload.triwulan, payload.triwulan)}-{payload.tahun}"
    period = await db.periods.find_one({"kode": kode})
    if period:
        if period.get("is_locked"):
            raise HTTPException(status_code=400, detail="Periode terkunci, tidak dapat diperbarui")
        period_id = period["id"]
    else:
        period_id = str(uuid.uuid4())
        await db.periods.insert_one({
            "id": period_id, "kode": kode, "triwulan": payload.triwulan, "tahun": payload.tahun,
            "label": f"Triwulan {payload.triwulan} {payload.tahun}", "is_active": False,
            "is_locked": False, "created_at": now_iso(),
        })
    await db.kecamatan.delete_many({"period_id": period_id})
    docs = []
    for i, r in enumerate(payload.rows, 1):
        if not r.get("valid", True):
            continue
        d = {k: v for k, v in r.items() if k not in ("errors",)}
        d["period_id"] = period_id
        d["no"] = i
        docs.append(d)
    if docs:
        await db.kecamatan.insert_many(docs)
    if payload.set_active:
        await db.periods.update_many({}, {"$set": {"is_active": False}})
        await db.periods.update_one({"id": period_id}, {"$set": {"is_active": True}})
    if payload.archive and payload.archive.get("path"):
        await db.periods.update_one({"id": period_id}, {"$set": {
            "excel_path": payload.archive["path"],
            "excel_filename": payload.archive.get("filename"),
            "excel_uploaded_at": now_iso(),
        }})
    return {"message": "Data tersimpan & dashboard diperbarui", "period_id": period_id, "saved": len(docs)}


@api_router.get("/periods/{period_id}/excel")
async def download_period_excel(period_id: str, user=Depends(current_user)):
    p = await db.periods.find_one({"id": period_id})
    if not p or not p.get("excel_path"):
        raise HTTPException(status_code=404, detail="Arsip Excel tidak tersedia untuk periode ini")
    try:
        data, _ = get_object(p["excel_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="File arsip tidak ditemukan di storage")
    fn = p.get("excel_filename") or f"{p['kode']}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


# ---------------- Galeri Foto (penyimpanan lokal data/galeri) ----------------
ALLOWED_IMG = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD = 10 * 1024 * 1024


def make_thumbnail(data: bytes, max_w: int = 720, quality: int = 72) -> bytes:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    if img.width > max_w:
        ratio = max_w / float(img.width)
        img = img.resize((max_w, max(1, int(img.height * ratio))))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()


@api_router.get("/galeri")
async def galeri_list(user=Depends(current_user)):
    docs = await db.galeri.find({"is_deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for d in docs:
        d["has_thumb"] = bool(d.get("thumb_path"))
    return docs


@api_router.post("/galeri/upload")
async def galeri_upload(file: UploadFile = File(...), judul: str = Form(""),
                        kecamatan: str = Form(""), kategori: str = Form("Wilayah"),
                        user=Depends(require("galeri:write"))):
    if file.content_type not in ALLOWED_IMG:
        raise HTTPException(status_code=400, detail="File harus berupa gambar (JPG/PNG/WEBP/GIF)")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=400, detail="Ukuran file maksimal 10 MB")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    uid = uuid.uuid4()
    path = f"murung-raya-re/galeri/{uid}.{ext}"
    result = put_object(path, data, file.content_type)
    # Generate + store a compressed thumbnail for fast gallery loading
    thumb_path = None
    thumb_size = 0
    try:
        thumb_bytes = make_thumbnail(data)
        tp = f"murung-raya-re/galeri/thumb/{uid}.jpg"
        tr = put_object(tp, thumb_bytes, "image/jpeg")
        thumb_path = tr["path"]
        thumb_size = tr.get("size", len(thumb_bytes))
    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")
    doc = {
        "id": str(uuid.uuid4()), "storage_path": result["path"], "thumb_path": thumb_path,
        "external_url": None, "judul": judul.strip() or file.filename,
        "kecamatan": kecamatan.strip(), "kategori": kategori,
        "content_type": file.content_type, "size": result.get("size", len(data)),
        "thumb_size": thumb_size, "original_filename": file.filename,
        "is_deleted": False, "created_at": now_iso(),
    }
    await db.galeri.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/galeri/file/{file_id}")
async def galeri_file(file_id: str, variant: str = Query("full"), user=Depends(current_user)):
    rec = await db.galeri.find_one({"id": file_id, "is_deleted": False})
    if not rec:
        raise HTTPException(status_code=404, detail="File tidak ditemukan")
    use_thumb = variant == "thumb" and rec.get("thumb_path")
    obj_path = rec.get("thumb_path") if use_thumb else rec.get("storage_path")
    if not obj_path:
        raise HTTPException(status_code=404, detail="File tidak ditemukan")
    try:
        data, ctype = get_object(obj_path)
    except Exception:
        raise HTTPException(status_code=404, detail="Objek tidak ditemukan di storage")
    media = "image/jpeg" if use_thumb else (rec.get("content_type") or ctype)
    return Response(content=data, media_type=media)


@api_router.delete("/galeri/{file_id}")
async def galeri_delete(file_id: str, user=Depends(require("galeri:write"))):
    res = await db.galeri.update_one({"id": file_id}, {"$set": {"is_deleted": True}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Foto tidak ditemukan")
    return {"message": "Foto dihapus"}


@api_router.get("/")
async def root():
    return {"message": "API Rasio Elektrifikasi Murung Raya"}


# ---------------- Sistem, Backup & Restore (mode portable/offline) ----------------
@api_router.get("/system/info")
async def system_info(user=Depends(current_user)):
    return {
        "portable_mode": PORTABLE_MODE, "db_name": db.name,
        "mongo_host": mongo_url.split("@")[-1], "galeri_dir": str(GALERI_DIR),
        "backup_dir": str(BACKUP_DIR), "backup_keep": BACKUP_KEEP,
        "can_shutdown": uvicorn_server is not None,
    }


@api_router.get("/backup")
async def backup_list(user=Depends(require("data:write"))):
    return list_backups()


@api_router.post("/backup")
async def backup_now(user=Depends(require("data:write"))):
    try:
        return await asyncio.to_thread(create_backup, "manual")
    except Exception as e:
        logger.exception("backup failed")
        raise HTTPException(status_code=500, detail=f"Backup gagal: {e}")


@api_router.get("/backup/{name}/download")
async def backup_download(name: str, user=Depends(require("data:write"))):
    try:
        p = backup_path(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File backup tidak ditemukan")
    return FileResponse(str(p), media_type="application/zip", filename=p.name)


@api_router.post("/backup/{name}/restore")
async def backup_restore(name: str, user=Depends(require("user:manage"))):
    try:
        await asyncio.to_thread(create_backup, "auto")
        result = await asyncio.to_thread(restore_backup, name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File backup tidak ditemukan")
    except Exception as e:
        logger.exception("restore failed")
        raise HTTPException(status_code=500, detail=f"Restore gagal: {e}")
    return {"message": "Data berhasil dipulihkan. Silakan login ulang.", **result}


@api_router.delete("/backup/{name}")
async def backup_delete(name: str, user=Depends(require("user:manage"))):
    try:
        delete_backup(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File backup tidak ditemukan")
    return {"message": "Backup dihapus"}


@api_router.post("/system/shutdown")
async def system_shutdown(user=Depends(require("user:manage"))):
    if uvicorn_server is None:
        raise HTTPException(status_code=400, detail="Tutup aplikasi hanya tersedia pada mode portable")

    async def _exit():
        await asyncio.sleep(1)
        uvicorn_server.should_exit = True
    asyncio.create_task(_exit())
    return {"message": "Aplikasi sedang ditutup. Backup otomatis dibuat, lalu jendela hitam akan menutup sendiri."}


PORTABLE_ZIP = Path(os.environ.get("PORTABLE_ZIP_PATH") or (ROOT_DIR.parent / "dist" / "RE-Baru-Portable.zip"))


@api_router.get("/portable/download")
async def portable_download():
    if not PORTABLE_ZIP.exists():
        raise HTTPException(status_code=404, detail="Paket portable belum dibuat. Jalankan scripts/build_portable.sh")
    return FileResponse(str(PORTABLE_ZIP), media_type="application/zip", filename=PORTABLE_ZIP.name)


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Single-server mode (offline/portable): serve built React frontend ----
# Aktif otomatis jika folder build (FRONTEND_BUILD_DIR) tersedia; di preview tanpa build blok ini dilewati.
BUILD_DIR = FRONTEND_BUILD_DIR
if (BUILD_DIR / "index.html").exists():
    app.mount("/static", StaticFiles(directory=str(BUILD_DIR / "static")), name="static-assets")

    @app.get("/{full_path:path}")
    async def spa_handler(full_path: str):
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = BUILD_DIR / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(BUILD_DIR / "index.html"))



async def seed_data():
    if await db.periods.count_documents({}) > 0:
        return
    path = ROOT_DIR / "seed_data.json"
    if not path.exists():
        return
    with open(path) as f:
        data = json.load(f)
    for per in data["periods"]:
        pid = str(uuid.uuid4())
        await db.periods.insert_one({
            "id": pid, "kode": per["kode"], "triwulan": per["triwulan"], "tahun": per["tahun"],
            "label": per["label"], "is_active": per["is_active"], "is_locked": per["is_locked"],
            "created_at": now_iso(),
        })
        for r in per["kec"]:
            rec = dict(r)
            rec["period_id"] = pid
            await db.kecamatan.insert_one(rec)
    if data.get("households"):
        await db.households.insert_many([dict(h) for h in data["households"]])
    if data.get("desa"):
        await db.desa.insert_many([dict(d) for d in data["desa"]])
    logger.info("Seed data imported")


@app.on_event("startup")
async def startup():
    init_storage()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Mode portable={PORTABLE_MODE} | galeri={GALERI_DIR} | backup={BACKUP_DIR}")
    await db.users.create_index("username", unique=True)
    await seed_admin(db)
    await seed_data()


@app.on_event("shutdown")
async def shutdown():
    client.close()
