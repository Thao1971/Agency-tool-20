import { useState, useEffect, useCallback, useRef } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Loader2, Upload, CheckCircle2, XCircle, Clock, Trash2, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';

// Carga periódica (mensual, ad hoc) de las entregas reales de Iberinform. Sube el zip
// tal cual lo envía Iberinform (Datos_GENERALES.tab + el resto de ficheros .tab) y el
// backend lo carga en los DOS esquemas de empresa que tiene la app:
//  - legacy (companies_master) — lo usan Sector/Geo Intelligence y Valuo.
//  - moderno (master_companies) — lo usan Control&Synergy, Roll-up, Fragmentación,
//    Watchlist y el resto de motores de M&A.
// Ver POST /admin/iberinform/upload-delivery (routes/iberinform_admin.py).

const STEP_LABELS = {
  legacy_ingest: 'Esquema legacy (companies_master)',
  legacy_intelligence: 'Sector / Geo Intelligence',
  modern_ingest: 'Esquema moderno (master_companies + grafo)',
};

function StatusBadge({ status }) {
  if (status === 'completed') {
    return <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/20"><CheckCircle2 className="w-3 h-3 mr-1" />Completada</Badge>;
  }
  if (status === 'completed_with_errors' || status === 'completed_with_warnings') {
    return <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/20"><AlertTriangle className="w-3 h-3 mr-1" />Con avisos</Badge>;
  }
  if (status === 'failed') {
    return <Badge className="bg-rose-500/15 text-rose-400 border-rose-500/20"><XCircle className="w-3 h-3 mr-1" />Fallida</Badge>;
  }
  return <Badge className="bg-blue-500/15 text-blue-400 border-blue-500/20"><Loader2 className="w-3 h-3 mr-1 animate-spin" />En curso</Badge>;
}

function StepRow({ step }) {
  const label = STEP_LABELS[step.step] || step.step;
  const ok = step.status === 'ok';
  return (
    <div className="flex items-center gap-2 text-xs py-1">
      {ok ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" /> : <XCircle className="w-3.5 h-3.5 text-rose-500 flex-shrink-0" />}
      <span className={ok ? 'text-zinc-300' : 'text-rose-400'}>{label}</span>
      {step.result?.companies_imported !== undefined && (
        <span className="text-zinc-500">— {step.result.companies_imported} empresas</span>
      )}
      {step.result?.verification && (
        <span className="text-zinc-500">
          — {step.result.verification.counts?.master_companies ?? '—'} en master_companies
        </span>
      )}
      {step.error && <span className="text-rose-400">— {step.error}</span>}
    </div>
  );
}

export default function IberinformDeliveryPage() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [purging, setPurging] = useState(false);
  const fileInputRef = useRef(null);
  const pollRef = useRef(null);

  const loadRuns = useCallback(async () => {
    try {
      const { data } = await api.get('/admin/iberinform/upload-delivery');
      setRuns(data.runs || []);
      return data.runs || [];
    } catch {
      toast.error('Error cargando el historial de entregas');
      return [];
    }
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      await loadRuns();
      setLoading(false);
    })();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [loadRuns]);

  const startPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const latest = await loadRuns();
      const stillRunning = latest.some(r => r.status === 'running');
      if (!stillRunning && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }, 4000);
  };

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.zip')) {
      toast.error('El fichero debe ser el .zip que envía Iberinform');
      e.target.value = '';
      return;
    }
    const form = new FormData();
    form.append('file', file);
    setUploading(true);
    try {
      const { data } = await api.post('/admin/iberinform/upload-delivery', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast.success('Entrega recibida — cargando en segundo plano (puede tardar varios minutos con 25.000 empresas)');
      await loadRuns();
      startPolling();
    } catch (err) {
      const msg = err.response?.data?.detail || 'Error subiendo la entrega';
      toast.error(msg);
    }
    setUploading(false);
    e.target.value = '';
  };

  const handlePurgeSynthetic = async () => {
    if (!window.confirm('Esto borra permanentemente las empresas sintéticas restantes (las que quedan tras cargar datos reales). ¿Continuar?')) return;
    setPurging(true);
    try {
      const { data } = await api.post('/admin/iberinform/purge-synthetic');
      toast.success(`Purga completada: ${data.iberinform_companies_deleted ?? 0} empresas sintéticas eliminadas`);
    } catch {
      toast.error('Error purgando datos sintéticos');
    }
    setPurging(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-5 h-5 animate-spin text-zinc-500" />
      </div>
    );
  }

  const anyRunning = runs.some(r => r.status === 'running');

  return (
    <div className="space-y-4" data-testid="iberinform-delivery-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Entregas de Iberinform</h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            Cada vez que Iberinform envíe una nueva entrega, sube aquí el zip tal cual lo recibas.
            Se carga automáticamente en los dos esquemas de empresa de la app.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              onChange={handleUpload}
              className="hidden"
              data-testid="iberinform-upload-input"
              disabled={uploading || anyRunning}
            />
            <span className={`inline-flex items-center px-3 py-1.5 rounded border text-xs transition-colors ${
              uploading || anyRunning
                ? 'border-zinc-800 text-zinc-600 cursor-not-allowed'
                : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800 cursor-pointer'
            }`}>
              {uploading ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <Upload className="w-3 h-3 mr-1.5" />}
              Subir nueva entrega (.zip)
            </span>
          </label>
        </div>
      </div>

      {anyRunning && (
        <div className="flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 rounded-lg px-3 py-2 text-xs text-blue-300">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Hay una carga en curso — esta pantalla se actualiza sola cada 4s.
        </div>
      )}

      <Card className="bg-zinc-900/40 border-zinc-800/50">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-200">Historial de cargas</CardTitle>
        </CardHeader>
        <CardContent>
          {runs.length === 0 ? (
            <p className="text-xs text-zinc-500 py-4 text-center">Todavía no se ha subido ninguna entrega desde esta pantalla.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Fichero</TableHead>
                  <TableHead className="text-xs">Estado</TableHead>
                  <TableHead className="text-xs">Pasos</TableHead>
                  <TableHead className="text-xs">Iniciada</TableHead>
                  <TableHead className="text-xs">Duración</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((r) => (
                  <TableRow key={r.run_id}>
                    <TableCell className="text-xs text-zinc-300">{r.filename}</TableCell>
                    <TableCell><StatusBadge status={r.status} /></TableCell>
                    <TableCell>
                      <div className="space-y-0.5">
                        {(r.steps || []).map((s, i) => <StepRow key={i} step={s} />)}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-zinc-500">
                      <Clock className="w-3 h-3 inline mr-1" />
                      {r.started_at ? new Date(r.started_at).toLocaleString('es-ES') : '—'}
                    </TableCell>
                    <TableCell className="text-xs text-zinc-500">{r.duration_s ? `${r.duration_s}s` : '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card className="bg-zinc-900/40 border-zinc-800/50">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-200">Mantenimiento</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-zinc-300">Purgar dataset sintético</p>
              <p className="text-xs text-zinc-500 mt-0.5">
                Borra las empresas de prueba generadas antes de tener datos reales. Solo hace falta
                una vez, tras confirmar que una carga real se completó correctamente. No afecta a
                ninguna empresa real ya cargada.
              </p>
            </div>
            <Button
              variant="outline" size="sm" onClick={handlePurgeSynthetic} disabled={purging}
              className="border-rose-900/50 text-rose-400 hover:bg-rose-950/30 h-7 text-xs flex-shrink-0 ml-4"
            >
              {purging ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <Trash2 className="w-3 h-3 mr-1.5" />}
              Purgar sintéticos
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
