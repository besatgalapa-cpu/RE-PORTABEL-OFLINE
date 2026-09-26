import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { FolderInput, Loader2, Save, CheckCircle2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

export function SecondaryBackupDir({ canManage }) {
  const [cfg, setCfg] = useState(null);
  const [val, setVal] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/backup/config").then((r) => { setCfg(r.data); setVal(r.data.secondary_dir || ""); }).catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put("/backup/config", { secondary_dir: val });
      setCfg(data); setVal(data.secondary_dir || "");
      toast.success(data.secondary_dir ? `Folder cadangan kedua aktif: ${data.path}` : "Cadangan kedua dinonaktifkan");
    } catch (e) { toast.error(apiError(e)); } finally { setSaving(false); }
  };

  if (!cfg) return null;
  const active = !!cfg.secondary_dir;
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-2" data-testid="secondary-backup-panel">
      <Label className="text-sm font-semibold text-slate-800 flex items-center gap-2"><FolderInput className="w-4 h-4 text-teal-600" /> Folder Cadangan Kedua (di luar flashdisk)</Label>
      <p className="text-xs text-slate-500">Setiap backup (manual & otomatis) juga disalin ke folder ini, misalnya harddisk PC: <span className="font-mono">D:\Cadangan-RE</span>. Kosongkan untuk menonaktifkan.</p>
      <div className="flex flex-col sm:flex-row gap-2">
        <Input value={val} onChange={(e) => setVal(e.target.value)} disabled={!canManage} placeholder="Contoh: D:\Cadangan-RE" className="rounded-xl font-mono text-sm" data-testid="secondary-dir-input" />
        {canManage && (
          <Button onClick={save} disabled={saving} variant="outline" className="rounded-xl shrink-0" data-testid="secondary-dir-save">
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Save className="w-4 h-4 mr-2" />} Simpan & Uji
          </Button>
        )}
      </div>
      <div className={`text-xs flex items-center gap-1.5 ${!active ? "text-slate-400" : cfg.ok ? "text-emerald-700" : "text-amber-700"}`} data-testid="secondary-dir-status">
        {!active ? "Nonaktif — backup hanya tersimpan di flashdisk" : cfg.ok ? <><CheckCircle2 className="w-3.5 h-3.5" /> {cfg.message}: {cfg.path}</> : <><AlertTriangle className="w-3.5 h-3.5" /> {cfg.message}</>}
      </div>
    </div>
  );
}
