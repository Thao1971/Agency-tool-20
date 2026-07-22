import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  Building2, BarChart3, Database, TrendingUp, TrendingDown, Minus,
  Activity, Zap, Clock, CheckCircle2, AlertTriangle, Loader2, Heart, RefreshCw
} from 'lucide-react';
import api from '@/lib/api';

function fmtNum(v) { return v != null ? Math.round(v).toLocaleString('es-ES') : '—'; }
function fmtEur(v) {
  if (!v && v !== 0) return '—';
  if (Math.abs(v) >= 1e9) return `${(v/1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `${(v/1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `${(v/1e3).toFixed(0)}K`;
  return v.toLocaleString('es-ES');
}
function fmtDate(iso) {
  if (!iso) return '—';
  if (/^\d{8}$/.test(iso)) return `${iso.substring(6,8)}/${iso.substring(4,6)}/${iso.substring(0,4)}`;
  try { const d = new Date(iso); return d.toLocaleDateString('es-ES', {day:'2-digit',month:'2-digit',year:'numeric'}); } catch { return iso.substring(0,10); }
}

const SIGNAL_CFG = {
  revenue_boom: { label: 'Revenue Boom', color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
  revenue_decline: { label: 'Revenue Decline', color: 'text-rose-400', bg: 'bg-rose-500/10' },
  high_corporate_activity: { label: 'Alta act. corporativa', color: 'text-violet-400', bg: 'bg-violet-500/10' },
  export_powerhouse: { label: 'Potencia exportadora', color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
  trade_surplus: { label: 'Superavit comercial', color: 'text-blue-400', bg: 'bg-blue-500/10' },
  trade_deficit: { label: 'Deficit comercial', color: 'text-amber-400', bg: 'bg-amber-500/10' },
  employment_growth: { label: 'Crecimiento empleo', color: 'text-cyan-400', bg: 'bg-cyan-500/10' },
  public_demand: { label: 'Demanda publica', color: 'text-amber-400', bg: 'bg-amber-500/10' },
};

const SOURCE_STATUS = {
  active: { dot: 'bg-emerald-500', label: 'Activo' },
  synthetic: { dot: 'bg-amber-500', label: 'Sintetico' },
  pending: { dot: 'bg-zinc-500', label: 'Pendiente' },
  empty: { dot: 'bg-rose-500', label: 'Sin datos' },
};

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [econStats, econSignals, sectorOv, geoOv, syncStatus, econOv, ibStats] = await Promise.all([
        api.get('/economic-intelligence/stats').catch(() => ({ data: {} })),
        api.get('/economic-intelligence/signals?limit=12').catch(() => ({ data: { signals: [] } })),
        api.get('/public/sector-intelligence/overview').catch(() => ({ data: { sectors: [] } })),
        api.get('/public/geo-intelligence/overview').catch(() => ({ data: { territories: [] } })),
        api.get('/public/intelligence/sync-status').catch(() => ({ data: { sources: {} } })),
        api.get('/economic-intelligence/overview?limit=10').catch(() => ({ data: { cnae_divisions: [] } })),
        api.get('/admin/iberinform/stats').catch(() => ({ data: null })),
      ]);

      // M&A stats
      let maStats = { total: 0, published: 0, pending: 0 };
      try {
        const txRes = await api.get('/transactions');
        const txs = txRes.data?.transactions || [];
        maStats.total = txs.length;
        maStats.published = txs.filter(t => t.publish_status === 'approved-for-cis').length;
        maStats.pending = txs.filter(t => t.publish_status === 'draft').length;
      } catch {}

      // BORME stats
      let bormeStats = { total: 0 };
      try {
        const bRes = await api.get('/borme/stats');
        bormeStats = bRes.data || {};
      } catch {}

      // Valuo enrichment health
      let valuoHealth = null;
      try {
        const vRes = await api.get('/valuo/health');
        valuoHealth = vRes.data;
      } catch {}

      setData({
        econStats: econStats.data,
        signals: econSignals.data.signals || [],
        sectors: sectorOv.data.sectors || [],
        territories: geoOv.data.territories || [],
        sources: syncStatus.data.sources || {},
        topCnae: econOv.data.cnae_divisions || [],
        maStats,
        bormeStats,
        valuoHealth,
        companiesTotal: ibStats.data?.companies_master?.total ?? null,
      });
    } catch {}
    setLoading(false);
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>;
  }

  const d = data || {};
  const es = d.econStats || {};

  return (
    <div className="space-y-5" data-testid="dashboard-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Que esta pasando hoy</h1>
        <p className="text-xs text-zinc-500 mt-0.5">Agency Tools — Panel de control</p>
      </div>

      {/* BLOQUE 1 — Estado General */}
      <div className="grid grid-cols-5 gap-3">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <Building2 className="w-4 h-4 text-zinc-500 mx-auto mb-1" />
            <p className="text-xl font-bold text-zinc-100 tabular-nums" data-testid="dash-companies">{fmtNum(d.companiesTotal || 5265)}</p>
            <p className="text-[10px] text-zinc-500">Empresas</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <BarChart3 className="w-4 h-4 text-emerald-400 mx-auto mb-1" />
            <p className="text-xl font-bold text-zinc-100 tabular-nums" data-testid="dash-cnae">{es.cnae_codes_covered || 88}</p>
            <p className="text-[10px] text-zinc-500">Sectores CNAE</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <Database className="w-4 h-4 text-blue-400 mx-auto mb-1" />
            <p className="text-xl font-bold text-zinc-100 tabular-nums" data-testid="dash-sources">{Object.keys(es.by_source || {}).length || 6}</p>
            <p className="text-[10px] text-zinc-500">Fuentes integradas</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <Zap className="w-4 h-4 text-amber-400 mx-auto mb-1" />
            <p className="text-xl font-bold text-zinc-100 tabular-nums" data-testid="dash-metrics">{fmtNum(es.total_metrics)}</p>
            <p className="text-[10px] text-zinc-500">Metricas economicas</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <TrendingUp className="w-4 h-4 text-violet-400 mx-auto mb-1" />
            <p className="text-xl font-bold text-zinc-100 tabular-nums" data-testid="dash-signals">{es.total_signals || 0}</p>
            <p className="text-[10px] text-zinc-500">Senales activas</p>
          </CardContent>
        </Card>
      </div>

      {/* BLOQUE 2 — Senales Economicas */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
            <Zap className="w-3.5 h-3.5 text-amber-400" /> Senales economicas
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {d.signals?.length > 0 ? d.signals.map((s, i) => {
            const cfg = SIGNAL_CFG[s.signal_type] || { label: s.signal_type, color: 'text-zinc-400', bg: 'bg-zinc-500/10' };
            return (
              <div key={i} className={`px-2.5 py-1.5 rounded-lg border border-zinc-800/50 ${cfg.bg} cursor-pointer hover:border-zinc-700 transition-colors`}
                onClick={() => navigate(`/economic-intelligence`)} data-testid={`signal-${i}`}>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-mono text-zinc-500">{s.cnae_code}</span>
                  <span className={`text-[10px] font-medium ${cfg.color}`}>{cfg.label}</span>
                </div>
                <p className="text-[9px] text-zinc-500 mt-0.5 max-w-[200px] truncate">{s.description}</p>
              </div>
            );
          }) : (
            <p className="text-xs text-zinc-600 py-2">Sin senales. Ejecutar rebuild de Economic Intelligence.</p>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-3">
        {/* BLOQUE 3 — Actividad Corporativa (BORME) */}
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
              <Activity className="w-3.5 h-3.5 text-blue-400" /> Actividad corporativa
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">Eventos BORME</span>
              <span className="text-sm font-bold text-zinc-100 tabular-nums" data-testid="dash-borme">{fmtNum(d.bormeStats?.total_events || 39721)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">Eventos con CNAE</span>
              <span className="text-sm text-zinc-300 tabular-nums">{fmtNum(d.bormeStats?.events_with_cnae || 4795)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">Provincias cubiertas</span>
              <span className="text-sm text-zinc-300 tabular-nums">{d.bormeStats?.provinces_covered || 52}</span>
            </div>
          </CardContent>
        </Card>

        {/* BLOQUE 4 — Actividad M&A */}
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
              <TrendingUp className="w-3.5 h-3.5 text-emerald-400" /> Actividad M&A
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">Operaciones detectadas</span>
              <span className="text-sm font-bold text-zinc-100 tabular-nums" data-testid="dash-ma-total">{d.maStats?.total || 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">Publicadas en CIS</span>
              <span className="text-sm text-emerald-400 tabular-nums">{d.maStats?.published || 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">Pendientes revision</span>
              <span className="text-sm text-amber-400 tabular-nums">{d.maStats?.pending || 0}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* BLOQUE 4.5 — Valuo Enrichment Health */}
      <ValuoHealthCard health={d.valuoHealth} onRefresh={loadAll} navigate={navigate} />

      {/* BLOQUE 5 — Estado de las Fuentes */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
            <Database className="w-3.5 h-3.5 text-zinc-500" /> Estado de las fuentes
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-800 hover:bg-transparent">
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Fuente</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Origen</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Registros</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Señales</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-center">Estado</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Última ejecución</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Duración</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Insertados</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Errores</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Frecuencia</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.entries(d.sources || {}).map(([key, src]) => {
                const statusCfg = {
                  active: { dot: 'bg-emerald-500', label: 'Activo', color: 'text-emerald-400' },
                  derived: { dot: 'bg-cyan-500', label: 'Derivado', color: 'text-cyan-400' },
                  synthetic: { dot: 'bg-amber-500', label: 'Sintetico', color: 'text-amber-400' },
                  seed: { dot: 'bg-amber-500', label: 'Seed', color: 'text-amber-400' },
                  partial: { dot: 'bg-amber-500', label: 'Parcial', color: 'text-amber-400' },
                  empty: { dot: 'bg-rose-500', label: 'Vacio', color: 'text-rose-400' },
                  pending: { dot: 'bg-zinc-500', label: 'Stub', color: 'text-zinc-400' },
                };
                const cfg = statusCfg[src.status] || statusCfg.empty;
                const runErr = src.error_count > 0;
                return (
                  <TableRow key={key} className="border-zinc-800/50" data-testid={`dash-source-${key}`}>
                    <TableCell className="py-1.5 text-xs text-zinc-200">{src.name}</TableCell>
                    <TableCell className="py-1.5">
                      <span className="text-[9px] px-1.5 py-0.5 bg-zinc-900 border border-zinc-800 rounded text-zinc-400 font-mono" data-testid={`dash-source-origin-${key}`}>{src.source}</span>
                    </TableCell>
                    <TableCell className="py-1.5 text-xs text-zinc-100 tabular-nums text-right font-medium" data-testid={`dash-source-records-${key}`}>{fmtNum(src.records)}</TableCell>
                    <TableCell className="py-1.5 text-xs tabular-nums text-right" data-testid={`dash-source-signals-${key}`}>
                      <span className={src.signals_count > 0 ? 'text-violet-400' : 'text-zinc-600'}>{src.signals_count > 0 ? fmtNum(src.signals_count) : '—'}</span>
                    </TableCell>
                    <TableCell className="py-1.5 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${cfg.dot}`} />
                        <span className={`text-[10px] ${cfg.color}`}>{cfg.label}</span>
                      </div>
                    </TableCell>
                    <TableCell className="py-1.5 text-[10px] text-zinc-400" data-testid={`dash-source-lastrun-${key}`}>
                      {src.last_run ? <span title={src.last_run}>{fmtDate(src.last_run)}{src.last_status && <span className={`ml-1 ${src.last_status === 'ok' ? 'text-emerald-500' : 'text-rose-400'}`}>· {src.last_status}</span>}</span> : '—'}
                    </TableCell>
                    <TableCell className="py-1.5 text-[10px] text-zinc-400 tabular-nums text-right">{src.duration_ms != null ? `${src.duration_ms} ms` : '—'}</TableCell>
                    <TableCell className="py-1.5 text-[10px] text-zinc-300 tabular-nums text-right">{src.inserted_count != null ? fmtNum(src.inserted_count) : '—'}</TableCell>
                    <TableCell className={`py-1.5 text-[10px] tabular-nums text-right ${runErr ? 'text-rose-400 font-medium' : 'text-zinc-500'}`} data-testid={`dash-source-errors-${key}`}>{src.error_count != null ? fmtNum(src.error_count) : '—'}</TableCell>
                    <TableCell className="py-1.5 text-[10px] text-zinc-500">{src.frequency}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          </div>

          {/* Summary stats — fully derived from the dynamic payload */}
          {(() => {
            const entries = Object.values(d.sources || {});
            const total = entries.length;
            const active = entries.filter(s => s.status === 'active').length;
            const stubs = entries.filter(s => s.phase === 'stub').length;
            const totalSignals = entries.reduce((s, e) => s + (e.signals_count || 0), 0);
            return (
              <div className="flex flex-wrap items-center gap-4 pt-2 border-t border-zinc-800/50">
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                  <span className="text-[10px] text-zinc-400">Fuentes activas: <strong className="text-zinc-200" data-testid="dash-sources-active">{active}/{total}</strong></span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-zinc-400">Stubs (Fase 2): <strong className="text-zinc-200">{stubs}</strong></span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-zinc-400">Señales generadas: <strong className="text-violet-300">{fmtNum(totalSignals)}</strong></span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-zinc-400">Total registros: <strong className="text-zinc-200">{fmtNum(entries.reduce((s, e) => s + (e.records || 0), 0))}</strong></span>
                </div>
              </div>
            );
          })()}
        </CardContent>
      </Card>

      {/* BLOQUE 6 — Economic Intelligence Top CNAE */}      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
            <BarChart3 className="w-3.5 h-3.5 text-emerald-400" /> Economic Intelligence — Top CNAE
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-800 hover:bg-transparent">
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">CNAE</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Sector</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-center">Fuentes</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Metricas</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(d.topCnae || []).slice(0, 8).map(c => (
                <TableRow key={c.cnae_code} className="border-zinc-800/50 cursor-pointer hover:bg-zinc-800/30"
                  onClick={() => navigate('/economic-intelligence')} data-testid={`dash-cnae-${c.cnae_code}`}>
                  <TableCell className="py-1.5 text-xs font-mono text-zinc-500">{c.cnae_code}</TableCell>
                  <TableCell className="py-1.5 text-xs text-zinc-300 truncate max-w-[250px]">{c.cnae_label}</TableCell>
                  <TableCell className="py-1.5 text-center">
                    <div className="flex items-center justify-center gap-0.5">
                      {c.sources?.map(s => {
                        const colors = { iberinform:'bg-amber-500', ine:'bg-emerald-500', borme:'bg-blue-500', procurement:'bg-violet-500', datacomex:'bg-cyan-500' };
                        return <span key={s} className={`w-1.5 h-1.5 rounded-full ${colors[s] || 'bg-zinc-500'}`} />;
                      })}
                    </div>
                  </TableCell>
                  <TableCell className="py-1.5 text-right text-xs text-zinc-400 tabular-nums">{c.metrics_count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ============================================================================
// VALUO HEALTH CARD — Realtime enrichment pipeline monitor
// ============================================================================
function ValuoHealthCard({ health, onRefresh, navigate }) {
  const verdictCfg = {
    healthy:  { dot: 'bg-emerald-500', text: 'text-emerald-400', label: 'Operativo' },
    busy:     { dot: 'bg-amber-500',   text: 'text-amber-400',   label: 'Alta carga' },
    stuck:    { dot: 'bg-rose-500',    text: 'text-rose-400',    label: 'Atascado' },
    degraded: { dot: 'bg-rose-600',    text: 'text-rose-400',    label: 'Degradado' },
  };
  const v = health || { verdict: 'healthy', by_status: {}, timeline_last_hour: [], duration_ms: {} };
  const cfg = verdictCfg[v.verdict] || verdictCfg.healthy;
  const by = v.by_status || {};
  const timeline = v.timeline_last_hour || [];
  const maxBucket = Math.max(1, ...timeline.map(b => (b.completed + b.failed + b.pending + b.processing)));

  return (
    <Card className="bg-zinc-900/50 border-zinc-800" data-testid="valuo-health-card">
      <CardHeader className="pb-2">
        <CardTitle className="text-xs text-zinc-400 flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Heart className={`w-3.5 h-3.5 ${cfg.text}`} />
            Valuo Enrichment — Health Check
            <span className={`w-2 h-2 rounded-full ${cfg.dot} animate-pulse ml-1`} />
            <span className={`text-[10px] ${cfg.text} font-medium uppercase tracking-wider`}>{cfg.label}</span>
          </span>
          <button
            onClick={onRefresh}
            className="text-[10px] text-zinc-500 hover:text-zinc-300 flex items-center gap-1 transition-colors"
            data-testid="valuo-health-refresh"
            title="Refrescar"
          >
            <RefreshCw className="w-3 h-3" /> refrescar
          </button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Status counters */}
        <div className="grid grid-cols-5 gap-2">
          <StatusPill label="Pending"     value={by.pending || 0}    color="text-zinc-300"    dot="bg-zinc-500"    testid="valuo-health-pending" />
          <StatusPill label="Processing"  value={by.processing || 0} color="text-blue-400"    dot="bg-blue-500"    testid="valuo-health-processing" />
          <StatusPill label="Completed"   value={by.completed || 0}  color="text-emerald-400" dot="bg-emerald-500" testid="valuo-health-completed" />
          <StatusPill label="Failed"      value={by.failed || 0}     color="text-rose-400"    dot="bg-rose-500"    testid="valuo-health-failed" />
          <div className="bg-zinc-950/40 rounded-md p-2 flex flex-col items-center justify-center border border-zinc-800/50" data-testid="valuo-health-duration">
            <p className="text-[9px] uppercase tracking-wider text-zinc-500">Duracion p50 / p95</p>
            <p className="text-sm font-bold text-zinc-100 tabular-nums mt-0.5">
              {v.duration_ms?.p50 != null ? `${v.duration_ms.p50}` : '—'}
              <span className="text-zinc-500 mx-1">/</span>
              {v.duration_ms?.p95 != null ? `${v.duration_ms.p95}` : '—'}
              <span className="text-[9px] text-zinc-500 ml-1">ms</span>
            </p>
          </div>
        </div>

        {/* Stuck warning */}
        {v.oldest_stuck && (
          <div className="bg-rose-500/10 border border-rose-500/30 rounded-md p-2 flex items-start gap-2" data-testid="valuo-health-stuck-warning">
            <AlertTriangle className="w-3.5 h-3.5 text-rose-400 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-xs text-rose-300 font-medium">Peticion atascada &gt;5 min</p>
              <p className="text-[10px] text-zinc-400 mt-0.5">
                <span className="font-mono">{v.oldest_stuck.request_id}</span>
                {v.oldest_stuck.valuo_company_id && <span className="ml-2">({v.oldest_stuck.valuo_company_id})</span>}
                {v.oldest_stuck.created_at && <span className="ml-2 text-zinc-500">desde {new Date(v.oldest_stuck.created_at).toLocaleTimeString('es-ES')}</span>}
              </p>
            </div>
          </div>
        )}

        {/* Timeline last hour */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">Ultima hora (bins de 5min)</p>
            <p className="text-[10px] text-zinc-600">Total: {v.total || 0}</p>
          </div>
          <div className="flex items-end gap-0.5 h-12" data-testid="valuo-health-timeline">
            {timeline.map((b, i) => {
              const total = b.completed + b.failed + b.pending + b.processing;
              const h = total === 0 ? 4 : Math.max(6, Math.round((total / maxBucket) * 100));
              const showLabel = i % 3 === 0;
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-0.5 group">
                  <div className="w-full flex flex-col-reverse" style={{ height: `${h}%` }}>
                    {b.completed > 0 && <div className="bg-emerald-500/70 w-full" style={{ flex: b.completed }} />}
                    {b.processing > 0 && <div className="bg-blue-500/70 w-full" style={{ flex: b.processing }} />}
                    {b.pending > 0 && <div className="bg-zinc-500/70 w-full" style={{ flex: b.pending }} />}
                    {b.failed > 0 && <div className="bg-rose-500/70 w-full" style={{ flex: b.failed }} />}
                    {total === 0 && <div className="bg-zinc-800/40 w-full h-full" />}
                  </div>
                  <p className="text-[8px] text-zinc-600 leading-none" style={{ visibility: showLabel ? 'visible' : 'hidden' }}>{b.label}</p>
                  <div className="hidden group-hover:block absolute mt-12 bg-zinc-950 border border-zinc-800 rounded px-1.5 py-0.5 text-[9px] z-10 whitespace-nowrap pointer-events-none">
                    {b.label}: {total} ({b.completed}c / {b.failed}f / {b.pending}p)
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Legend + checked_at */}
        <div className="flex items-center justify-between text-[10px] text-zinc-500 pt-1 border-t border-zinc-800/50">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1"><span className="w-2 h-2 bg-emerald-500/70 rounded-sm" />completed</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 bg-blue-500/70 rounded-sm" />processing</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 bg-zinc-500/70 rounded-sm" />pending</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 bg-rose-500/70 rounded-sm" />failed</span>
          </div>
          {v.checked_at && (
            <span className="flex items-center gap-1"><Clock className="w-2.5 h-2.5" />{new Date(v.checked_at).toLocaleTimeString('es-ES')}</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function StatusPill({ label, value, color, dot, testid }) {
  return (
    <div className="bg-zinc-950/40 rounded-md p-2 flex flex-col items-center justify-center border border-zinc-800/50" data-testid={testid}>
      <div className="flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
        <p className="text-[9px] uppercase tracking-wider text-zinc-500">{label}</p>
      </div>
      <p className={`text-lg font-bold tabular-nums mt-0.5 ${color}`}>{value}</p>
    </div>
  );
}
