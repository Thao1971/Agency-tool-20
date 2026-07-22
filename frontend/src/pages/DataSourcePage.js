import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Database, Play, Loader2, RefreshCw, Clock, ChevronLeft, ChevronRight, Table2, Search, Zap, Upload } from 'lucide-react';
import { toast } from 'sonner';
import api from '@/lib/api';

function fmtNum(v) { return v != null ? Number(v).toLocaleString('es-ES') : '—'; }
function fmtDateTime(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return iso; }
}
function decodeEntities(s) {
  if (typeof document === 'undefined' || !/&[#a-zA-Z0-9]+;/.test(s)) return s;
  const el = document.createElement('textarea');
  el.innerHTML = s;
  return el.value;
}
function fmtCell(v) {
  if (v == null) return '—';
  if (Array.isArray(v)) return v.length ? v.map(fmtCell).join(', ') : '—';
  if (typeof v === 'object') { const keys = Object.keys(v); if (!keys.length) return '—'; const s = JSON.stringify(v); return s.length > 80 ? s.slice(0, 80) + '…' : s; }
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString('es-ES') : v.toString();
  if (typeof v === 'boolean') return v ? 'Sí' : 'No';
  const s = decodeEntities(String(v));
  return s.length > 90 ? s.slice(0, 90) + '…' : s;
}

const PAGE_SIZE = 25;

// Hide technical / auxiliary fields by default (only when no display_fields given).
function isTechnicalField(k) {
  return /(^_)|(_id$)|(^id$)|(_url$)|(uuid)|(idempotency)|(_at$)|(_path$)|(_version$)|(^source$)|(^source_provider$)|(^source_record_id$)|(^source_row$)|(^job_id$)|(^last_update$)|(_mapped_at$)|(_evidence)|(_raw$)/i.test(k);
}

// snake_case → human label, with optional declarative override from META.field_labels.
function humanize(field, labels) {
  if (labels && labels[field]) return labels[field];
  return field.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// Resolve table columns: display_fields (whitelist, ordered) > hidden_fields/default-hide.
function resolveColumns(items, src) {
  if (!items.length) return [];
  const keys = Object.keys(items[0]);
  if (src?.display_fields?.length) {
    const present = src.display_fields.filter((f) => keys.includes(f));
    if (present.length) return present;
  }
  const hidden = new Set(src?.hidden_fields || []);
  const filtered = keys.filter((k) => !hidden.has(k) && !isTechnicalField(k));
  return filtered.length ? filtered : keys;
}

const PHASE_CFG = {
  active: { dot: 'bg-emerald-500', label: 'Activo', color: 'text-emerald-400' },
  derived: { dot: 'bg-cyan-500', label: 'Derivado', color: 'text-cyan-400' },
  stub: { dot: 'bg-zinc-500', label: 'Stub (Fase 2)', color: 'text-zinc-400' },
};

function Metric({ label, value, color = 'text-zinc-100', testid }) {
  return (
    <div className="bg-zinc-950/40 rounded-md p-3 border border-zinc-800/50" data-testid={testid}>
      <p className="text-[9px] uppercase tracking-wider text-zinc-500">{label}</p>
      <p className={`text-xl font-bold tabular-nums ${color}`}>{value ?? '—'}</p>
    </div>
  );
}

export default function DataSourcePage() {
  const { source } = useParams();
  const [src, setSrc] = useState(null);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ingesting, setIngesting] = useState(false);
  const [data, setData] = useState(null);
  const [dataPage, setDataPage] = useState(1);
  const [dataLoading, setDataLoading] = useState(false);
  const [filterField, setFilterField] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [applied, setApplied] = useState(null); // { field, value }

  const load = async () => {
    setLoading(true);
    try {
      const [statusRes, auditRes] = await Promise.all([
        api.get('/public/intelligence/sync-status').catch(() => ({ data: { sources: {} } })),
        api.get('/intelligence/scheduler/audit?limit=50').catch(() => ({ data: { runs: [] } })),
      ]);
      setSrc((statusRes.data?.sources || {})[source] || null);
      setAudit(auditRes.data?.runs || []);
    } catch {}
    setLoading(false);
  };

  const loadData = async (page, filter) => {
    setDataLoading(true);
    try {
      let url = `/intelligence/sources/${source}/query?page=${page}&page_size=${PAGE_SIZE}`;
      if (filter?.field && filter?.value) {
        url += `&field=${encodeURIComponent(filter.field)}&value=${encodeURIComponent(filter.value)}`;
      }
      const r = await api.get(url);
      setData(r.data);
    } catch { setData(null); }
    setDataLoading(false);
  };

  useEffect(() => {
    setDataPage(1); setApplied(null); setFilterField(''); setFilterValue('');
    load(); /* eslint-disable-next-line */
  }, [source]);

  useEffect(() => {
    if (src?.queryable) loadData(dataPage, applied);
    else setData(null);
    /* eslint-disable-next-line */
  }, [src?.queryable, dataPage, applied, source]);

  const runSearch = () => {
    setDataPage(1);
    setApplied(filterField && filterValue ? { field: filterField, value: filterValue } : null);
  };
  const clearSearch = () => {
    setFilterField(''); setFilterValue(''); setDataPage(1); setApplied(null);
  };

  const triggerIngest = async () => {
    setIngesting(true);
    try {
      const r = await api.post(`/intelligence/sources/ingest/${source}`);
      const res = r.data || {};
      if (res.status === 'error') toast.error(`Ingesta falló: ${res.reason || 'error'}`);
      else toast.success(`Ingesta completada: ${res.inserted ?? 0} insertados`);
      await load();
      if (src?.queryable) await loadData(1, applied);
      setDataPage(1);
    } catch { toast.error('No se pudo ejecutar la ingesta'); }
    setIngesting(false);
  };

  const [actionLoading, setActionLoading] = useState(null);

  const runAction = async (action) => {
    setActionLoading(action.id);
    try {
      let url = action.endpoint;
      if (action.params && Object.keys(action.params).length) {
        const qs = new URLSearchParams(action.params).toString();
        url += (url.includes('?') ? '&' : '?') + qs;
      }
      const r = await api.post(url, null, { timeout: 180000 });
      toast.success(`${action.label}: ${JSON.stringify(r.data).substring(0, 120)}`);
      await load();
      if (src?.queryable) await loadData(dataPage, applied);
    } catch (e) {
      toast.error(`${action.label} falló: ${e.response?.data?.detail || e.message}`);
    }
    setActionLoading(null);
  };

  const runUpload = async (action, file) => {
    if (!file) return;
    setActionLoading(action.id);
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await api.post(action.endpoint, form, {
        headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000,
      });
      toast.success(`${action.label}: ${JSON.stringify(r.data).substring(0, 120)}`);
      await load();
      if (src?.queryable) await loadData(dataPage, applied);
    } catch (e) {
      toast.error(`${action.label} falló: ${e.response?.data?.detail || e.message}`);
    }
    setActionLoading(null);
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>;
  }

  if (!src) {
    return (
      <div className="space-y-3" data-testid="data-source-page">
        <h1 className="text-lg font-bold text-zinc-100">Fuente no encontrada</h1>
        <p className="text-xs text-zinc-500">La fuente <span className="font-mono text-zinc-300">{source}</span> no existe en el Intelligence Engine.</p>
      </div>
    );
  }

  const phase = PHASE_CFG[src.phase] || { dot: 'bg-zinc-500', label: src.phase, color: 'text-zinc-400' };

  return (
    <div className="space-y-5" data-testid="data-source-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
            <Database className="w-4 h-4 text-emerald-400" /> {src.name}
            <span className="flex items-center gap-1 ml-2">
              <span className={`w-2 h-2 rounded-full ${phase.dot}`} />
              <span className={`text-[10px] ${phase.color}`}>{phase.label}</span>
            </span>
          </h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            Origen <span className="font-mono text-zinc-400">{src.source}</span> · {src.frequency}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="text-[10px] text-zinc-500 hover:text-zinc-300 flex items-center gap-1 transition-colors" data-testid="data-source-refresh-btn">
            <RefreshCw className="w-3 h-3" /> refrescar
          </button>
          {src.supports_manual_ingestion && (
            <button onClick={triggerIngest} disabled={ingesting}
              className="flex items-center gap-1.5 text-[11px] font-medium px-3 py-1.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 transition-colors disabled:opacity-50"
              data-testid="data-source-ingest-btn">
              {ingesting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              {ingesting ? 'Ejecutando…' : 'Ejecutar ahora'}
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Metric label="Registros" value={fmtNum(src.records)} testid="data-source-records" />
        <Metric label="Señales" value={fmtNum(src.signals_count)} color="text-violet-300" testid="data-source-signals" />
        <Metric label="Última ejecución" value={fmtDateTime(src.last_run)} color="text-zinc-300" testid="data-source-lastrun" />
        <Metric label="Duración" value={src.duration_ms != null ? `${src.duration_ms} ms` : '—'} color="text-zinc-300" />
        <Metric label="Insertados" value={fmtNum(src.inserted_count)} color="text-zinc-300" />
        <Metric label="Errores" value={fmtNum(src.error_count)} color={src.error_count > 0 ? 'text-rose-400' : 'text-zinc-300'} testid="data-source-errors" />
      </div>

      {/* Acciones operativas — declaradas en META, sin formularios específicos */}
      {(src.actions?.length > 0) && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
              <Zap className="w-3.5 h-3.5 text-amber-400" /> Acciones operativas
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2" data-testid="data-source-actions">
              {src.actions.map((a) => (
                a.kind === 'upload' ? (
                  <label key={a.id}
                    className="flex items-center gap-1.5 text-[11px] font-medium px-3 py-1.5 rounded bg-zinc-800/60 border border-zinc-700 text-zinc-200 hover:bg-zinc-800 transition-colors cursor-pointer"
                    data-testid={`data-source-action-${a.id}`}>
                    {actionLoading === a.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                    {a.label}
                    <input type="file" className="hidden" disabled={actionLoading === a.id}
                      onChange={(e) => { runUpload(a, e.target.files?.[0]); e.target.value = ''; }}
                      data-testid={`data-source-upload-${a.id}`} />
                  </label>
                ) : (
                  <button key={a.id} onClick={() => runAction(a)} disabled={actionLoading != null}
                    className="flex items-center gap-1.5 text-[11px] font-medium px-3 py-1.5 rounded bg-blue-500/10 border border-blue-500/30 text-blue-300 hover:bg-blue-500/20 transition-colors disabled:opacity-40"
                    data-testid={`data-source-action-${a.id}`}>
                    {actionLoading === a.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
                    {a.label}
                  </button>
                )
              ))}
            </div>
            <p className="text-[9px] text-zinc-600 mt-2">Acciones declaradas en el META del módulo. Las operaciones de sincronización pueden tardar.</p>
          </CardContent>
        </Card>
      )}

      {src.supports_manual_ingestion && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-zinc-500" /> Historial de ingestas (er_audit_logs)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1 max-h-80 overflow-y-auto" data-testid="data-source-audit">
              {(() => {
                const runs = audit.filter(r => !data?.collection || r.source_name === data.collection);
                if (runs.length === 0) return <p className="text-[11px] text-zinc-600">Sin ejecuciones registradas todavía.</p>;
                return runs.map((r) => (
                <div key={r.log_id} className="flex items-center justify-between text-[10px] py-1 px-2 bg-zinc-950/30 rounded">
                  <span className="font-mono text-zinc-500">{r.source_name}</span>
                  <span className={`uppercase tracking-wider ${r.status === 'ok' ? 'text-emerald-400' : 'text-rose-400'}`}>{r.status}</span>
                  <span className="text-zinc-400 tabular-nums">{r.inserted_count ?? 0} ins · {r.error_count ?? 0} err</span>
                  <span className="text-zinc-400 tabular-nums">{r.duration_ms != null ? `${r.duration_ms} ms` : '—'}</span>
                  <span className="text-zinc-600">{fmtDateTime(r.started_at)}</span>
                </div>
                ));
              })()}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Data explorer — dynamic query + paginated real records of the collection */}
      {src.queryable && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs text-zinc-400 flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Table2 className="w-3.5 h-3.5 text-emerald-400" /> Datos
                {data && <span className="text-[10px] text-zinc-600 font-normal">· {fmtNum(data.total_records)} registros{applied ? ' (filtrado)' : ''} · <span className="font-mono">{data.collection}</span></span>}
              </span>
              {dataLoading && <Loader2 className="w-3 h-3 animate-spin text-zinc-500" />}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Search bar — field dropdown auto-generated from the documents */}
            <div className="flex flex-wrap items-end gap-2 pb-2 border-b border-zinc-800/50" data-testid="data-source-search">
              <div className="flex flex-col gap-1">
                <label className="text-[9px] uppercase tracking-wider text-zinc-500">Campo</label>
                <select value={filterField} onChange={(e) => setFilterField(e.target.value)}
                  className="bg-zinc-950 border border-zinc-800 rounded text-[11px] text-zinc-200 px-2 py-1.5 min-w-[160px] focus:outline-none focus:border-zinc-600"
                  data-testid="data-source-field-select">
                  <option value="">— selecciona campo —</option>
                  {(data?.fields || []).map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1 flex-1 min-w-[180px]">
                <label className="text-[9px] uppercase tracking-wider text-zinc-500">Valor</label>
                <input value={filterValue} onChange={(e) => setFilterValue(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') runSearch(); }}
                  placeholder="Introduce un valor…"
                  className="bg-zinc-950 border border-zinc-800 rounded text-[11px] text-zinc-200 px-2 py-1.5 focus:outline-none focus:border-zinc-600"
                  data-testid="data-source-value-input" />
              </div>
              <button onClick={runSearch} disabled={!filterField || !filterValue || dataLoading}
                className="flex items-center gap-1.5 text-[11px] font-medium px-3 py-1.5 rounded bg-blue-500/15 border border-blue-500/30 text-blue-300 hover:bg-blue-500/25 transition-colors disabled:opacity-40"
                data-testid="data-source-search-btn">
                <Search className="w-3.5 h-3.5" /> Buscar
              </button>
              {applied && (
                <button onClick={clearSearch} className="text-[10px] text-zinc-500 hover:text-zinc-300 px-2 py-1.5 transition-colors" data-testid="data-source-clear-btn">
                  limpiar
                </button>
              )}
            </div>

            {applied && (
              <div className="text-[10px] text-zinc-500" data-testid="data-source-active-filter">
                Filtro activo: <span className="font-mono text-zinc-300">{applied.field}</span> ⊇ <span className="font-mono text-blue-300">"{applied.value}"</span>
              </div>
            )}

            {(() => {
              const items = data?.items || [];
              if (!dataLoading && items.length === 0) {
                return <p className="text-[11px] text-zinc-600" data-testid="data-source-empty">{applied ? 'Sin resultados para este filtro.' : 'Sin registros en esta colección todavía.'}</p>;
              }
              const columns = resolveColumns(items, src);
              return (
                <div className="overflow-x-auto" data-testid="data-source-table">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-zinc-800 hover:bg-transparent">
                        {columns.map(c => (
                          <TableHead key={c} className="text-[9px] uppercase tracking-wider text-zinc-500 whitespace-nowrap">{humanize(c, src.field_labels)}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {items.map((row, i) => (
                        <TableRow key={i} className="border-zinc-800/50" data-testid={`data-source-row-${i}`}>
                          {columns.map(c => (
                            <TableCell key={c} className="py-1.5 text-[11px] text-zinc-300 whitespace-nowrap max-w-[260px] truncate" title={fmtCell(row[c])}>{fmtCell(row[c])}</TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              );
            })()}

            {data && data.total_pages > 0 && (
              <div className="flex items-center justify-between pt-1 border-t border-zinc-800/50">
                <span className="text-[10px] text-zinc-500">Página <strong className="text-zinc-300">{data.current_page}</strong> de {fmtNum(data.total_pages)}</span>
                <div className="flex items-center gap-1.5">
                  <button onClick={() => setDataPage(p => Math.max(1, p - 1))} disabled={dataPage <= 1 || dataLoading}
                    className="flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-zinc-800/60 text-zinc-300 hover:bg-zinc-800 transition-colors disabled:opacity-40"
                    data-testid="data-source-prev-page"><ChevronLeft className="w-3 h-3" /> Anterior</button>
                  <button onClick={() => setDataPage(p => Math.min(data.total_pages, p + 1))} disabled={dataPage >= data.total_pages || dataLoading}
                    className="flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-zinc-800/60 text-zinc-300 hover:bg-zinc-800 transition-colors disabled:opacity-40"
                    data-testid="data-source-next-page">Siguiente <ChevronRight className="w-3 h-3" /></button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
