"""Launcher portable: start MongoDB -> start FastAPI (API + frontend) -> buka browser -> backup saat tutup."""
import os
import sys
import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RUNTIME = ROOT / "runtime"
DATA_DB = ROOT / "data" / "db"
LOG_DIR = ROOT / "data" / "log"
IS_WIN = os.name == "nt"


def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_port(preferred: int) -> int:
    for p in range(preferred, preferred + 100):
        if not port_busy(p):
            return p
    raise RuntimeError(f"Tidak ada port kosong mulai dari {preferred}")


def wait_port(port: int, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if port_busy(port):
            return True
        time.sleep(0.5)
    return False


def start_mongod(port: int) -> subprocess.Popen:
    exe = RUNTIME / "mongodb" / ("mongod.exe" if IS_WIN else "mongod")
    DATA_DB.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [str(exe), "--dbpath", str(DATA_DB), "--port", str(port), "--bind_ip", "127.0.0.1",
           "--logpath", str(LOG_DIR / "mongod.log"), "--logappend", "--wiredTigerCacheSizeGB", "0.25"]
    return subprocess.Popen(cmd, cwd=str(ROOT))


def stop_mongod(proc: subprocess.Popen, port: int):
    if proc.poll() is not None:
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


def banner(app_port: int, mongo_port: int):
    print("=" * 66)
    print("  RE-BARU  -  SISTEM LAPORAN RASIO ELEKTRIFIKASI KAB. MURUNG RAYA")
    print("  Mode PORTABLE / OFFLINE  (data tersimpan di folder data\\ USB ini)")
    print("=" * 66)
    print(f"  Alamat aplikasi : http://127.0.0.1:{app_port}")
    print(f"  Database lokal  : 127.0.0.1:{mongo_port}  ->  {DATA_DB}")
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
    mongod = start_mongod(mongo_port)
    if not wait_port(mongo_port, 90):
        print("[X] Database gagal start. Lihat data\\log\\mongod.log")
        print("    Penyebab umum: Visual C++ Runtime belum terpasang (lihat PANDUAN.md), atau CPU tanpa AVX.")
        stop_mongod(mongod, mongo_port)
        return 1

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
    banner(app_port, mongo_port)
    srv.run()

    print("\nMenutup aplikasi: membuat backup otomatis...", flush=True)
    try:
        from portable import create_backup
        info = create_backup("auto")
        print(f"  Backup tersimpan: backup\\{info['name']} ({info['size'] // 1024} KB)")
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
