import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { SecondaryBackupDir } from "@/components/SecondaryBackupDir";
import { Database, HardDrive, Loader2, Download, RotateCcw, Trash2, Power, Usb, ShieldCheck, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";

const fmtSize = (b) => (b > 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
const fmtDate = (iso) => new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });

function BackupRow({ b, i, canManage, onRestore, onDelete }) {
  const download = async () => {
    try {
      const r = await api.get(`/backup/${b.name}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = Object.assign(document.createElement("a"), { href: url, download: b.name });
      a.click(); URL.revokeObjectURL(url);
    } catch (e) { toast.error(apiError(e)); }
  };
  return (
    <div className="flex items-center justify-between gap-3 py-2.5 border-b border-slate-100 last:border-0" data-testid={`backup-row-${i}`}>
      <div className="min-w-0">
        <div className="font-mono text-xs sm:text-sm text-slate-800 truncate" data-testid={`backup-name-${i}`}>{b.name}</div>
        <div className="text-xs text-slate-400 flex items-center gap-2">
          <span className={`px-1.5 py-0.5 rounded-full font-semibold ${b.kind === "manual" ? "bg-sky-50 text-sky-700" : "bg-slate-100 text-slate-600"}`}>{b.kind === "manual" ? "Manual" : "Otomatis"}</span>
          {fmtDate(b.created_at)} · {fmtSize(b.size)}
        </div>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <Button size="sm" variant="ghost" onClick={download} className="h-8 px-2" title="Unduh" data-testid={`backup-download-${i}`}><Download className="w-4 h-4" /></Button>
        {canManage && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button size="sm" variant="ghost" className="h-8 px-2 text-amber-600 hover:text-amber-700" title="Pulihkan" data-testid={`backup-restore-${i}`}><RotateCcw className="w-4 h-4" /></Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Pulihkan data dari backup ini?</AlertDialogTitle>
                <AlertDialogDescription>
                  Seluruh data saat ini akan DIGANTI dengan isi <b>{b.name}</b>. Sistem otomatis membuat backup pengaman terlebih dahulu. Setelah selesai Anda perlu login ulang.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel data-testid="restore-cancel">Batal</AlertDialogCancel>
                <AlertDialogAction onClick={() => onRestore(b.name)} className="bg-amber-600 hover:bg-amber-700" data-testid="restore-confirm">Ya, Pulihkan</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
        {canManage && (
          <Button size="sm" variant="ghost" onClick={() => onDelete(b.name)} className="h-8 px-2 text-slate-400 hover:text-red-600" title="Hapus" data-testid={`backup-delete-${i}`}><Trash2 className="w-4 h-4" /></Button>
        )}
      </div>
    </div>
  );
}

export function BackupPanel() {
  const { can } = useAuth();
  const canWrite = can("data:write");
  const canManage = can("user:manage");
  const [info, setInfo] = useState(null);
  const [backups, setBackups] = useState([]);
  const [busy, setBusy] = useState("");
  const [closing, setClosing] = useState(false);

  const load = () => {
    api.get("/system/info").then((r) => setInfo(r.data)).catch(() => {});
    if (canWrite) api.get("/backup").then((r) => setBackups(r.data)).catch(() => {});
  };
  useEffect(load, [canWrite]); // eslint-disable-line react-hooks/exhaustive-deps

  const backupNow = async () => {
    setBusy("backup");
    try {
      const { data } = await api.post("/backup");
      toast.success(`Backup dibuat: ${data.name}${data.copies?.length ? " (+ salinan ke folder kedua)" : ""}`);
      if (data.copy_error) toast.warning(`Salinan ke folder kedua gagal: ${data.copy_error}`);
      load();
    }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(""); }
  };
  const restore = async (name) => {
    setBusy("restore");
    try {
      const { data } = await api.post(`/backup/${name}/restore`);
      toast.success(data.message);
      setTimeout(() => { localStorage.removeItem("re_token"); window.location.href = "/login"; }, 1500);
    } catch (e) { toast.error(apiError(e)); setBusy(""); }
  };
  const del = async (name) => {
    try { await api.delete(`/backup/${name}`); toast.success("Backup dihapus"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };
  const shutdown = async () => {
    setBusy("shutdown");
    try { const { data } = await api.post("/system/shutdown"); setClosing(true); toast.success(data.message); }
    catch (e) { toast.error(apiError(e)); setBusy(""); }
  };

  return (
    <>
      <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4" data-testid="backup-panel">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <h3 className="font-bold text-slate-900 flex items-center gap-2"><Database className="w-4 h-4 text-teal-600" /> Basis Data & Backup</h3>
          {canWrite && (
            <Button onClick={backupNow} disabled={!!busy} className="rounded-xl bg-teal-600 hover:bg-teal-700 text-white" data-testid="backup-now-btn">
              {busy === "backup" ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <HardDrive className="w-4 h-4 mr-2" />} Backup Sekarang
            </Button>
          )}
        </div>
        {info && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs" data-testid="system-info">
            <div className={`flex items-center gap-2 rounded-xl px-3 py-2 border ${info.portable_mode ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "bg-slate-50 border-slate-200 text-slate-600"}`}>
              <ShieldCheck className="w-4 h-4 shrink-0" />
              <span data-testid="system-mode">{info.portable_mode ? `Mode Portable / Offline aktif — data tersimpan di flashdisk${info.mongo_engine === "legacy" ? " (MongoDB 4.4 legacy, CPU tanpa AVX)" : ""}` : "Mode server (preview) — database lokal MongoDB"}</span>
            </div>
            <div className="flex items-center gap-2 rounded-xl px-3 py-2 border bg-slate-50 border-slate-200 text-slate-600 font-mono truncate">
              <FolderOpen className="w-4 h-4 shrink-0" /> <span className="truncate" title={info.backup_dir}>{info.backup_dir}</span>
            </div>
          </div>
        )}
        {canWrite && <SecondaryBackupDir canManage={canManage} />}
        {canWrite && (
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Riwayat Backup <span className="text-slate-400 normal-case font-normal">(otomatis disimpan {info?.backup_keep ?? 5} versi terakhir)</span></div>
            {backups.length === 0 ? (
              <div className="text-sm text-slate-400 py-3" data-testid="backup-empty">Belum ada backup. Klik "Backup Sekarang".</div>
            ) : backups.map((b, i) => <BackupRow key={b.name} b={b} i={i} canManage={canManage} onRestore={restore} onDelete={del} />)}
          </div>
        )}
      </div>

      {info?.portable_mode && canManage && (
        <div className="bg-white rounded-2xl border border-amber-200 p-6 space-y-3" data-testid="safe-eject-panel">
          <h3 className="font-bold text-slate-900 flex items-center gap-2"><Usb className="w-4 h-4 text-amber-600" /> Tutup Aplikasi & Cabut Flashdisk dengan Aman</h3>
          <p className="text-sm text-slate-600">
            Sebelum mencabut flashdisk, tutup aplikasi lewat tombol ini. Sistem akan membuat backup otomatis, mematikan database dengan rapi, lalu menutup jendela hitam. <b>Mencabut USB saat aplikasi masih berjalan dapat merusak data.</b>
          </p>
          {closing ? (
            <div className="text-sm rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 px-4 py-3" data-testid="shutdown-status">
              Aplikasi sedang ditutup. Tunggu jendela hitam menutup sendiri, lalu cabut flashdisk lewat "Safely Remove Hardware". Tab ini boleh ditutup.
            </div>
          ) : (
            <Button onClick={shutdown} disabled={!!busy} variant="outline" className="rounded-xl border-amber-300 text-amber-700 hover:bg-amber-50" data-testid="shutdown-btn">
              {busy === "shutdown" ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Power className="w-4 h-4 mr-2" />} Tutup Aplikasi Sekarang
            </Button>
          )}
        </div>
      )}
    </>
  );
}
