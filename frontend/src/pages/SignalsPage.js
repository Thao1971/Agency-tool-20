import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Loader2, Zap, TrendingUp, TrendingDown, Minus, Clock, RefreshCw, X } from 'lucide-react';
import { toast } from 'sonner';

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' }); }
  catch { return '—'; }
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return '—'; }
}

const TREND_CFG = {
  improving: { icon: TrendingUp, color: 'text-emerald-400', label: 'Mejorando' },
  worsening: { icon: TrendingDown, color: 'text-rose-400', label: 'Empeorando' },
  stable: { icon: Minus, color: 'text-zinc-400', label: 'Estable' },
};

const SEVERITY_CFG = {
  opportunity: { color: 'border-amber-500/30 text-amber-400 bg-amber-500/5', label: 'Oportunidad' },
  positive: { color: 'border-emerald-500/30 text-emerald-400 bg-emerald-500/5', label: 'Positiva' },
  info: { color: 'border-zinc-600 text-zinc-400 bg-zinc-500/5', label: 'Info' },
  warning: { color: 'border-orange-500/30 text-orange-400 bg-orange-500/5', label: 'Aviso' },
  risk: { color: 'border-rose-500/30 text-rose-400 bg-rose-500/5', label: 'Riesgo' },
  critical: { color: 'border-red-600/40 text-red-400 bg-red-600/10', label: 'Crítica' },
};

const STATUS_CFG = {
  active: { color: 'border-blue-500/30 text-blue-400 bg-blue-500/5', label: 'Activa' },
  disappeared: { color: 'border-zinc-700 text-zinc-500 bg-zinc-800/40', label: 'Desaparecida' },
  resolved: { color: 'border-zinc-700 text-zinc-500 bg-zinc-800/40', label: 'Resuelta' },
};

const DIM_LABELS = { impact: 'Impacto', confidence: 'Confianza', urgency: 'Urgencia', persistence: 'Persistencia' };

function DimBar({ label, value }) {
  const pct = Math.round((value || 0) * 100);
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[9px] text-zinc-500 w-16 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[9px] text-zinc-400 w-8 text-right tabular-nums">{pct}%</span>
    </div>
  );
}

function SeverityBadge({ severity }) {
  const cfg = SEVERITY_CFG[severity] || SEVERITY_CFG.info;
  return <Badge variant="outline" className={`text-[9px] ${cfg.color}`}>{cfg.label}</Badge>;
}

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.active;
  return <Badge variant="outline" className={`text-[9px] ${cfg.color}`}>{cfg.label}</Badge>;
}

// Exported so other screens (Oportunidades, Watchlist) can render a consistent, clickable
// signal reference that navigates here (task: enlazar señales desde cualquier parte).
export function signalLink(signalId, masterId) {
  const params = new URLSearchParams();
  if (signalId) params.set('signal_id', signalId);
  if (masterId) params.set('master_id', masterId);
  return `/signals?${params.toString()}`;
}

function SignalDetailDialog({ signalId, onClose, typeLabel }) {
  const [signal, setSignal] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!signalId) return;
    setLoading(true);
    (async () => {
      try {
        const { data } = await api.get(`/signal-intelligence/signal/${signalId}/view`);
        setSignal(data);
        if (data?.master_id) {
          const h = await api.get('/signal-intelligence/history/view', {
            params: { identifier: data.master_id, signal_type: data.signal_type },
          });
          setHistory(h.data.signals?.[0]?.timeline || []);
        }
      } catch (e) {
        toast.error('No se pudo cargar el detalle de la señal');
        setSignal(null);
      }
      setLoading(false);
    })();
  }, [signalId]);

  return (
    <Dialog open={!!signalId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-zinc-900 border-zinc-800 max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-zinc-100 text-sm flex items-center gap-2">
            <Zap className="w-4 h-4 text-blue-400" /> Detalle de señal
          </DialogTitle>
        </DialogHeader>
        {loading ? (
          <div className="flex items-center justify-center py-10"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>
        ) : !signal ? (
          <p className="text-xs text-zinc-500 py-6 text-center">Señal no encontrada.</p>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline" className="text-[9px] border-blue-500/30 text-blue-400 bg-blue-500/5">
                {typeLabel ? typeLabel(signal.signal_type) : signal.signal_type}
              </Badge>
              <SeverityBadge severity={signal.severity} />
              <StatusBadge status={signal.status} />
              {signal.trend && TREND_CFG[signal.trend] && (
                <span className={`flex items-center gap-1 text-[9px] ${TREND_CFG[signal.trend].color}`}>
                  {(() => { const I = TREND_CFG[signal.trend].icon; return <I className="w-3 h-3" />; })()}
                  {TREND_CFG[signal.trend].label}
                </span>
              )}
            </div>

            <p className="text-xs text-zinc-400">{signal.explanation}</p>

            <div className="space-y-1">
              {Object.entries(DIM_LABELS).map(([k, l]) => (
                <DimBar key={k} label={l} value={signal.dimensions?.[k]} />
              ))}
            </div>

            {signal.recommended_actions?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {signal.recommended_actions.map((a, i) => (
                  <Badge key={i} variant="outline" className="text-[8px] text-zinc-400 border-zinc-700">{a}</Badge>
                ))}
              </div>
            )}

            <div className="grid grid-cols-3 gap-2 text-[10px] text-zinc-500 pt-2 border-t border-zinc-800">
              <div><span className="text-zinc-600 block">Detectada</span>{fmtDate(signal.first_detected_at)}</div>
              <div><span className="text-zinc-600 block">Última vez vista</span>{fmtDate(signal.last_seen_at)}</div>
              <div><span className="text-zinc-600 block">Ocurrencias</span>{signal.occurrences ?? '—'}</div>
            </div>

            {history.length > 0 && (
              <div className="pt-2 border-t border-zinc-800">
                <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">Historial</p>
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {history.slice().reverse().map((h, i) => (
                    <div key={i} className="flex items-center justify-between text-[10px] text-zinc-500">
                      <span>{fmtDateTime(h.observed_at)}</span>
                      <span className="text-zinc-600">impacto {Math.round((h.dimensions?.impact || 0) * 100)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function SignalsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [category, setCategory] = useState('all');
  const [severity, setSeverity] = useState('all');
  const [status, setStatus] = useState('active');
  const [provincia, setProvincia] = useState('');
  const [masterId, setMasterId] = useState(searchParams.get('master_id') || '');
  const [catalog, setCatalog] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSignalId, setSelectedSignalId] = useState(searchParams.get('signal_id') || null);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.get('/signal-intelligence/catalog/view').then(r => setCatalog(r.data)).catch(() => setCatalog(null));
  }, []);

  useEffect(() => {
    // Real total for the current status filter, NOT capped by the /signals/view
    // `limit` (this page only ever fetches up to 100 rows to render) — see
    // routes/signal_intelligence.py _signal_stats().
    api.get('/signal-intelligence/stats/view', { params: { status: status !== 'all' ? status : '' } })
      .then(r => setStats(r.data)).catch(() => setStats(null));
  }, [status]);

  const typeLabel = (st) => catalog?.signal_types?.find(t => t.signal_type === st)?.description || st;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/signal-intelligence/signals/view', {
        params: {
          category: category !== 'all' ? category : undefined,
          severity: severity !== 'all' ? severity : undefined,
          // '' (not undefined) when 'all' is selected: the backend's `status` query
          // param defaults to "active" when omitted entirely (sensible default for
          // external API callers), so omitting it here would silently keep
          // filtering to active-only even though the user picked "Todos los
          // estados". An explicit empty string reaches the backend and its
          // `if status: q["status"] = status` check treats it as "no filter".
          status: status !== 'all' ? status : '',
          provincia: provincia || undefined,
          master_id: masterId || undefined,
          limit: 100,
        },
      });
      setItems(data.signals || []);
    } catch (e) {
      toast.error('Error cargando señales');
      setItems([]);
    }
    setLoading(false);
  }, [category, severity, status, provincia, masterId]);

  useEffect(() => { load(); }, [load]);

  const openSignal = (signalId) => {
    setSelectedSignalId(signalId);
    const next = new URLSearchParams(searchParams);
    next.set('signal_id', signalId);
    setSearchParams(next, { replace: true });
  };

  const closeSignal = () => {
    setSelectedSignalId(null);
    const next = new URLSearchParams(searchParams);
    next.delete('signal_id');
    setSearchParams(next, { replace: true });
  };

  return (
    <div className="space-y-5" data-testid="signals-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
            <Zap className="w-4 h-4 text-blue-400" /> Señales
          </h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            Todas las señales detectadas por el motor (financieras, riesgo, corporativas, mercado, propiedad, oportunidad...) —
            distinto de Oportunidades, que solo muestra el subconjunto de severidad "oportunidad"
            {stats && <span className="text-zinc-400 font-medium"> — {stats.total_signals} señales en total{status !== 'all' ? ` (${STATUS_CFG[status]?.label.toLowerCase() || status})` : ''}</span>}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} className="border-zinc-700 text-zinc-300 h-7 text-xs">
          <RefreshCw className="w-3 h-3 mr-1.5" /> Actualizar
        </Button>
      </div>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3 flex flex-wrap items-center gap-2">
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-8 w-44 text-xs">
              <SelectValue placeholder="Categoría" />
            </SelectTrigger>
            <SelectContent className="bg-zinc-900 border-zinc-700">
              <SelectItem value="all">Todas las categorías</SelectItem>
              {(catalog?.categories || []).map(c => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={severity} onValueChange={setSeverity}>
            <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-8 w-40 text-xs">
              <SelectValue placeholder="Severidad" />
            </SelectTrigger>
            <SelectContent className="bg-zinc-900 border-zinc-700">
              <SelectItem value="all">Cualquier severidad</SelectItem>
              {Object.entries(SEVERITY_CFG).map(([k, c]) => (
                <SelectItem key={k} value={k}>{c.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-8 w-36 text-xs">
              <SelectValue placeholder="Estado" />
            </SelectTrigger>
            <SelectContent className="bg-zinc-900 border-zinc-700">
              <SelectItem value="active">Activas</SelectItem>
              <SelectItem value="disappeared">Desaparecidas</SelectItem>
              <SelectItem value="all">Todos los estados</SelectItem>
            </SelectContent>
          </Select>

          <Input value={provincia} onChange={e => setProvincia(e.target.value)}
            placeholder="Provincia (ej. MADRID)"
            className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs w-44" />

          {masterId && (
            <Badge variant="outline" className="text-[10px] border-blue-500/30 text-blue-400 bg-blue-500/5 flex items-center gap-1">
              Empresa: {masterId}
              <button onClick={() => setMasterId('')} className="ml-1"><X className="w-2.5 h-2.5" /></button>
            </Badge>
          )}
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex items-center justify-center py-16"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>
      ) : items.length === 0 ? (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-8 text-center text-xs text-zinc-500">
            Sin señales para estos filtros.
          </CardContent>
        </Card>
      ) : (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800 hover:bg-transparent">
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Empresa</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Tipo</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Severidad</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Estado</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Tendencia</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Detectada</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Vista por última vez</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((s, i) => {
                  const trend = TREND_CFG[s.trend];
                  const TrendIcon = trend?.icon;
                  return (
                    <TableRow key={s.signal_id || i}
                      className="border-zinc-800/50 cursor-pointer hover:bg-zinc-800/40"
                      onClick={() => s.signal_id && openSignal(s.signal_id)}
                      data-testid="signal-row">
                      <TableCell className="py-2 text-xs text-zinc-200">{s.name || s.master_id}</TableCell>
                      <TableCell className="py-2 text-xs text-zinc-400">{typeLabel(s.signal_type)}</TableCell>
                      <TableCell className="py-2"><SeverityBadge severity={s.severity} /></TableCell>
                      <TableCell className="py-2"><StatusBadge status={s.status} /></TableCell>
                      <TableCell className="py-2">
                        {trend && (
                          <span className={`flex items-center gap-1 text-[10px] ${trend.color}`}>
                            <TrendIcon className="w-3 h-3" />{trend.label}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="py-2 text-[10px] text-zinc-500">
                        <span className="flex items-center gap-1"><Clock className="w-2.5 h-2.5" />{fmtDate(s.first_detected_at)}</span>
                      </TableCell>
                      <TableCell className="py-2 text-[10px] text-zinc-500">{fmtDate(s.last_seen_at)}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <SignalDetailDialog signalId={selectedSignalId} onClose={closeSignal} typeLabel={typeLabel} />
    </div>
  );
}
