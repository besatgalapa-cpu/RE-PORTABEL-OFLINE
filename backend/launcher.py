"""Launcher portable: start MongoDB -> start FastAPI (API + frontend) -> buka browser -> backup saat tutup."""
import os
import sys
import json
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RUNTIME = ROOT / "runtime"
DATA_DB = ROOT / "data" / "db"
LOG_DIR = ROOT / "data" / "log"
ENGINE_FILE = ROOT / "data" / "mongo_engine.txt"
IS_WIN = os.name == "nt"
EXE = "mongod.exe" if IS_WIN else "mongod"
ENGINES = {"modern": RUNTIME / "mongodb" / EXE, "legacy": RUNTIME / "mongodb" / "legacy" / EXE}


def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_port(preferred: int) -> int:
    for p in range(preferred, preferred + 100):
        if not port_busy(p):
            return p
    raise RuntimeError(f"Tidak ada port kosong mulai dari {preferred}")


def wait_port(port: int, timeout: float, proc=None) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if port_busy(port):
            return True
        if proc is not None and proc.poll() is not None:
            return False
        time.sleep(0.5)
    return False


def cpu_has_avx() -> bool:
    if not IS_WIN:
        return True
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(39))  # PF_AVX_INSTRUCTIONS_AVAILABLE
    except Exception:
        return True


def mongod_log_tail(n: int = 12) -> str:
    fp = LOG_DIR / "mongod.log"
    if not fp.exists():
        return "(log belum ada)"
    lines = fp.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:]
    out = []
    for ln in lines:
        try:
            j = json.loads(ln)
            out.append(f"  {j.get('s', '')} {j.get('msg', '')} {json.dumps(j.get('attr', ''), ensure_ascii=False)[:160]}")
        except Exception:
            out.append("  " + ln[:200])
    return "\n".join(out)


def start_mongod(exe: Path, port: int) -> subprocess.Popen:
    DATA_DB.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [str(exe), "--dbpath", str(DATA_DB), "--port", str(port), "--bind_ip", "127.0.0.1",
           "--logpath", str(LOG_DIR / "mongod.log"), "--logappend", "--wiredTigerCacheSizeGB", "0.25"]
    # Grup proses terpisah: Ctrl+C di jendela hitam tidak ikut mematikan mongod sebelum backup selesai
    extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WIN else {"start_new_session": True}
    return subprocess.Popen(cmd, cwd=str(ROOT), **extra)


def stop_mongod(proc, port: int):
    if proc is None or proc.poll() is not None:
        return
    try:
        from pymongo import MongoClient
        MongoClient(f"mongodb://127.0.0.1:{port}", serverSelectionTimeoutMS=3000).admin.command("shutdown")
    except Exception:
        pass
    try:
        proc.wait(timeout=30)
    except Exception:
        proc.terminate()


def latest_backup() -> Path | None:
    zips = sorted((ROOT / "backup").glob("*.zip"), key=lambda p: p.stat().st_mtime)
    return zips[-1] if zips else None


def boot_database(port: int):
    """Coba mongod modern (7.x), fallback ke legacy (4.4) bila CPU tanpa AVX / gagal start.
    Mengembalikan (proc, engine, restore_from) - restore_from terisi jika data lama tidak kompatibel."""
    order = ["modern", "legacy"]
    if not cpu_has_avx() and ENGINES["legacy"].exists():
        print("  CPU ini tidak mendukung AVX -> memakai MongoDB 4.4 (legacy).")
        order = ["legacy"]
    last_engine = ENGINE_FILE.read_text().strip() if ENGINE_FILE.exists() else ""
    data_exists = any(DATA_DB.iterdir()) if DATA_DB.exists() else False

    for engine in order:
        exe = ENGINES[engine]
        if not exe.exists():
            continue
        restore_from = None
        if data_exists and last_engine and last_engine != engine:
            # File database dari versi lain tidak bisa dibuka -> pindahkan, mulai kosong, pulihkan dari backup terbaru
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            moved = ROOT / "data" / f"db_{last_engine}_{stamp}"
            print(f"  Data dibuat oleh mesin '{last_engine}', tidak kompatibel dengan '{engine}'.")
            print(f"  Memindahkan data lama ke {moved.name} dan memulihkan dari backup terbaru...")
            shutil.move(str(DATA_DB), str(moved))
            restore_from = latest_backup()
        proc = start_mongod(exe, port)
        if wait_port(port, 90, proc):
            ENGINE_FILE.parent.mkdir(parents=True, exist_ok=True)
            ENGINE_FILE.write_text(engine)
            return proc, engine, restore_from
        print(f"  [!] mongod '{engine}' gagal start (exit={proc.poll()}).")
        print(mongod_log_tail())
    return None, None, None


def banner(app_port: int, mongo_port: int, engine: str):
    print("=" * 66)
    print("  RE-BARU  -  SISTEM LAPORAN RASIO ELEKTRIFIKASI KAB. MURUNG RAYA")
    print("  Mode PORTABLE / OFFLINE  (data tersimpan di folder data\\ USB ini)")
    print("=" * 66)
    print(f"  Alamat aplikasi : http://127.0.0.1:{app_port}")
    print(f"  Database lokal  : 127.0.0.1:{mongo_port} ({'MongoDB 7' if engine == 'modern' else 'MongoDB 4.4 legacy'}) -> {DATA_DB}")
    print(f"  Login           : {os.environ.get('ADMIN_USERNAME')} / {os.environ.get('ADMIN_PASSWORD')}")
    print()
    print("  PENTING: Biarkan jendela ini terbuka selama aplikasi dipakai.")
    print("  Untuk berhenti: klik 'Tutup Aplikasi' di menu Pengaturan, atau tekan Ctrl+C di sini.")
    print("  JANGAN cabut flashdisk sebelum jendela ini menutup sendiri.")
    print("=" * 66, flush=True)


def already_running(port: int) -> bool:
    try:
        from urllib.request import urlopen
        with urlopen(f"http://127.0.0.1:{port}/api/", timeout=2) as r:
            return "Rasio Elektrifikasi" in r.read().decode("utf-8", "ignore")
    except Exception:
        return False


def main() -> int:
    os.chdir(HERE)
    sys.path.insert(0, str(HERE))
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")

    preferred_app = int(os.environ.get("PORTABLE_APP_PORT", "8765"))
    if already_running(preferred_app):
        print(f"Aplikasi sudah berjalan di http://127.0.0.1:{preferred_app} - membuka browser saja.")
        webbrowser.open(f"http://127.0.0.1:{preferred_app}")
        time.sleep(3)
        return 0

    mongo_port = free_port(int(os.environ.get("PORTABLE_MONGO_PORT", "27117")))
    app_port = free_port(preferred_app)
    os.environ["MONGO_URL"] = f"mongodb://127.0.0.1:{mongo_port}"
    os.environ["PORTABLE_MODE"] = "true"

    print("[1/3] Menyalakan database lokal...", flush=True)
    mongod, engine, restore_from = boot_database(mongo_port)
    if mongod is None:
        print("\n[X] Database gagal start. Detail lengkap: data\\log\\mongod.log")
        print("    Penyebab umum: Visual C++ Runtime belum terpasang (lihat PANDUAN.md bagian 7),")
        print("    file runtime\\mongodb tidak lengkap, atau antivirus memblokir mongod.exe.")
        return 1
    os.environ["MONGO_ENGINE"] = engine
    if restore_from is not None:
        from portable import restore_backup
        try:
            info = restore_backup(restore_from.name)
            print(f"  Data dipulihkan dari backup\\{restore_from.name}: {info['collections']}")
        except Exception as e:
            print(f"  [!] Pemulihan otomatis gagal: {e}. Gunakan menu Pengaturan -> Restore.")

    print("[2/3] Menyalakan server aplikasi...", flush=True)
    import uvicorn
    import server
    config = uvicorn.Config("server:app", host="127.0.0.1", port=app_port, log_level="warning")
    srv = uvicorn.Server(config)
    server.uvicorn_server = srv

    if IS_WIN:
        import ctypes
        HandlerType = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)

        def on_console_close(event):
            srv.should_exit = True
            stop_mongod(mongod, mongo_port)
            return True
        _handler = HandlerType(on_console_close)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_handler, True)

    def open_browser():
        if wait_port(app_port, 60):
            webbrowser.open(f"http://127.0.0.1:{app_port}")
    threading.Thread(target=open_browser, daemon=True).start()

    print("[3/3] Membuka browser...", flush=True)
    banner(app_port, mongo_port, engine)
    srv.run()

    print("\nMenutup aplikasi: membuat backup otomatis...", flush=True)
    try:
        from portable import create_backup
        info = create_backup("auto")
        print(f"  Backup tersimpan: backup\\{info['name']} ({info['size'] // 1024} KB)")
        for c in info.get("copies", []):
            print(f"  Salinan cadangan: {c}")
        if info.get("copy_error"):
            print(f"  [!] Salinan ke folder kedua gagal: {info['copy_error']}")
    except Exception as e:
        print(f"  [!] Backup otomatis gagal: {e}")
    stop_mongod(mongod, mongo_port)
    print("\nAplikasi sudah ditutup dengan aman. Flashdisk boleh dicabut (gunakan 'Safely Remove').")
    time.sleep(4)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
