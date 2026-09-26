@echo off
chcp 65001 >nul
title RE-Baru - Sistem Rasio Elektrifikasi Kab. Murung Raya (Portable)
color 0A
cd /d "%~dp0"

echo ================================================================
echo    RE-BARU - SISTEM LAPORAN RASIO ELEKTRIFIKASI MURUNG RAYA
echo              MODE PORTABLE / OFFLINE (dari flashdisk)
echo ================================================================
echo.

if not exist "runtime\python\python.exe" (
  echo [X] File runtime\python\python.exe tidak ditemukan.
  echo     Paket portable tidak lengkap. Salin ulang seluruh folder RE-Baru-Portable.
  pause
  exit /b 1
)
if not exist "runtime\mongodb\mongod.exe" (
  echo [X] File runtime\mongodb\mongod.exe tidak ditemukan.
  echo     Paket portable tidak lengkap. Salin ulang seluruh folder RE-Baru-Portable.
  pause
  exit /b 1
)

if not exist "%SystemRoot%\System32\vcruntime140_1.dll" (
  echo [!] Visual C++ Runtime belum terpasang di PC ini. Database membutuhkannya.
  if exist "runtime\vcredist\vc_redist.x64.exe" (
    echo     Memasang Visual C++ Runtime ^(sekali saja, klik Yes jika diminta^)...
    start /wait "" "runtime\vcredist\vc_redist.x64.exe" /install /passive /norestart
  ) else (
    echo     Unduh dan pasang: https://aka.ms/vs/17/release/vc_redist.x64.exe
  )
)

if not exist "data\db" mkdir "data\db"
if not exist "data\galeri" mkdir "data\galeri"
if not exist "backup" mkdir "backup"

"runtime\python\python.exe" -E -s "app\backend\launcher.py"
if errorlevel 1 (
  echo.
  echo [X] Aplikasi berhenti karena kesalahan. Lihat pesan di atas dan file data\log\mongod.log
  pause
)
