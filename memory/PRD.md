# PRD — Sistem Laporan Rasio Elektrifikasi Kabupaten Murung Raya

## Problem Statement
Website laporan rasio elektrifikasi Kabupaten Murung Raya dengan Admin Panel: Login Admin, Ringkasan, Upload Excel, Data Desa/Kelurahan, Data Kecamatan, Data Keluarga/RT, Periode Data, Pengguna Admin, Pengaturan. Alur: Upload Excel → Validasi → Simpan → Dashboard diperbarui. Data dari file Excel RE TW I & TW II 2026.

## Architecture
- Backend: FastAPI + MongoDB (motor). Modules: server.py, auth.py (JWT+bcrypt), excel_parser.py (openpyxl).
- Frontend: React 19 + Tailwind + shadcn/ui + recharts + sonner. Auth token in localStorage (`re_token`), Bearer header.
- Theme: light professional civic (teal #0D9488, PLN blue, EBT green, amber). Fonts: Plus Jakarta Sans + JetBrains Mono.

## User Personas
- Super Admin ESDM: full access, kelola data & pengguna.
- Verifikator Data / Viewer Eksekutif: peran tambahan (dikelola via Pengguna Admin).

## Core Requirements (static)
- Username+password login (admin / adminRE1234#).
- Dashboard KPI + 4 charts (donut proporsi, bar per kecamatan, area trend, stacked PLN/Non-PLN).
- Upload Excel → validasi → preview → commit → dashboard update.
- Data tables: Kecamatan, Desa/Kelurahan, Keluarga/RT (paginated).
- Periode management (aktif/lock), Pengguna Admin CRUD, Pengaturan.

## Implemented (2026-06)
- [x] JWT username auth + admin seed + user management
- [x] Auto-seed real data: TW I 2026 (37,041 RT) & TW II 2026 (36,800 RT), 10 kecamatan, 756 households, 43 desa
- [x] Dashboard with KPIs, donut, per-kecamatan bar, trend area, stacked bar, period selector, target progress
- [x] Data Kecamatan (search, period switch, CSV export), Data Desa (filter/search), Data Keluarga/RT (search + pagination)
- [x] Upload flow with real openpyxl parser for "RE MURUNG RAYA" sheet + validation + commit
- [x] Periode Data CRUD (activate/lock/delete), Pengguna Admin CRUD, Pengaturan
- [x] Tested: backend 17/17, frontend all flows pass
- [x] Removed "Data Keluarga/RT" from sidebar menu (per user visual edit)

## Backlog / Next (P1/P2)
- P1: Per-desa electrification detail (from detailed sheet keterangan PLN/Non-PLN, jenis pembangkit, sumber bantuan)
- P1: Export dashboard to PDF/print report
- P2: Map visualization of kecamatan
- P2: Audit log for uploads/edits
- P2: Role-based access enforcement (currently all authed users have full access)

## Notes
- No email/password-reset (username-only internal login).
- Period kode format: TW1-2026 / TW2-2026.

## Portable / Offline (2026-06) — RE-Baru
- [x] Import repo besatgalapa-cpu/RE-Baru (main). Deps installed, app sehat di preview.
- [x] Fase 1: object storage cloud DIHAPUS → storage lokal (`LOCAL_STORAGE_DIR`, portable: `data/galeri`). Seed galeri online dihapus. Font Google → @fontsource (offline). `api.js` fallback same-origin. FastAPI serve build React (`FRONTEND_BUILD_DIR`).
- [x] Fase 2: `scripts/build_portable.sh` → `dist/RE-Baru-Portable/` + zip (Python 3.11.9 embeddable + wheel win_amd64, mongod.exe 7.0.14, vc_redist, frontend build offline, `JALANKAN_APLIKASI.bat`, `PANDUAN.md`). `backend/launcher.py`: cek app sudah jalan, pilih port kosong (8765/27117), start mongod (127.0.0.1, dbpath data/db), uvicorn in-process, buka browser, backup otomatis saat tutup, mongod shutdown rapi, handler console close.
- [x] Fase 3: `portable.py` backup zip (db.json via bson json_util + galeri) rolling 5 (auto_), manual_ tidak dihapus; endpoints /api/backup (list/create/download/restore/delete), /api/system/info, /api/system/shutdown (portable only); UI BackupPanel di Pengaturan + panel Tutup Aman (portable only). PWA: manifest lokal, icon, sw.js, index.offline.html.
- [x] Tested: launcher end-to-end disimulasikan di Linux (mongod symlink) — login, backup, shutdown → auto backup → mongod stop OK. Testing agent iteration_1: backend 100%, frontend 100%.
- Unduh paket: `GET /api/portable/download` (dist/RE-Baru-Portable.zip, ~72 MB).

## Backlog Portable
- P1: Uji nyata di PC Windows kedua (tanpa Python/Mongo) — belum bisa dilakukan dari sini.
- P2: Opsi migrasi ke DB embedded single-file (hanya jika USB tidak andal; perlu persetujuan user).
- P2: mongod 4.4 fallback untuk CPU tanpa AVX (otomatis).

- [x] Imported from github.com/besatgalapa-cpu/RE (public). Stack verified = React + FastAPI + MongoDB (matches default).
- [x] Env restored: JWT_SECRET, ADMIN_USERNAME=admin / ADMIN_PASSWORD=adminRE1234#, EMERGENT_LLM_KEY (object storage untuk Galeri).
- [x] Backend & frontend boot clean; login + dashboard + seed data verified via curl & screenshot.
- Audit findings: full app already built (10 pages: Dashboard, Upload, Kecamatan, Desa, Keluarga, Periode, Pengguna, Pengaturan, Galeri, Login). No half-done features detected.
- Tech debt: role-based access not enforced (all authed users = full access); no audit log; no PDF export.
- Fitur baru belum ditentukan user — menunggu arahan (lihat Next Action Items).
