# PANDUAN RE-Baru Portable (Flashdisk) — 100% Offline

Sistem Laporan Rasio Elektrifikasi Kabupaten Murung Raya, dikemas agar bisa dijalankan
dari **flashdisk** di PC/laptop Windows mana pun **tanpa install, tanpa internet, tanpa setting**.

## 1. Cara Menjalankan (setiap hari)
1. Colok flashdisk, buka folder `RE-Baru-Portable`.
2. Klik ganda **`JALANKAN_APLIKASI.bat`**.
3. Tunggu ±10–20 detik. Browser terbuka otomatis di `http://127.0.0.1:8765`.
   Jika tidak terbuka, buka Chrome/Edge lalu ketik alamat tersebut.
4. Login: **Username `admin`** — **Password `adminRE1234#`**
5. **Biarkan jendela hitam (console) tetap terbuka** selama aplikasi dipakai.

## 2. Cara Menutup dengan AMAN (wajib sebelum cabut USB)
Pilih salah satu:
- Di aplikasi: menu **Pengaturan → Tutup Aplikasi & Cabut Aman**, atau
- Di jendela hitam: tekan **Ctrl+C**.

Aplikasi akan: membuat **backup otomatis** ke folder `backup\` → mematikan database dengan rapi
→ jendela menutup sendiri. Setelah itu cabut flashdisk lewat **"Safely Remove Hardware"**.

> ⚠️ Mencabut flashdisk saat jendela hitam masih terbuka dapat MERUSAK database.
> Jika terjadi, pulihkan dari `backup\` lewat menu Pengaturan → Restore.

## 3. Pindah ke PC/Laptop Lain
Tidak perlu apa-apa. Cabut (dengan aman) → colok di PC lain → klik `JALANKAN_APLIKASI.bat`.
Semua data (database, foto galeri, backup) ada di dalam flashdisk, jadi ikut berpindah.
Huruf drive boleh berubah (E: → F:), tidak berpengaruh.

## 4. "Install as App" (PWA) agar seperti aplikasi desktop
Saat aplikasi terbuka di Chrome/Edge, klik ikon **Install** di kanan address bar
(atau menu ⋮ → *Install RE-Baru* / *Apps → Install this site as an app*).
Aplikasi tampil di jendela sendiri tanpa tab browser. Server tetap harus dijalankan dulu lewat `.bat`.

## 5. Backup & Restore
- **Otomatis**: setiap kali aplikasi ditutup dengan benar → file `backup\auto_TANGGAL_JAM.zip`
  (disimpan 5 versi terakhir, yang lebih lama dihapus otomatis).
- **Manual**: menu **Pengaturan → Backup Sekarang** → file `backup\manual_....zip` (tidak dihapus otomatis).
- **Restore**: menu **Pengaturan → pilih backup → Pulihkan**. Sebelum memulihkan, sistem membuat
  backup otomatis dulu sebagai pengaman. Setelah restore, login ulang.
- **Folder cadangan kedua** (menu Pengaturan → "Folder Cadangan Kedua"): isi path di luar flashdisk, misal
  `D:\Cadangan-RE`. Setiap backup manual & otomatis ikut disalin ke sana. Jika PC lain tidak punya folder itu,
  penyalinan dilewati dengan peringatan (backup di flashdisk tetap dibuat).
- Isi file backup: seluruh database (`db.json`) + semua foto galeri. Salin file `.zip` ini ke
  komputer/harddisk lain secara berkala sebagai cadangan di luar flashdisk.

## 5b. Bila `.bat` Gagal — Kirim Pesan Errornya
Jika jendela hitam menampilkan `[X]`, foto/salin teks di jendela tersebut beserta 10 baris terakhir
`data\log\mongod.log`, lalu kirimkan agar bisa diperbaiki. Launcher sudah menampilkan ringkasan log
mongod secara otomatis saat gagal.

## 6. Struktur Folder
```
RE-Baru-Portable/
├── JALANKAN_APLIKASI.bat   <- klik ini
├── PANDUAN.md              <- file ini
├── runtime/
│   ├── python/             Python embeddable + semua library backend
│   ├── mongodb/mongod.exe  Database MongoDB 7 portable
│   │   └── legacy/mongod.exe  MongoDB 4.4 (otomatis dipakai bila CPU tanpa AVX)
│   └── vcredist/           Installer Visual C++ Runtime (dipakai otomatis bila perlu)
├── app/
│   ├── backend/            Server FastAPI (+ .env konfigurasi lokal)
│   └── frontend_build/     Tampilan aplikasi (React, sudah di-build)
├── data/
│   ├── db/                 DATABASE ANDA (jangan diedit manual)
│   ├── galeri/             Foto galeri & arsip Excel yang di-upload
│   └── log/                Log database
└── backup/                 File backup .zip (otomatis & manual)
```

## 7. Masalah Umum & Solusi
| Gejala | Penyebab | Solusi |
|---|---|---|
| Windows menampilkan "Windows protected your PC" saat klik `.bat` | SmartScreen | Klik **More info → Run anyway** |
| Antivirus memblokir `mongod.exe` / `python.exe` | False positive | Tambahkan folder `RE-Baru-Portable` ke daftar pengecualian (exclusion) antivirus |
| "Database gagal start" | Visual C++ Runtime belum ada | `.bat` memasang otomatis dari `runtime\vcredist`. Bila gagal, jalankan `vc_redist.x64.exe` manual (butuh hak admin sekali saja) |
| "Database gagal start" di PC lama | CPU tanpa instruksi AVX (MongoDB ≥5 butuh AVX) | **Otomatis**: launcher mendeteksi CPU tanpa AVX dan memakai `runtime\mongodb\legacy\mongod.exe` (MongoDB 4.4). Data lama yang dibuat MongoDB 7 dipindah ke `data\db_modern_TANGGAL` lalu dipulihkan otomatis dari backup terbaru di `backup\` (format backup tidak tergantung versi) |
| Browser tidak terbuka otomatis | Default browser belum diset | Buka manual `http://127.0.0.1:8765` (port tampil di jendela hitam) |
| Port 8765 / 27117 terpakai program lain | Bentrok port | Otomatis: launcher memilih port kosong berikutnya dan menampilkannya di jendela hitam |
| Aplikasi terasa lambat | Kecepatan flashdisk | Gunakan flashdisk **USB 3.0** berkualitas, atau salin folder ke harddisk PC |
| Lupa password admin | — | Ubah `ADMIN_PASSWORD` di `app\backend\.env`; saat start berikutnya password admin disinkronkan otomatis |
| Data rusak setelah USB dicabut paksa | Korupsi WiredTiger | Hapus isi `data\db`, jalankan aplikasi, lalu **Restore** backup terbaru dari `backup\` |

## 8. Ubah Port / Kredensial
Edit `app\backend\.env` dengan Notepad:
- `PORTABLE_APP_PORT=8765` — port aplikasi (alamat browser)
- `PORTABLE_MONGO_PORT=27117` — port database
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `JWT_SECRET`
Aplikasi hanya mendengarkan di `127.0.0.1` (tidak bisa diakses PC lain di jaringan).

## 9. Persyaratan PC Tujuan
- Windows 10/11 64-bit (MongoDB 7 tidak mendukung Windows 7/8).
- CPU dengan AVX (umumnya Intel/AMD tahun 2012 ke atas).
- Browser Chrome atau Edge.
- Ruang kosong flashdisk minimal 1 GB (disarankan 8 GB, USB 3.0).

## 10. Untuk Developer — Membuat Ulang Paket
Dari repo sumber, jalankan `bash scripts/build_portable.sh` (Linux/WSL/Git Bash, butuh internet):
mengunduh Python embeddable, wheel Windows, `mongod.exe`, VC++ redist, build React (mode offline),
lalu menyusun `dist/RE-Baru-Portable/` dan `dist/RE-Baru-Portable.zip`.
