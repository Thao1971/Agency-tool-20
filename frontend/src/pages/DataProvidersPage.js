import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Database, RefreshCw, Download, Loader2, CheckCircle, AlertTriangle,
  FileSpreadsheet, BarChart3, Globe, Upload, Search, Layers, Clock,
  TrendingUp, Shield, ChevronLeft, ChevronRight
} from 'lucide-react';
import { toast } from 'sonner';

function fmtDate(iso) {
  if (!iso) return '—';
  const s = String(iso);
  // Handle YYYYMMDD format (BORME)
  if (/^\d{8}$/.test(s)) return `${s.substring(6, 8)}/${s.substring(4, 6)}/${s.substring(0, 4)}`;
  // Handle ISO YYYY-MM-DD...
  const [y, m, d] = s.substring(0, 10).split('-');
  return d && m && y ? `${d}/${m}/${y}` : s.substring(0, 10);
}
function fmtSize(b) { if (!b) return '—'; if (b < 1024) return `${b} B`; if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`; return `${(b / 1048576).toFixed(1)} MB`; }

// Spanish label translations for all technical terms
const L = {
  // Status
  healthy: 'Operativo', ok: 'Operativo', warning: 'Atencion', error: 'Error', inactive: 'Inactivo',
  active: 'Activo', disabled: 'Desactivado', excluded: 'Excluido', pending: 'Pendiente',
  idle: 'En espera', running: 'Procesando', completed: 'Completado', failed: 'Fallido',
  // Metrics
  index: 'Indice', yoy_change: 'Var. anual', mom_change: 'Var. mensual', ytd_change: 'Var. acumulada',
  revenue: 'Facturacion', ebitda: 'EBITDA', employees: 'Empleados', margin: 'Margen',
  productivity: 'Productividad', price_index: 'Indice precios', company_count: 'Num. empresas',
  by_size: 'Por tamano', by_territory: 'Por territorio',
  ma_events: 'Operaciones M&A', constitutions: 'Constituciones', appointments: 'Nombramientos',
  growth_metrics: 'Metricas crecimiento', market_context_api: 'Contexto mercado',
  market_snapshots: 'Snapshots mercado', activity_index: 'Indice actividad',
  // Visibility
  visible: 'Visible', oculto: 'Oculto',
};
const t = (key) => L[key] || key;

const SB = (s) => s === 'healthy' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : s === 'warning' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' : s === 'error' ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' : 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20';
const SD = (s) => s === 'healthy' ? 'bg-emerald-500' : s === 'warning' ? 'bg-amber-500' : s === 'error' ? 'bg-rose-500' : 'bg-zinc-500';
const DS = { active: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20', registered: 'bg-blue-500/10 text-blue-400 border-blue-500/20', pending: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20' };
const REASONS = { wrong_company_match: 'Empresa incorrecta', duplicate: 'Duplicado', irrelevant: 'Irrelevante', outdated: 'Obsoleto', low_confidence: 'Baja confianza', outside_scope: 'Fuera de scope', incorrect_source: 'Fuente incorrecta', manual_quality_control: 'Control calidad', other: 'Otro', manual_restore: 'Restaurado' };
const REASON_CODES = ['wrong_company_match', 'duplicate', 'irrelevant', 'outdated', 'low_confidence', 'outside_scope', 'incorrect_source', 'manual_quality_control', 'other'];

export default function DataProvidersPage() {
  const [params, setParams] = useSearchParams();
  const view = params.get('view') || 'overview';
  const setView = (v) => setParams({ view: v });

  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/data-providers/health').then(r => setHealth(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const isProvider = ['borme', 'ine', 'iberinform'].includes(view);
  const providerName = view === 'borme' ? 'BORME' : view === 'ine' ? 'INE' : view === 'iberinform' ? 'Iberinform' : '';

  // Get last update timestamp
  const lastUpdate = health?.providers?.reduce((latest, p) => {
    const d = p.last_success_at;
    return d && d > (latest || '') ? d : latest;
  }, null);

  return (
    <div className="space-y-4" data-testid="data-providers-page">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {isProvider && <Button variant="ghost" size="sm" onClick={() => setView('overview')} className="text-zinc-400 h-7"><ChevronLeft className="w-4 h-4" /></Button>}
          <div>
            <h1 className="text-xl font-bold tracking-tight text-zinc-50 font-heading">
              {isProvider ? providerName : view === 'governance' ? 'Governance Overview' : 'Data Providers Overview'}
            </h1>
            <p className="text-xs text-zinc-400">
              {isProvider ? `Detalle del proveedor ${providerName}` : view === 'governance' ? 'Control de calidad, exclusiones, conflictos y publicacion transversal' : 'Estado general de proveedores externos y pipeline de datos'}
            </p>
          </div>
        </div>
        {!isProvider && view !== 'governance' && lastUpdate && (
          <div className="flex items-center gap-1.5 text-[11px] text-zinc-500">
            <Clock className="w-3.5 h-3.5" />Ultima actualizacion: {fmtDate(lastUpdate)}
          </div>
        )}
      </div>

      {/* Top navigation — Overview */}
      {!isProvider && view !== 'governance' && (
        <>
          {/* Summary bar */}
          {health && (
            <div className="flex items-center gap-6 text-[11px] text-zinc-400 px-4 py-2.5 rounded bg-zinc-900 border border-zinc-800">
              {health.providers?.map(p => (
                <span key={p.provider} className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${SD(p.status)}`} />
                  <span className="text-zinc-300 font-medium">{p.name}</span>
                  <span className="text-zinc-500">{p.records_total?.toLocaleString()}</span>
                </span>
              ))}
            </div>
          )}

          {/* Provider cards — large format matching mockup */}
          {loading ? <Loader2 className="w-5 h-5 animate-spin text-zinc-400 mx-auto mt-8" /> : (
            <div className="space-y-3">
              {health?.providers?.map(p => {
                const dotColor = p.provider === 'borme' ? 'bg-emerald-500' : p.provider === 'ine' ? 'bg-zinc-400' : 'bg-amber-500';
                return (
                  <Card key={p.provider} className="bg-zinc-900 border-zinc-800 cursor-pointer hover:border-zinc-700 transition-colors" onClick={() => setView(p.provider)}>
                    <CardContent className="p-5">
                      <div className="flex items-start">
                        {/* Left: dot + name + data */}
                        <div className="flex-1">
                          <div className="flex items-center gap-2.5 mb-4">
                            <span className={`w-3.5 h-3.5 rounded-full ${dotColor}`} />
                            <span className="text-lg font-bold text-zinc-100">{p.name}</span>
                          </div>
                          <div className="grid grid-cols-2 gap-x-16 gap-y-1.5 text-[12px]">
                            <div><span className="text-zinc-500">Registros: </span><span className="text-zinc-200 font-semibold">{p.records_total?.toLocaleString()}</span></div>
                            <div><span className="text-zinc-500">En Valuo: </span><span className="text-emerald-400 font-semibold">{p.records_visible_in_valuo?.toLocaleString()}</span></div>
                            <div><span className="text-zinc-500">Excluidos: </span><span className="text-zinc-300">{p.records_excluded}</span></div>
                            <div><span className="text-zinc-500">Pendientes: </span><span className={p.pending_review > 0 ? 'text-amber-400 font-semibold' : 'text-zinc-300'}>{p.pending_review}</span></div>
                            <div><span className="text-zinc-500">Estado: </span><span className="text-zinc-300">{t(p.sync_status)}</span></div>
                            <div><span className="text-zinc-500">Ultima sincronizacion: </span><span className="text-zinc-300 font-semibold">{fmtDate(p.last_success_at)}</span></div>
                          </div>
                        </div>
                        {/* Right: badge + chevron */}
                        <div className="flex items-center gap-3 pt-1">
                          <Badge className={`text-[10px] border px-2.5 py-0.5 ${SB(p.status)}`}>{t(p.status)}</Badge>
                          <div className="w-8 h-8 rounded-full border border-zinc-700 flex items-center justify-center text-zinc-500 hover:text-zinc-300 hover:border-zinc-500 transition-colors">
                            <ChevronRight className="w-4 h-4" />
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}

              {/* Governance card */}
              <Card className="bg-zinc-900 border-zinc-800 cursor-pointer hover:border-zinc-700 transition-colors" onClick={() => setView('governance')}>
                <CardContent className="p-5">
                  <div className="flex items-center">
                    <Shield className="w-5 h-5 text-zinc-500 mr-3" />
                    <div className="flex-1">
                      <p className="text-sm font-bold text-zinc-200">Governance Overview</p>
                      <p className="text-[11px] text-zinc-500">Control de calidad, exclusiones, conflictos y publicacion transversal</p>
                    </div>
                    <div className="flex items-center gap-3">
                      {health?.providers?.reduce((a, p) => a + p.pending_review, 0) > 0 && (
                        <Badge className="text-[10px] border bg-amber-500/10 text-amber-400 border-amber-500/20 px-2.5 py-0.5">
                          {health.providers.reduce((a, p) => a + p.pending_review, 0)} pendientes
                        </Badge>
                      )}
                      <div className="w-8 h-8 rounded-full border border-zinc-700 flex items-center justify-center text-zinc-500">
                        <ChevronRight className="w-4 h-4" />
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </>
      )}

      {/* Provider detail views */}
      {view === 'borme' && <BormeProvider />}
      {view === 'ine' && <INEProvider />}
      {view === 'iberinform' && <IberinformProvider />}
      {view === 'governance' && <GovernanceOverview health={health} onBack={() => setView('overview')} />}
    </div>
  );
}

// ═══════════════════════════════════════════
// BORME PROVIDER
// ═══════════════════════════════════════════
function BormeProvider() {
  const [tab, setTab] = useState('overview');
  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList className="bg-zinc-900 border border-zinc-800 p-1 flex-wrap h-auto gap-0.5">
        <TabsTrigger value="overview" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]">Overview</TabsTrigger>
        <TabsTrigger value="exclusions" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><AlertTriangle className="w-3 h-3 mr-1" />Exclusiones</TabsTrigger>
        <TabsTrigger value="records" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]">Registros</TabsTrigger>
      </TabsList>
      <TabsContent value="overview"><ProviderStatus provider="borme" /></TabsContent>
      <TabsContent value="exclusions"><ExclusionsPanel provider="borme" /></TabsContent>
      <TabsContent value="records"><RecordsPanel provider="borme" /></TabsContent>
    </Tabs>
  );
}

// ═══════════════════════════════════════════
// INE PROVIDER
// ═══════════════════════════════════════════
function INEProvider() {
  const [tab, setTab] = useState('overview');
  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList className="bg-zinc-900 border border-zinc-800 p-1 flex-wrap h-auto gap-0.5">
        <TabsTrigger value="overview" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]">Overview</TabsTrigger>
        <TabsTrigger value="datasets" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><Layers className="w-3 h-3 mr-1" />Datasets</TabsTrigger>
        <TabsTrigger value="cnaes" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]">CNAEs</TabsTrigger>
        <TabsTrigger value="tables" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><FileSpreadsheet className="w-3 h-3 mr-1" />Tables</TabsTrigger>
        <TabsTrigger value="coverage" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><BarChart3 className="w-3 h-3 mr-1" />Coverage</TabsTrigger>
        <TabsTrigger value="context" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><Globe className="w-3 h-3 mr-1" />Market Context</TabsTrigger>
        <TabsTrigger value="exclusions" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><AlertTriangle className="w-3 h-3 mr-1" />Exclusiones</TabsTrigger>
      </TabsList>
      <TabsContent value="overview"><ProviderStatus provider="ine" /></TabsContent>
      <TabsContent value="datasets"><INEDatasets /></TabsContent>
      <TabsContent value="cnaes"><INECNAEs /></TabsContent>
      <TabsContent value="tables"><INETables /></TabsContent>
      <TabsContent value="coverage"><INECoverage /></TabsContent>
      <TabsContent value="context"><INEMarketContext /></TabsContent>
      <TabsContent value="exclusions"><ExclusionsPanel provider="ine" /></TabsContent>
    </Tabs>
  );
}

// ═══════════════════════════════════════════
// IBERINFORM PROVIDER
// ═══════════════════════════════════════════
function IberinformProvider() {
  const [tab, setTab] = useState('overview');
  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList className="bg-zinc-900 border border-zinc-800 p-1 flex-wrap h-auto gap-0.5">
        <TabsTrigger value="overview" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]">Overview</TabsTrigger>
        <TabsTrigger value="files" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><Upload className="w-3 h-3 mr-1" />Files</TabsTrigger>
        <TabsTrigger value="exclusions" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><AlertTriangle className="w-3 h-3 mr-1" />Exclusiones</TabsTrigger>
      </TabsList>
      <TabsContent value="overview"><ProviderStatus provider="iberinform" /></TabsContent>
      <TabsContent value="files"><IberinformFiles /></TabsContent>
      <TabsContent value="exclusions"><ExclusionsPanel provider="iberinform" /></TabsContent>
    </Tabs>
  );
}

// ═══════════════════════════════════════════
// SHARED: Provider Status
// ═══════════════════════════════════════════
function ProviderStatus({ provider }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    api.get('/data-providers/health').then(r => {
      const p = r.data.providers?.find(x => x.provider === provider);
      setData(p);
    }).catch(() => {});
  }, [provider]);
  if (!data) return <Loader2 className="w-4 h-4 animate-spin text-zinc-400 mx-auto mt-4" />;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {[
        ['Registros', data.records_total?.toLocaleString(), 'text-zinc-100'],
        ['En Valuo', data.records_visible_in_valuo?.toLocaleString(), 'text-emerald-400'],
        ['Excluidos', data.records_excluded, data.records_excluded > 0 ? 'text-rose-400' : 'text-zinc-500'],
        ['Pendientes', data.pending_review, data.pending_review > 0 ? 'text-amber-400' : 'text-zinc-500'],
        ['Estado', t(data.status), ''],
        ['Sincronizacion', t(data.sync_status), 'text-zinc-300'],
        ['Ultima sincronizacion', fmtDate(data.last_success_at), 'text-zinc-300'],
        ['Ultimo error', data.last_error_message ? 'Error de conexion' : 'Ninguno', data.last_error_message ? 'text-rose-400' : 'text-zinc-500'],
      ].map(([l, v, c]) => (
        <Card key={l} className="bg-zinc-900 border-zinc-800"><CardContent className="p-3">
          <p className="text-[8px] uppercase text-zinc-500">{l}</p>
          <p className={`text-lg font-bold font-mono ${c}`}>{v}</p>
        </CardContent></Card>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════
// SHARED: Exclusions Panel (per provider)
// ═══════════════════════════════════════════
function ExclusionsPanel({ provider }) {
  const [exclusions, setExclusions] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    try { const r = await api.get(`/data-providers/${provider}/exclusions`); setExclusions(r.data.exclusions || []); setTotal(r.data.total || 0); } catch (_) {}
    finally { setLoading(false); }
  }, [provider]);
  useEffect(() => { fetch(); }, [fetch]);

  return (
    <div className="space-y-3">
      <span className="text-[10px] text-zinc-500">{total} registros de exclusion</span>
      {loading ? <Loader2 className="w-4 h-4 animate-spin text-zinc-400 mx-auto mt-4" /> : (
        <div className="rounded border border-zinc-800 overflow-hidden">
          <Table><TableHeader><TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900">
            <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-20">Accion</TableHead>
            <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5">Record</TableHead>
            <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-28">Motivo</TableHead>
            <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5">Detalle</TableHead>
            <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-24">Fecha</TableHead>
            <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-24">Usuario</TableHead>
            <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16"></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {exclusions.length === 0 && <TableRow><TableCell colSpan={7} className="text-center text-zinc-500 py-6 text-xs">Sin exclusiones</TableCell></TableRow>}
            {exclusions.map((e, i) => (
              <TableRow key={e.exclusion_id || i} className="border-zinc-800">
                <TableCell className="py-1"><Badge className={`text-[7px] border ${e.action === 'exclude' ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' : e.action === 'restore' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-blue-500/10 text-blue-400 border-blue-500/20'}`}>{e.action}</Badge></TableCell>
                <TableCell className="py-1 text-[9px] font-mono text-zinc-400 truncate max-w-[100px]">{e.source_record_id}</TableCell>
                <TableCell className="py-1 text-[9px] text-zinc-300">{REASONS[e.reason_code] || e.reason_code}</TableCell>
                <TableCell className="py-1 text-[9px] text-zinc-500 truncate max-w-[140px]">{e.reason_text || e.related_company_name || '—'}</TableCell>
                <TableCell className="py-1 text-[9px] text-zinc-500">{fmtDate(e.created_at)}</TableCell>
                <TableCell className="py-1 text-[9px] text-zinc-500 truncate">{e.created_by}</TableCell>
                <TableCell className="py-1">{e.action === 'exclude' && (
                  <Button size="sm" variant="ghost" className="h-5 text-[8px] text-emerald-400" disabled={restoring === e.source_record_id}
                    onClick={async () => { setRestoring(e.source_record_id); try { await api.post(`/data-providers/${provider}/records/${e.source_record_id}/restore`); toast.success('Restaurado'); fetch(); } catch (_) { toast.error('Error'); } finally { setRestoring(null); } }}>
                    <RefreshCw className="w-3 h-3" />
                  </Button>
                )}</TableCell>
              </TableRow>
            ))}
          </TableBody></Table>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// SHARED: Records Panel (per provider)
// ═══════════════════════════════════════════
function RecordsPanel({ provider }) {
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [excluding, setExcluding] = useState(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    try { const r = await api.get(`/data-providers/${provider}/records`, { params: { search: search || undefined, limit: 50 } }); setRecords(r.data.records || []); setTotal(r.data.total || 0); } catch (_) {}
    finally { setLoading(false); }
  }, [provider, search]);
  useEffect(() => { fetch(); }, [fetch]);

  const handleExclude = async (recordId) => {
    const reason = prompt('Motivo de exclusion (wrong_company_match, duplicate, irrelevant, outside_scope, other):');
    if (!reason) return;
    setExcluding(recordId);
    try { await api.post(`/data-providers/${provider}/records/${recordId}/exclude`, { reason_code: REASON_CODES.includes(reason) ? reason : 'other', reason_text: REASON_CODES.includes(reason) ? null : reason }); toast.success('Excluido'); fetch(); } catch (e) { toast.error(e.response?.data?.detail || 'Error'); }
    finally { setExcluding(null); }
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2"><Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar..." className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs flex-1" /><span className="text-[10px] text-zinc-500 self-center">{total}</span></div>
      {loading ? <Loader2 className="w-4 h-4 animate-spin text-zinc-400 mx-auto mt-4" /> : (
        <div className="rounded border border-zinc-800 overflow-hidden">
          <Table><TableHeader><TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900">
            <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5">ID</TableHead>
            <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-20">Visibilidad</TableHead>
            <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Accion</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {records.map(r => (
              <TableRow key={r._record_id} className="border-zinc-800">
                <TableCell className="py-1 text-[10px] font-mono text-zinc-300">{r._record_id?.substring(0, 24)}</TableCell>
                <TableCell className="py-1"><Badge className={`text-[7px] border ${r.valuo_visibility_status === 'visible' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border-rose-500/20'}`}>{r.valuo_visibility_status}</Badge></TableCell>
                <TableCell className="py-1">{r.valuo_visibility_status === 'visible' ? (
                  <Button size="sm" variant="ghost" className="h-5 text-[8px] text-rose-400" disabled={excluding === r._record_id} onClick={() => handleExclude(r._record_id)}>Excluir</Button>
                ) : (
                  <Button size="sm" variant="ghost" className="h-5 text-[8px] text-emerald-400" onClick={async () => { await api.post(`/data-providers/${provider}/records/${r._record_id}/restore`); toast.success('Restaurado'); fetch(); }}>Restaurar</Button>
                )}</TableCell>
              </TableRow>
            ))}
          </TableBody></Table>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// GOVERNANCE OVERVIEW
// ═══════════════════════════════════════════
function GovernanceOverview({ health, onBack }) {
  const providers = health?.providers || [];
  const totalExcluded = providers.reduce((a, p) => a + p.records_excluded, 0);
  const totalPending = providers.reduce((a, p) => a + p.pending_review, 0);
  const totalRecords = providers.reduce((a, p) => a + p.records_total, 0);
  const totalInValuo = providers.reduce((a, p) => a + p.records_visible_in_valuo, 0);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        {[['Total registros', totalRecords.toLocaleString(), 'text-zinc-100'], ['En Valuo', totalInValuo.toLocaleString(), 'text-emerald-400'], ['Excluidos', totalExcluded, totalExcluded > 0 ? 'text-rose-400' : 'text-zinc-500'], ['Pendientes review', totalPending, totalPending > 0 ? 'text-amber-400' : 'text-zinc-500']].map(([l, v, c]) => (
          <Card key={l} className="bg-zinc-900 border-zinc-800"><CardContent className="p-3"><p className="text-[8px] uppercase text-zinc-500">{l}</p><p className={`text-xl font-bold font-mono ${c}`}>{v}</p></CardContent></Card>
        ))}
      </div>
      <Card className="bg-zinc-900 border-zinc-800"><CardContent className="p-4">
        <p className="text-[9px] uppercase text-zinc-500 font-semibold mb-3">Estado por provider</p>
        <div className="space-y-2">
          {providers.map(p => (
            <div key={p.provider} className="flex items-center gap-3 text-[10px] py-1 border-b border-zinc-800/30">
              <span className={`w-2 h-2 rounded-full ${SD(p.status)}`} />
              <span className="text-zinc-200 font-medium w-20">{p.name}</span>
              <span className="text-zinc-400">registros: {p.records_total?.toLocaleString()}</span>
              <span className="text-emerald-400">valuo: {p.records_visible_in_valuo?.toLocaleString()}</span>
              <span className={p.records_excluded > 0 ? 'text-rose-400' : 'text-zinc-600'}>excluidos: {p.records_excluded}</span>
              <span className={p.pending_review > 0 ? 'text-amber-400' : 'text-zinc-600'}>pending: {p.pending_review}</span>
              <Badge className={`text-[7px] border ml-auto ${SB(p.status)}`}>{p.status}</Badge>
            </div>
          ))}
        </div>
      </CardContent></Card>
    </div>
  );
}

// ═══════════════════════════════════════════
// INE SUB-COMPONENTS (preserved from previous)
// ═══════════════════════════════════════════
function INEDatasets() {
  const [datasets, setDatasets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(null);

  const fetch = useCallback(async () => {
    try { const r = await api.get('/registry/datasets?include_disabled=true'); setDatasets(r.data.datasets || []); } catch (_) {}
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetch(); }, [fetch]);

  const toggle = async (id, enabled) => {
    setToggling(id);
    try {
      await api.post(`/registry/datasets/${id}/${enabled ? 'disable' : 'activate'}`);
      toast.success(enabled ? 'Dataset desactivado' : 'Dataset activado');
      fetch();
    } catch (_) { toast.error('Error'); }
    finally { setToggling(null); }
  };

  if (loading) return <Loader2 className="w-5 h-5 animate-spin text-zinc-400 mx-auto mt-8" />;
  return (<div className="space-y-3"><p className="text-[10px] text-zinc-500">Fuentes de datos gobernadas desde el registro. {datasets.length} fuentes.</p>{datasets.map(ds => (<Card key={ds.dataset_id} className={`bg-zinc-900 border-zinc-800 ${!ds.enabled ? 'opacity-50' : ''}`}><CardContent className="p-4"><div className="flex items-center gap-2 mb-1"><span className={`w-2 h-2 rounded-full ${ds.enabled ? 'bg-emerald-500' : 'bg-zinc-600'}`} /><span className="text-sm font-medium text-zinc-100">{ds.name}</span><Badge className={`text-[8px] border ${DS[ds.status] || DS.pending}`}>{t(ds.status)}</Badge><div className="ml-auto flex gap-2"><Badge variant="outline" className="text-[7px] text-zinc-500 border-zinc-700">{ds.provider}</Badge><Button size="sm" variant="ghost" className={`h-5 text-[8px] ${ds.enabled ? 'text-rose-400' : 'text-emerald-400'}`} disabled={toggling === ds.dataset_id} onClick={() => toggle(ds.dataset_id, ds.enabled)}>{ds.enabled ? 'Desactivar' : 'Activar'}</Button></div></div><p className="text-[10px] text-zinc-400 mb-1">{ds.description}</p><div className="flex items-center gap-4 text-[10px] text-zinc-500"><span>Valuo: <span className={ds.visible_in_valuo ? 'text-emerald-400' : 'text-zinc-600'}>{ds.visible_in_valuo ? 'Visible' : 'Oculto'}</span></span><span>Sincronizacion: {fmtDate(ds.last_sync_at)}</span><div className="flex gap-1 ml-auto">{(ds.supported_metrics || []).map(m => <Badge key={typeof m === 'string' ? m : m?.key || Math.random()} variant="outline" className="text-[7px] text-zinc-400 border-zinc-700">{t(typeof m === 'string' ? m : m?.name || '?')}</Badge>)}</div></div></CardContent></Card>))}</div>);
}

function INECNAEs() {
  const [cnaes, setCnaes] = useState([]); const [search, setSearch] = useState(''); const [loading, setLoading] = useState(true); const [al, setAl] = useState(null);
  const fetch = useCallback(async () => { setLoading(true); try { const r = await api.get(`/data-providers/ine/cnae-search?q=${search}`); setCnaes(r.data.cnaes || []); } catch (_) {} finally { setLoading(false); } }, [search]);
  useEffect(() => { fetch(); }, [fetch]);
  return (<div className="space-y-3"><div className="flex gap-2"><Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar CNAE..." className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs flex-1" /><span className="text-[10px] text-zinc-500 self-center">{cnaes.length}</span></div>{loading ? <Loader2 className="w-4 h-4 animate-spin text-zinc-400 mx-auto mt-4" /> : (<div className="rounded border border-zinc-800 overflow-hidden"><Table><TableHeader><TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900"><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Codigo</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5">Nombre</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Estado</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Obs</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-20">Accion</TableHead></TableRow></TableHeader><TableBody>{cnaes.map(c => (<TableRow key={c.cnae_code} className="border-zinc-800"><TableCell className="py-1 text-xs font-mono text-zinc-200">{c.cnae_code}</TableCell><TableCell className="py-1 text-xs text-zinc-300">{c.cnae_label||'—'}</TableCell><TableCell className="py-1">{c.active ? <Badge className="text-[7px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Activo</Badge> : <span className="text-zinc-600 text-[10px]">—</span>}</TableCell><TableCell className="py-1 text-[10px] font-mono text-zinc-300">{c.observations}</TableCell><TableCell className="py-1"><Button size="sm" variant="ghost" className={`h-5 text-[8px] ${c.active?'text-rose-400':'text-emerald-400'}`} disabled={al===c.cnae_code} onClick={async()=>{setAl(c.cnae_code);try{await api.post('/data-providers/ine/cnae-scope',{cnae_code:c.cnae_code,cnae_name:c.cnae_label||'',priority:c.active?'disabled':'high'});toast.success(c.active?'Desactivado':'Activado');fetch();}catch(_){toast.error('Error');}finally{setAl(null);}}}>{c.active?'Desactivar':'Activar'}</Button></TableCell></TableRow>))}</TableBody></Table></div>)}</div>);
}

function INETables() {
  const [opId, setOpId] = useState('31'); const [tables, setTables] = useState([]); const [loading, setLoading] = useState(false); const [syncing, setSyncing] = useState(null);
  const fetchT = async () => { setLoading(true); try { const r = await api.get(`/data-providers/ine/tables?operation_id=${opId}`); setTables(r.data.tables || []); } catch (_) {} finally { setLoading(false); } };
  useEffect(() => { fetchT(); }, [opId]);
  return (<div className="space-y-3"><div className="flex gap-2 items-center"><Select value={opId} onValueChange={setOpId}><SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-8 w-80 text-xs"><SelectValue /></SelectTrigger><SelectContent className="bg-zinc-900 border-zinc-700"><SelectItem value="31">IASS</SelectItem><SelectItem value="130">Estructural</SelectItem><SelectItem value="14">Precios</SelectItem><SelectItem value="250">Produccion</SelectItem></SelectContent></Select><Button size="sm" onClick={fetchT} variant="outline" className="border-zinc-700 text-zinc-300 h-8"><RefreshCw className="w-3 h-3" /></Button></div>{loading ? <Loader2 className="w-4 h-4 animate-spin text-zinc-400 mx-auto mt-4" /> : (<div className="rounded border border-zinc-800 overflow-hidden"><Table><TableHeader><TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900"><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">ID</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5">Nombre</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-20">Estado</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-20">Accion</TableHead></TableRow></TableHeader><TableBody>{tables.map(t => (<TableRow key={t.table_id} className="border-zinc-800"><TableCell className="py-1 text-[10px] font-mono text-zinc-400">{t.table_id}</TableCell><TableCell className="py-1 text-xs text-zinc-200 truncate max-w-[300px]">{t.name}</TableCell><TableCell className="py-1">{t.registered ? <Badge className="text-[7px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Reg</Badge> : <span className="text-zinc-600 text-[10px]">—</span>}</TableCell><TableCell className="py-1"><Button size="sm" variant="ghost" className="h-5 text-[9px] text-blue-400" disabled={syncing===t.table_id} onClick={async()=>{setSyncing(t.table_id);try{await api.post('/data-providers/ine/tables/register',{table_id:t.table_id,dataset_type:opId==='31'?'iass':'other'});const r=await api.post(`/data-providers/ine/tables/${t.table_id}/sync?nult=10`);toast.success(`${r.data.inserted} obs`);fetchT();}catch(_){toast.error('Error');}finally{setSyncing(null);}}}>{syncing===t.table_id?<Loader2 className="w-3 h-3 animate-spin" />:<RefreshCw className="w-3 h-3 mr-0.5" />}Sync</Button></TableCell></TableRow>))}</TableBody></Table></div>)}</div>);
}

function INECoverage() {
  const [coverage, setCoverage] = useState([]); const [loading, setLoading] = useState(true);
  useEffect(() => { api.get('/data-providers/ine/coverage').then(r => setCoverage(r.data.coverage || [])).catch(() => {}).finally(() => setLoading(false)); }, []);
  if (loading) return <Loader2 className="w-4 h-4 animate-spin text-zinc-400 mx-auto mt-4" />;
  return (<div className="space-y-3"><p className="text-[10px] text-zinc-500">{coverage.length} combinaciones dataset/metrica/CNAE.</p><div className="rounded border border-zinc-800 overflow-hidden"><Table><TableHeader><TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900"><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Dataset</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Metrica</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-12">CNAE</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5">Sector</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Periods</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Rango</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Ultimo</TableHead></TableRow></TableHeader><TableBody>{coverage.map((c,i) => (<TableRow key={i} className="border-zinc-800"><TableCell className="py-1"><Badge variant="outline" className="text-[7px] text-zinc-400 border-zinc-700">{c.dataset}</Badge></TableCell><TableCell className="py-1"><Badge variant="outline" className="text-[7px] text-blue-400 border-blue-500/20">{c.metric||'?'}</Badge></TableCell><TableCell className="py-1 text-[10px] font-mono text-zinc-200">{c.cnae_code}</TableCell><TableCell className="py-1 text-[10px] text-zinc-300">{c.cnae_label||'—'}</TableCell><TableCell className="py-1 text-[10px] font-mono text-zinc-400">{c.periods}</TableCell><TableCell className="py-1 text-[10px] font-mono text-zinc-400">{c.year_range}</TableCell><TableCell className="py-1 text-[10px] font-mono text-zinc-200">{c.last_value}</TableCell></TableRow>))}</TableBody></Table></div></div>);
}

function INEMarketContext() {
  const [cnae, setCnae] = useState('73'); const [ctx, setCtx] = useState(null); const [loading, setLoading] = useState(false);
  const fetch = async () => { setLoading(true); try { const r = await api.get(`/data-providers/ine/market-context?cnae_code=${cnae}`); setCtx(r.data.context); } catch (_) {} finally { setLoading(false); } };
  useEffect(() => { fetch(); }, [cnae]);
  return (<div className="space-y-3"><div className="flex gap-2 items-center"><Input value={cnae} onChange={e => setCnae(e.target.value)} placeholder="CNAE" className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs w-40" /><Button size="sm" onClick={fetch} className="bg-zinc-800 text-zinc-300 h-8"><Search className="w-3 h-3 mr-1" />Ver</Button><p className="text-[10px] text-zinc-500 ml-2">Preview payload Valuo</p></div>{loading && <Loader2 className="w-4 h-4 animate-spin text-zinc-400 mx-auto mt-4" />}{ctx && !loading && (<Card className="bg-zinc-900 border-zinc-800"><CardContent className="p-4"><p className="text-xs font-medium text-zinc-100 mb-3">CNAE {ctx.cnae_code} — {ctx.cnae_label}</p><div className="grid grid-cols-4 gap-4">{ctx.index&&<div><p className="text-[8px] uppercase text-zinc-500">Indice</p><p className="text-2xl font-bold font-mono text-zinc-100">{ctx.index.value}</p></div>}{ctx.yoy_change&&<div><p className="text-[8px] uppercase text-zinc-500">Var. anual</p><p className={`text-2xl font-bold font-mono ${ctx.yoy_change.value_pct>=0?'text-emerald-400':'text-rose-400'}`}>{ctx.yoy_change.value_pct>=0&&'+'}{ctx.yoy_change.value_pct}%</p></div>}{ctx.mom_change&&<div><p className="text-[8px] uppercase text-zinc-500">Var. mensual</p><p className={`text-2xl font-bold font-mono ${ctx.mom_change.value_pct>=0?'text-emerald-400':'text-rose-400'}`}>{ctx.mom_change.value_pct>=0&&'+'}{ctx.mom_change.value_pct}%</p></div>}{ctx.ytd_change&&<div><p className="text-[8px] uppercase text-zinc-500">Acumulado</p><p className={`text-2xl font-bold font-mono ${ctx.ytd_change.value_pct>=0?'text-emerald-400':'text-rose-400'}`}>{ctx.ytd_change.value_pct>=0&&'+'}{ctx.ytd_change.value_pct}%</p></div>}</div><p className="text-[8px] text-zinc-600 mt-2">INE | {ctx.data_points} obs | {fmtDate(ctx.last_updated)}</p></CardContent></Card>)}</div>);
}

function IberinformFiles() {
  const [files, setFiles] = useState([]); const [total, setTotal] = useState(0); const [loading, setLoading] = useState(true);
  useEffect(() => { api.get('/providers/iberinform/files').then(r => { setFiles(r.data.files || []); setTotal(r.data.total || 0); }).catch(() => {}).finally(() => setLoading(false)); }, []);
  return (<div className="space-y-3"><span className="text-[10px] text-zinc-500">{total} ficheros</span>{loading ? <Loader2 className="w-4 h-4 animate-spin text-zinc-400 mx-auto mt-4" /> : (<div className="rounded border border-zinc-800 overflow-hidden"><Table><TableHeader><TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900"><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5">Fichero</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Tamaño</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-20">Estado</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-24">Fecha</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-28">SHA256</TableHead><TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-12"></TableHead></TableRow></TableHeader><TableBody>{files.map(f => (<TableRow key={f.file_id} className="border-zinc-800"><TableCell className="py-1 text-xs text-zinc-200">{f.filename}</TableCell><TableCell className="py-1 text-[10px] font-mono text-zinc-300">{fmtSize(f.size_bytes)}</TableCell><TableCell className="py-1"><Badge className="text-[7px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">{f.status}</Badge></TableCell><TableCell className="py-1 text-[10px] text-zinc-400">{fmtDate(f.uploaded_at)}</TableCell><TableCell className="py-1 text-[8px] font-mono text-zinc-600">{f.checksum_sha256?.substring(0,16)}...</TableCell><TableCell className="py-1"><Button size="sm" variant="ghost" className="h-5 text-[9px] text-blue-400" onClick={()=>window.open(`${api.defaults.baseURL}/providers/iberinform/files/${f.file_id}/download`,'_blank')}><Download className="w-3 h-3" /></Button></TableCell></TableRow>))}</TableBody></Table></div>)}</div>);
}
