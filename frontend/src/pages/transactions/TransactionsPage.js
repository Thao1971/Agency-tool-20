import { useState, useEffect, useCallback, useRef } from 'react';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle
} from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import {
  Activity, Plus, Upload, Download, Search, Edit2, Loader2,
  ChevronLeft, ChevronRight, GitMerge, XCircle, History, Send,
  CheckCircle, AlertTriangle, Eye, Trash2, Link2, RefreshCw,
  UserCheck, Ban, PlusCircle, Sparkles, Play, Shield,
  FileText, ExternalLink, ChevronDown, Settings2, Globe, BarChart3,
  ArrowUpDown, ArrowUp, ArrowDown, Filter, ChevronsLeft, ChevronsRight
} from 'lucide-react';
import { toast } from 'sonner';

// ── Status colors & labels ──
const VS_CONFIG = {
  draft: { label: 'Borrador', cls: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20' },
  incomplete: { label: 'Incompleta', cls: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
  needs_review: { label: 'Necesita revision', cls: 'bg-orange-500/10 text-orange-400 border-orange-500/20' },
  ready_for_cis: { label: 'Preparada', cls: 'bg-blue-500/10 text-blue-400 border-blue-500/20' },
  published_in_cis: { label: 'Publicada en CIS', cls: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' },
  pending_sync: { label: 'Cambios pendientes', cls: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
  withdrawn_from_cis: { label: 'Retirada del CIS', cls: 'bg-rose-500/10 text-rose-400 border-rose-500/20' },
  archived: { label: 'Archivada', cls: 'bg-zinc-600/10 text-zinc-500 border-zinc-600/20' },
};

const INC_LABELS = {
  falta_target: 'Falta target', falta_fecha: 'Falta fecha', falta_categoria: 'Falta categoria',
  falta_fuente: 'Falta fuente', falta_fuente_principal: 'Sin fuente principal', falta_descripcion: 'Falta descripcion',
  posible_duplicado: 'Posible duplicado', entidad_pendiente: 'Entidad pendiente',
  review_pendiente: 'Review pendiente', pendiente_sincronizar: 'Sincronizar CIS',
};

const TX_TYPES = ['takeover', 'private_equity', 'venture_capital', 'merger', 'minority_stake', 'asset_acquisition', 'other'];
const TX_STATUSES = ['completed', 'ongoing', 'cancelled', 'unknown'];
const PAGE_SIZE = 30;

// Date formatter DD/MM/YYYY
function fmtDate(isoStr) {
  if (!isoStr) return '—';
  const d = isoStr.substring(0, 10);
  const [y, m, dd] = d.split('-');
  if (!y || !m || !dd) return d;
  return `${dd}/${m}/${y}`;
}

// Country translation
const COUNTRY_ES = {
  spain: 'España', mexico: 'México', 'united states': 'Estados Unidos',
  'united kingdom': 'Reino Unido', france: 'Francia', germany: 'Alemania',
  italy: 'Italia', portugal: 'Portugal', brazil: 'Brasil', uk: 'Reino Unido',
  us: 'Estados Unidos', usa: 'Estados Unidos',
};
function countryES(c) { return c ? (COUNTRY_ES[c.toLowerCase()] || c) : ''; }

const SORT_FIELDS = {
  date: (a, b) => (a.announcement_date || '').localeCompare(b.announcement_date || ''),
  target: (a, b) => (a.target_name || '').localeCompare(b.target_name || ''),
  buyer: (a, b) => (a.buyer_name || '').localeCompare(b.buyer_name || ''),
  category: (a, b) => (a.cis_category_suggested || '').localeCompare(b.cis_category_suggested || ''),
  amount: (a, b) => (a.value_eurm ?? -1) - (b.value_eurm ?? -1),
  status: (a, b) => {
    const order = { published_in_cis: 0, pending_sync: 1, ready_for_cis: 2, needs_review: 3, incomplete: 4, draft: 5, withdrawn_from_cis: 6, archived: 7 };
    return (order[a.visible_status] ?? 9) - (order[b.visible_status] ?? 9);
  },
  incidences: (a, b) => (b.incidences?.length || 0) - (a.incidences?.length || 0),
};

function VsBadge({ status }) {
  const c = VS_CONFIG[status] || VS_CONFIG.draft;
  return <Badge className={`text-[8px] border ${c.cls}`} data-testid={`vs-badge-${status}`}>{c.label}</Badge>;
}

function IncChips({ incidences = [] }) {
  if (!incidences.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {incidences.slice(0, 3).map(inc => (
        <span key={inc} className="text-[7px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/15">
          {INC_LABELS[inc] || inc}
        </span>
      ))}
      {incidences.length > 3 && <span className="text-[7px] text-zinc-500">+{incidences.length - 3}</span>}
    </div>
  );
}

function SortIcon({ field, sortField, sortDir }) {
  if (field !== sortField) return <ArrowUpDown className="w-2.5 h-2.5 text-zinc-600 ml-0.5" />;
  return sortDir === 'asc' ? <ArrowUp className="w-2.5 h-2.5 text-blue-400 ml-0.5" /> : <ArrowDown className="w-2.5 h-2.5 text-blue-400 ml-0.5" />;
}

function TxTable({ txs: rawTxs, total: rawTotal, onOpen, loading: tblLoading, showFilters = true }) {
  const [page, setPage] = useState(0);
  const [sortField, setSortField] = useState('date');
  const [sortDir, setSortDir] = useState('desc');
  const [filters, setFilters] = useState({});
  const [showFilterBar, setShowFilterBar] = useState(false);

  // Reset page when data changes
  useEffect(() => { setPage(0); }, [rawTxs.length]);

  const toggleSort = (field) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir(field === 'date' ? 'desc' : 'asc');
    }
    setPage(0);
  };

  const setFilter = (k, v) => {
    setFilters(f => {
      const nf = { ...f };
      if (!v || v === 'all') delete nf[k]; else nf[k] = v;
      return nf;
    });
    setPage(0);
  };

  const activeFilterCount = Object.keys(filters).length;

  // Apply filters
  let filtered = rawTxs;
  if (filters.search) {
    const q = filters.search.toLowerCase();
    filtered = filtered.filter(tx =>
      (tx.target_name || '').toLowerCase().includes(q) ||
      (tx.buyer_name || '').toLowerCase().includes(q) ||
      (tx.seller_name || '').toLowerCase().includes(q)
    );
  }
  if (filters.category) filtered = filtered.filter(tx => tx.cis_category_suggested === filters.category);
  if (filters.status) filtered = filtered.filter(tx => tx.visible_status === filters.status);
  if (filters.amount === 'known') filtered = filtered.filter(tx => tx.value_eurm != null);
  if (filters.amount === 'unknown') filtered = filtered.filter(tx => tx.value_eurm == null);
  if (filters.incidence) filtered = filtered.filter(tx => (tx.incidences || []).includes(filters.incidence));
  if (filters.has_source === 'yes') filtered = filtered.filter(tx => (tx.sources_count || 0) > 0 || tx.source);
  if (filters.has_source === 'no') filtered = filtered.filter(tx => !((tx.sources_count || 0) > 0 || tx.source));
  if (filters.dateFrom) filtered = filtered.filter(tx => (tx.announcement_date || '') >= filters.dateFrom);
  if (filters.dateTo) filtered = filtered.filter(tx => (tx.announcement_date || '') <= filters.dateTo);

  // Apply sort
  const sortFn = SORT_FIELDS[sortField];
  if (sortFn) {
    filtered = [...filtered].sort((a, b) => sortDir === 'asc' ? sortFn(a, b) : sortFn(b, a));
  }

  const total = filtered.length;
  const pages = Math.ceil(total / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // Get unique categories for filter
  const categories = [...new Set(rawTxs.map(tx => tx.cis_category_suggested).filter(Boolean))].sort();

  const thCls = "text-[8px] uppercase text-zinc-500 py-1.5 px-2 cursor-pointer hover:text-zinc-300 select-none whitespace-nowrap";

  return (
    <div>
      {/* Filter bar */}
      {showFilters && (
        <div className="flex items-center gap-2 mb-2">
          <Input value={filters.search || ''} onChange={e => setFilter('search', e.target.value)}
            placeholder="Buscar target, buyer, seller..." className="bg-zinc-950 border-zinc-700 text-zinc-50 h-7 text-[10px] w-56" data-testid="tx-search" />
          <Button size="sm" variant={showFilterBar ? 'default' : 'outline'} className={`h-7 text-[9px] ${showFilterBar ? 'bg-blue-600 text-white' : 'border-zinc-700 text-zinc-400'}`}
            onClick={() => setShowFilterBar(!showFilterBar)} data-testid="toggle-filters">
            <Filter className="w-3 h-3 mr-1" />Filtros{activeFilterCount > 0 ? ` (${activeFilterCount})` : ''}
          </Button>
          {activeFilterCount > 0 && (
            <Button size="sm" variant="ghost" className="h-7 text-[9px] text-zinc-500" onClick={() => { setFilters({}); setPage(0); }}>
              Limpiar filtros
            </Button>
          )}
          <span className="text-[10px] text-zinc-500 ml-auto">{total} de {rawTxs.length}</span>
        </div>
      )}

      {/* Expanded filter row */}
      {showFilterBar && (
        <div className="flex flex-wrap gap-2 mb-2 p-2 rounded bg-zinc-900/50 border border-zinc-800">
          <Select value={filters.category || 'all'} onValueChange={v => setFilter('category', v)}>
            <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-7 w-44 text-[9px]"><SelectValue placeholder="Categoria" /></SelectTrigger>
            <SelectContent className="bg-zinc-900 border-zinc-700 max-h-60">
              <SelectItem value="all">Todas las categorias</SelectItem>
              {categories.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filters.status || 'all'} onValueChange={v => setFilter('status', v)}>
            <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-7 w-40 text-[9px]"><SelectValue placeholder="Estado" /></SelectTrigger>
            <SelectContent className="bg-zinc-900 border-zinc-700">
              <SelectItem value="all">Todos</SelectItem>
              {Object.entries(VS_CONFIG).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filters.amount || 'all'} onValueChange={v => setFilter('amount', v)}>
            <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-7 w-32 text-[9px]"><SelectValue placeholder="Importe" /></SelectTrigger>
            <SelectContent className="bg-zinc-900 border-zinc-700">
              <SelectItem value="all">Todos</SelectItem>
              <SelectItem value="known">Con importe</SelectItem>
              <SelectItem value="unknown">Sin importe</SelectItem>
            </SelectContent>
          </Select>
          <Select value={filters.incidence || 'all'} onValueChange={v => setFilter('incidence', v)}>
            <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-7 w-40 text-[9px]"><SelectValue placeholder="Incidencia" /></SelectTrigger>
            <SelectContent className="bg-zinc-900 border-zinc-700">
              <SelectItem value="all">Todas</SelectItem>
              {Object.entries(INC_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
          <Input type="date" value={filters.dateFrom || ''} onChange={e => setFilter('dateFrom', e.target.value)}
            className="bg-zinc-950 border-zinc-700 text-zinc-200 h-7 w-32 text-[9px]" placeholder="Desde" />
          <Input type="date" value={filters.dateTo || ''} onChange={e => setFilter('dateTo', e.target.value)}
            className="bg-zinc-950 border-zinc-700 text-zinc-200 h-7 w-32 text-[9px]" placeholder="Hasta" />
        </div>
      )}

      {/* Active filter chips */}
      {activeFilterCount > 0 && !showFilterBar && (
        <div className="flex flex-wrap gap-1 mb-2">
          {filters.category && <Badge variant="outline" className="text-[8px] text-zinc-300 border-zinc-600 gap-1">{filters.category}<XCircle className="w-2.5 h-2.5 cursor-pointer" onClick={() => setFilter('category', null)} /></Badge>}
          {filters.status && <Badge variant="outline" className="text-[8px] text-zinc-300 border-zinc-600 gap-1">{VS_CONFIG[filters.status]?.label}<XCircle className="w-2.5 h-2.5 cursor-pointer" onClick={() => setFilter('status', null)} /></Badge>}
          {filters.amount && <Badge variant="outline" className="text-[8px] text-zinc-300 border-zinc-600 gap-1">{filters.amount === 'known' ? 'Con importe' : 'Sin importe'}<XCircle className="w-2.5 h-2.5 cursor-pointer" onClick={() => setFilter('amount', null)} /></Badge>}
          {filters.incidence && <Badge variant="outline" className="text-[8px] text-zinc-300 border-zinc-600 gap-1">{INC_LABELS[filters.incidence]}<XCircle className="w-2.5 h-2.5 cursor-pointer" onClick={() => setFilter('incidence', null)} /></Badge>}
          {filters.dateFrom && <Badge variant="outline" className="text-[8px] text-zinc-300 border-zinc-600 gap-1">Desde {filters.dateFrom}<XCircle className="w-2.5 h-2.5 cursor-pointer" onClick={() => setFilter('dateFrom', null)} /></Badge>}
          {filters.dateTo && <Badge variant="outline" className="text-[8px] text-zinc-300 border-zinc-600 gap-1">Hasta {filters.dateTo}<XCircle className="w-2.5 h-2.5 cursor-pointer" onClick={() => setFilter('dateTo', null)} /></Badge>}
        </div>
      )}

      {/* Table */}
      <div className="rounded border border-zinc-800 overflow-x-auto">
        <table className="w-full text-left" style={{ tableLayout: 'fixed' }}>
          <colgroup>
            <col style={{ width: '90px' }} />
            <col style={{ width: '34%' }} />
            <col style={{ width: '150px' }} />
            <col style={{ width: '75px' }} />
            <col style={{ width: '130px' }} />
            <col style={{ width: '120px' }} />
            <col style={{ width: '200px' }} />
          </colgroup>
          <thead>
            <tr className="bg-zinc-900 border-b border-zinc-800">
              <th className={thCls} onClick={() => toggleSort('date')}>Fecha<SortIcon field="date" sortField={sortField} sortDir={sortDir} /></th>
              <th className={thCls} onClick={() => toggleSort('target')}>Operacion<SortIcon field="target" sortField={sortField} sortDir={sortDir} /></th>
              <th className={thCls} onClick={() => toggleSort('category')}>Categoria<SortIcon field="category" sortField={sortField} sortDir={sortDir} /></th>
              <th className={thCls} onClick={() => toggleSort('amount')}>Importe<SortIcon field="amount" sortField={sortField} sortDir={sortDir} /></th>
              <th className={`${thCls} cursor-default`}>Fuente</th>
              <th className={thCls} onClick={() => toggleSort('status')}>Estado<SortIcon field="status" sortField={sortField} sortDir={sortDir} /></th>
              <th className={thCls} onClick={() => toggleSort('incidences')}>Incidencias<SortIcon field="incidences" sortField={sortField} sortDir={sortDir} /></th>
            </tr>
          </thead>
          <tbody>
            {paged.length === 0 && (
              <tr><td colSpan={7} className="text-center text-zinc-500 py-8 text-xs">
                {tblLoading ? 'Cargando...' : activeFilterCount > 0 ? 'Sin resultados con estos filtros.' : 'Sin operaciones.'}
              </td></tr>
            )}
            {paged.map(tx => {
              const title = tx.buyer_name ? `${tx.buyer_name} adquiere ${tx.target_name || '?'}` : tx.target_name || '(sin titulo)';
              const srcLabel = tx.primary_source_publisher || tx.source || '';
              const srcExtra = (tx.sources_count || 0) > 1 ? ` +${tx.sources_count - 1}` : '';
              return (
                <tr key={tx.transaction_id} className="border-b border-zinc-800/50 hover:bg-zinc-800/20 cursor-pointer"
                  onClick={() => onOpen(tx.transaction_id)} data-testid={`tx-row-${tx.transaction_id}`}>
                  <td className="py-1.5 px-2 text-[10px] font-mono text-zinc-400">{fmtDate(tx.announcement_date)}</td>
                  <td className="py-1.5 px-2 overflow-hidden">
                    <p className="text-[11px] text-zinc-100 font-medium truncate">{title}</p>
                    {tx.target_name && tx.buyer_name && <p className="text-[9px] text-zinc-500 truncate">{tx.target_name}</p>}
                  </td>
                  <td className="py-1.5 px-2 text-[9px] text-zinc-400 truncate">{tx.cis_category_suggested || '—'}</td>
                  <td className="py-1.5 px-2 text-[10px] font-mono text-zinc-300">{tx.value_eurm ? `${tx.value_eurm}M` : <span className="text-zinc-600">ND</span>}</td>
                  <td className="py-1.5 px-2 text-[10px] text-zinc-400 truncate">{srcLabel}{srcExtra && <span className="text-zinc-600">{srcExtra}</span>}</td>
                  <td className="py-1.5 px-2"><VsBadge status={tx.visible_status} /></td>
                  <td className="py-1.5 px-2"><IncChips incidences={tx.incidences} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between mt-2">
          <span className="text-[10px] text-zinc-500">
            Pagina {page + 1} de {pages} — {page * PAGE_SIZE + 1}-{Math.min((page + 1) * PAGE_SIZE, total)} de {total}
          </span>
          <div className="flex gap-1">
            <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(0)} className="border-zinc-700 text-zinc-300 h-6 w-6 p-0"><ChevronsLeft className="w-3 h-3" /></Button>
            <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)} className="border-zinc-700 text-zinc-300 h-6 w-6 p-0"><ChevronLeft className="w-3 h-3" /></Button>
            <Button variant="outline" size="sm" disabled={page >= pages - 1} onClick={() => setPage(p => p + 1)} className="border-zinc-700 text-zinc-300 h-6 w-6 p-0"><ChevronRight className="w-3 h-3" /></Button>
            <Button variant="outline" size="sm" disabled={page >= pages - 1} onClick={() => setPage(pages - 1)} className="border-zinc-700 text-zinc-300 h-6 w-6 p-0"><ChevronsRight className="w-3 h-3" /></Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function TransactionsPage() {
  const [view, setView] = useState('all');
  const [stats, setStats] = useState(null);
  const [txs, setTxs] = useState([]);
  const [txTotal, setTxTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [viewTxs, setViewTxs] = useState([]);
  const [viewTotal, setViewTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [showNewTx, setShowNewTx] = useState(false);
  const [detailTxId, setDetailTxId] = useState(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [analytics, setAnalytics] = useState(null);
  const fileRef = useRef(null);

  // ── Fetchers ──
  const fetchStats = useCallback(async () => {
    try { const r = await api.get('/transactions/stats'); setStats(r.data); } catch (_) {}
    finally { setLoading(false); }
  }, []);

  const fetchAll = useCallback(async () => {
    try {
      const r = await api.get('/transactions', { params: { limit: 500, offset: 0 } });
      setTxs(r.data.transactions || []);
      setTxTotal(r.data.total || 0);
    } catch (_) {}
  }, []);

  const fetchView = useCallback(async (v) => {
    const endpoint = v === 'needs_review' ? '/transactions/views/needs-review'
      : v === 'ready' ? '/transactions/views/ready-for-cis'
      : v === 'published' ? '/transactions/views/published' : null;
    if (!endpoint) return;
    try {
      const r = await api.get(endpoint, { params: { limit: 500 } });
      setViewTxs(r.data.transactions || []);
      setViewTotal(r.data.total || 0);
    } catch (_) {}
  }, []);

  useEffect(() => { fetchStats(); }, [fetchStats]);
  useEffect(() => {
    if (view === 'all') { fetchAll(); }
    else if (view === 'analytics') {
      api.get('/transactions/analytics').then(r => setAnalytics(r.data)).catch(() => {});
    }
    else { fetchView(view); }
  }, [view, fetchAll, fetchView]);

  const refreshAll = () => { fetchStats(); if (view === 'all') fetchAll(); else fetchView(view); };

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setActionLoading('import');
    try {
      const form = new FormData(); form.append('file', file);
      const r = await api.post('/transactions/import', form, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success(`Importadas ${r.data.imported} transacciones`);
      refreshAll();
    } catch (err) { toast.error(`Error: ${err.response?.data?.detail || err.message}`); }
    finally { setActionLoading(null); if (fileRef.current) fileRef.current.value = ''; }
  };

  const handleExport = async (format = 'excel', pubStatus = null) => {
    try {
      let url = `/transactions/export?format=${format}`;
      if (pubStatus) url += `&publish_status=${pubStatus}`;
      const r = await api.get(url, { responseType: 'blob' });
      const ext = format === 'json' ? 'json' : 'xlsx';
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([r.data]));
      a.download = `transactions.${ext}`;
      a.click();
    } catch (_) { toast.error('Error al exportar'); }
  };

  const s = stats || {};

  return (
    <div className="space-y-4" data-testid="transactions-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-zinc-50 font-heading">M&A Radar</h1>
          <p className="text-xs text-zinc-400">Gestiona operaciones corporativas, fuentes, revision editorial y publicacion en CIS</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setShowNewTx(true)} className="bg-blue-600 hover:bg-blue-500 text-white" data-testid="new-tx-btn">
            <Plus className="w-3 h-3 mr-1" />Nueva
          </Button>
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" onChange={handleImport} className="hidden" />
          <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={actionLoading === 'import'}
            className="border-zinc-700 text-zinc-300" data-testid="import-btn">
            {actionLoading === 'import' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Upload className="w-3 h-3 mr-1" />}Importar
          </Button>
          <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300" onClick={() => handleExport('excel')} data-testid="export-btn">
            <Download className="w-3 h-3 mr-1" />Exportar
          </Button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="flex items-center gap-4 text-[10px] text-zinc-400 px-3 py-2 rounded bg-zinc-900 border border-zinc-800">
        <span className="text-zinc-300 font-medium">{s.total || 0} total</span>
        <span>{s.pending_review || 0} pendientes</span>
        <span>{s.possible_duplicates || 0} duplicados</span>
        {(s.visible_in_cis || s.approved_for_cis) > 0 && <span className="text-cyan-400"><Shield className="w-3 h-3 inline mr-0.5" />{s.visible_in_cis || s.approved_for_cis} en CIS</span>}
        <span className="ml-auto text-zinc-500">{s.imported || 0} importadas / {s.manual || 0} manuales</span>
      </div>

      {/* 4 Main Views */}
      <Tabs value={view} onValueChange={(v) => { setView(v); setOffset(0); }}>
        <div className="flex items-center gap-2">
          <TabsList className="bg-zinc-900 border border-zinc-800 p-1">
            <TabsTrigger value="all" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]" data-testid="view-all">
              Todas
            </TabsTrigger>
            <TabsTrigger value="needs_review" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]" data-testid="view-needs-review">
              Necesitan revision{(s.pending_review || 0) > 0 ? ` (${s.pending_review})` : ''}
            </TabsTrigger>
            <TabsTrigger value="ready" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]" data-testid="view-ready">
              Preparadas
            </TabsTrigger>
            <TabsTrigger value="published" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]" data-testid="view-published">
              Publicadas en CIS{(s.visible_in_cis || s.approved_for_cis) > 0 ? ` (${s.visible_in_cis || s.approved_for_cis})` : ''}
            </TabsTrigger>
            <TabsTrigger value="analytics" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]" data-testid="view-analytics">
              <BarChart3 className="w-3 h-3 mr-1" />Analytics
            </TabsTrigger>
          </TabsList>
          <Button size="sm" variant="ghost" className={`h-7 text-[10px] ${showAdvanced ? 'text-zinc-200' : 'text-zinc-500'}`}
            onClick={() => setShowAdvanced(!showAdvanced)} data-testid="toggle-advanced">
            <Settings2 className="w-3 h-3 mr-1" />Avanzado<ChevronDown className={`w-3 h-3 ml-1 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
          </Button>
        </div>

        {/* ── ALL ── */}
        <TabsContent value="all">
          <TxTable txs={txs} total={txTotal} onOpen={setDetailTxId} loading={loading} />
        </TabsContent>

        {/* ── NEEDS REVIEW ── */}
        <TabsContent value="needs_review">
          <TxTable txs={viewTxs} total={viewTotal} onOpen={setDetailTxId} />
        </TabsContent>

        {/* ── READY FOR CIS ── */}
        <TabsContent value="ready">
          <TxTable txs={viewTxs} total={viewTotal} onOpen={setDetailTxId} />
        </TabsContent>

        {/* ── PUBLISHED ── */}
        <TabsContent value="published">
          <div className="flex gap-2 mb-3">
            <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300 text-[10px] h-8" onClick={() => handleExport('excel', 'approved_for_cis')} data-testid="export-cis-btn">
              <Download className="w-3 h-3 mr-1" />Exportar CIS (Excel)
            </Button>
            <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300 text-[10px] h-8" onClick={() => handleExport('json', 'approved_for_cis')}>
              <Download className="w-3 h-3 mr-1" />Exportar CIS (JSON)
            </Button>
          </div>
          <TxTable txs={viewTxs} total={viewTotal} onOpen={setDetailTxId} />
        </TabsContent>

        {/* ── ANALYTICS ── */}
        <TabsContent value="analytics">
          {!analytics ? (
            <div className="flex justify-center py-12"><Loader2 className="w-5 h-5 animate-spin text-zinc-400" /></div>
          ) : (
            <div className="space-y-4">
              {/* KPI row */}
              <div className="grid grid-cols-4 gap-3">
                {[
                  ['Operaciones', analytics.amount_stats?.total || 0, 'text-blue-400'],
                  ['Importe conocido', analytics.amount_stats?.with_amount || 0, 'text-emerald-400'],
                  ['Volumen total', `${analytics.amount_stats?.total_eurm || 0}M`, 'text-zinc-100'],
                  ['Media EURm', `${analytics.amount_stats?.avg_eurm || 0}M`, 'text-zinc-100'],
                ].map(([label, value, color]) => (
                  <Card key={label} className="bg-zinc-900 border-zinc-800">
                    <CardContent className="p-3">
                      <p className="text-[8px] uppercase tracking-[0.12em] text-zinc-500">{label}</p>
                      <p className={`text-xl font-bold font-mono mt-0.5 ${color}`}>{value}</p>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Funnel */}
              <Card className="bg-zinc-900 border-zinc-800">
                <CardContent className="p-4">
                  <p className="text-[9px] uppercase tracking-wider text-zinc-500 font-semibold mb-3">Pipeline de publicacion</p>
                  <div className="flex items-center gap-1">
                    {[
                      ['Borrador', analytics.funnel?.not_published || 0, 'bg-zinc-700'],
                      ['Lista', analytics.funnel?.ready_to_publish || 0, 'bg-blue-600'],
                      ['CIS', analytics.funnel?.approved_for_cis || 0, 'bg-cyan-600'],
                      ['Retiradas', analytics.funnel?.removed_from_cis || 0, 'bg-rose-600/50'],
                    ].map(([label, count, bg]) => {
                      const total = analytics.amount_stats?.total || 1;
                      const pct = Math.max(count / total * 100, count > 0 ? 8 : 2);
                      return (
                        <div key={label} className="text-center" style={{ flex: pct }}>
                          <div className={`${bg} h-8 rounded flex items-center justify-center`}>
                            <span className="text-[10px] font-bold text-white">{count}</span>
                          </div>
                          <p className="text-[8px] text-zinc-500 mt-1">{label}</p>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>

              <div className="grid grid-cols-2 gap-4">
                {/* By Category */}
                <Card className="bg-zinc-900 border-zinc-800">
                  <CardContent className="p-4">
                    <p className="text-[9px] uppercase tracking-wider text-zinc-500 font-semibold mb-3">Por categoria CIS</p>
                    <div className="space-y-2">
                      {analytics.by_category?.map(r => {
                        const maxCount = Math.max(...analytics.by_category.map(c => c.count), 1);
                        return (
                          <div key={r.category}>
                            <div className="flex items-center justify-between mb-0.5">
                              <span className="text-[10px] text-zinc-300 truncate max-w-[180px]">{r.category}</span>
                              <span className="text-[10px] font-mono text-zinc-400">{r.count} <span className="text-zinc-600">({r.total_eurm}M)</span></span>
                            </div>
                            <div className="w-full bg-zinc-800 rounded-full h-1.5">
                              <div className="bg-blue-500 h-1.5 rounded-full" style={{ width: `${(r.count / maxCount) * 100}%` }} />
                            </div>
                          </div>
                        );
                      })}
                      {!analytics.by_category?.length && <p className="text-[10px] text-zinc-600">Sin datos</p>}
                    </div>
                  </CardContent>
                </Card>

                {/* Top Buyers */}
                <Card className="bg-zinc-900 border-zinc-800">
                  <CardContent className="p-4">
                    <p className="text-[9px] uppercase tracking-wider text-zinc-500 font-semibold mb-3">Compradores mas activos</p>
                    <div className="space-y-2">
                      {analytics.top_buyers?.map((r, i) => (
                        <div key={r.buyer} className="flex items-center gap-2">
                          <span className="text-[10px] font-mono text-zinc-500 w-4">{i + 1}</span>
                          <span className="text-[10px] text-zinc-200 flex-1 truncate">{r.buyer}</span>
                          <span className="text-[10px] font-mono text-zinc-400">{r.count} ops</span>
                          {r.total_eurm > 0 && <span className="text-[9px] font-mono text-zinc-500">{r.total_eurm}M</span>}
                        </div>
                      ))}
                      {!analytics.top_buyers?.length && <p className="text-[10px] text-zinc-600">Sin datos</p>}
                    </div>
                  </CardContent>
                </Card>

                {/* By Year */}
                <Card className="bg-zinc-900 border-zinc-800">
                  <CardContent className="p-4">
                    <p className="text-[9px] uppercase tracking-wider text-zinc-500 font-semibold mb-3">Evolucion temporal</p>
                    <div className="space-y-2">
                      {analytics.by_year?.map(r => (
                        <div key={r.year} className="flex items-center gap-3">
                          <span className="text-xs font-mono text-zinc-300 w-12">{r.year}</span>
                          <div className="flex-1 bg-zinc-800 rounded-full h-2">
                            <div className="bg-cyan-500 h-2 rounded-full" style={{ width: `${Math.min((r.count / Math.max(...analytics.by_year.map(y => y.count), 1)) * 100, 100)}%` }} />
                          </div>
                          <span className="text-[10px] font-mono text-zinc-400 w-16 text-right">{r.count} ops</span>
                          <span className="text-[9px] font-mono text-zinc-500 w-14 text-right">{r.total_eurm}M</span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                {/* By Country + By Type */}
                <Card className="bg-zinc-900 border-zinc-800">
                  <CardContent className="p-4">
                    <p className="text-[9px] uppercase tracking-wider text-zinc-500 font-semibold mb-3">Por pais</p>
                    <div className="flex flex-wrap gap-2 mb-4">
                      {analytics.by_country?.map(r => (
                        <Badge key={r.country} variant="outline" className="text-[9px] text-zinc-300 border-zinc-600">
                          {r.country} <span className="ml-1 text-zinc-500">{r.count}</span>
                        </Badge>
                      ))}
                    </div>
                    <p className="text-[9px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Por tipo</p>
                    <div className="flex flex-wrap gap-2">
                      {analytics.by_type?.map(r => (
                        <Badge key={r.type} variant="outline" className="text-[9px] text-zinc-300 border-zinc-600">
                          {r.type} <span className="ml-1 text-zinc-500">{r.count}</span>
                        </Badge>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* ── ADVANCED (collapsible) ── */}
      {showAdvanced && (
        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="p-3">
            <p className="text-[9px] uppercase tracking-wider text-zinc-500 mb-2 font-semibold">Herramientas avanzadas</p>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300 text-[10px] h-7"
                onClick={async () => { setActionLoading('match'); try { const r = await api.post('/transactions/matching/run-all'); toast.success(`Matching: ${r.data.processed} procesadas`); } catch (_) { toast.error('Error'); } finally { setActionLoading(null); } }}>
                <Link2 className="w-3 h-3 mr-1" />{actionLoading === 'match' ? 'Ejecutando...' : 'Ejecutar matching'}
              </Button>
              <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300 text-[10px] h-7"
                onClick={async () => { setActionLoading('classify'); try { const r = await api.post('/transactions/classification-suggestions/batch', { limit: 20, only_without_category: true, only_without_existing_suggestion: true, dry_run: false }); toast.success(`Clasificacion: ${r.data.suggestions_created} sugerencias`); } catch (_) { toast.error('Error'); } finally { setActionLoading(null); } }}>
                <Sparkles className="w-3 h-3 mr-1" />{actionLoading === 'classify' ? 'Clasificando...' : 'Clasificar pendientes'}
              </Button>
              <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300 text-[10px] h-7" onClick={() => handleExport('excel')}>
                <Download className="w-3 h-3 mr-1" />Exportar todo (Excel)
              </Button>
              <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300 text-[10px] h-7" onClick={() => handleExport('json')}>
                <Download className="w-3 h-3 mr-1" />Exportar todo (JSON)
              </Button>
              <Button size="sm" variant="outline" className="border-cyan-700 text-cyan-300 text-[10px] h-7"
                onClick={async () => { setActionLoading('publish-all'); try { const r = await api.post('/transactions/publish-all-cis'); toast.success(`${r.data.count} operaciones publicadas en CIS`); refreshAll(); } catch (_) { toast.error('Error'); } finally { setActionLoading(null); } }}>
                <Shield className="w-3 h-3 mr-1" />{actionLoading === 'publish-all' ? 'Publicando...' : 'Publicar todas en CIS'}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── NEW TRANSACTION (simplified) ── */}
      <NewTxDialog open={showNewTx} onClose={() => setShowNewTx(false)} onSaved={refreshAll} />

      {/* ── TRANSACTION DETAIL ── */}
      {detailTxId && <TxDetail txId={detailTxId} onClose={() => setDetailTxId(null)} onUpdated={refreshAll} />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════
// NEW TRANSACTION DIALOG (simplified creation)
// ═══════════════════════════════════════════════════════

function NewTxDialog({ open, onClose, onSaved }) {
  const [f, setF] = useState({ target_name: '', buyer_name: '', seller_name: '', announcement_date: '', transaction_type: 'takeover', status: 'completed', geography_primary: '', summary: '' });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setF(p => ({ ...p, [k]: v }));

  useEffect(() => { if (open) setF({ target_name: '', buyer_name: '', seller_name: '', announcement_date: '', transaction_type: 'takeover', status: 'completed', geography_primary: '', summary: '' }); }, [open]);

  const save = async () => {
    if (!f.target_name?.trim()) { toast.error('Target es obligatorio'); return; }
    setSaving(true);
    try {
      const r = await api.post('/transactions', f);
      toast.success('Transaccion creada');
      onSaved();
      onClose();
    } catch (err) { toast.error('Error al crear'); }
    finally { setSaving(false); }
  };

  const inpCls = "bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs";

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="bg-zinc-900 border-zinc-700 max-w-lg">
        <DialogHeader><DialogTitle className="text-zinc-50 font-heading">Nueva operacion</DialogTitle></DialogHeader>
        <div className="space-y-3 pt-2">
          <div className="grid grid-cols-2 gap-3">
            <div><Label className="text-zinc-400 text-[11px]">Target *</Label><Input value={f.target_name} onChange={e => set('target_name', e.target.value)} className={inpCls} data-testid="tx-form-target" /></div>
            <div><Label className="text-zinc-400 text-[11px]">Buyer</Label><Input value={f.buyer_name} onChange={e => set('buyer_name', e.target.value)} className={inpCls} data-testid="tx-form-buyer" /></div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div><Label className="text-zinc-400 text-[11px]">Fecha</Label><Input value={f.announcement_date} onChange={e => set('announcement_date', e.target.value)} placeholder="2026-04-24" className={`${inpCls} font-mono`} data-testid="tx-form-date" /></div>
            <div><Label className="text-zinc-400 text-[11px]">Tipo</Label>
              <Select value={f.transaction_type} onValueChange={v => set('transaction_type', v)}>
                <SelectTrigger className={inpCls}><SelectValue /></SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-700">{TX_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select></div>
            <div><Label className="text-zinc-400 text-[11px]">Pais</Label><Input value={f.geography_primary} onChange={e => set('geography_primary', e.target.value)} className={inpCls} /></div>
          </div>
          <div><Label className="text-zinc-400 text-[11px]">Descripcion</Label><Textarea value={f.summary} onChange={e => set('summary', e.target.value)} rows={2} className="bg-zinc-950 border-zinc-700 text-zinc-50 text-xs" placeholder="Descripcion factual de la operacion..." /></div>
          <Button onClick={save} disabled={saving} className="w-full bg-blue-600 hover:bg-blue-500 text-white" data-testid="tx-form-save">
            {saving && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}Crear operacion
          </Button>
          <p className="text-[9px] text-zinc-600 text-center">Podras completar todos los datos despues desde la ficha.</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ═══════════════════════════════════════════════════════
// TRANSACTION DETAIL (full editorial panel)
// ═══════════════════════════════════════════════════════

function TxDetail({ txId, onClose, onUpdated }) {
  const [tx, setTx] = useState(null);
  const [sources, setSources] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [logs, setLogs] = useState([]);
  const [checklist, setChecklist] = useState(null);
  const [taxonomy, setTaxonomy] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [editFields, setEditFields] = useState({});
  const [showAddSource, setShowAddSource] = useState(false);
  const [newSource, setNewSource] = useState({ title: '', publisher: '', url: '', source_type: 'press_article', is_primary: false });
  const [entitySearch, setEntitySearch] = useState({ open: false, linkId: null, query: '', results: [], loading: false, searched: false });
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [withdrawReason, setWithdrawReason] = useState('incorrect_information');
  const [withdrawNotes, setWithdrawNotes] = useState('');

  const blockRefs = {
    basics: useRef(null), entities: useRef(null), classification: useRef(null),
    sources: useRef(null), description: useRef(null), economics: useRef(null),
    quality: useRef(null), history: useRef(null),
  };

  const loadData = useCallback(async () => {
    if (!txId) return;
    setLoading(true);
    try {
      const [txR, srcR, sugR, logR, clR, taxR] = await Promise.all([
        api.get(`/transactions/${txId}`),
        api.get(`/transactions/sources/${txId}`),
        api.get(`/transactions/${txId}/classification-suggestions`),
        api.get(`/transactions/audit/${txId}`),
        api.get(`/transactions/${txId}/validation-checklist`),
        api.get('/transactions/taxonomy-options'),
      ]);
      setTx(txR.data);
      setSources(srcR.data.sources || []);
      setSuggestions(sugR.data.suggestions || []);
      setLogs(logR.data.logs || []);
      setChecklist(clR.data);
      setTaxonomy(taxR.data.categories || []);
    } catch (_) { toast.error('Error cargando detalle'); }
    finally { setLoading(false); }
  }, [txId]);

  useEffect(() => { loadData(); }, [loadData]);

  const setE = (k, v) => setEditFields(p => ({ ...p, [k]: v }));
  const val = (k) => editMode && k in editFields ? editFields[k] : tx?.[k];
  const inpCls = "bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs";

  const handleSave = async () => {
    if (!Object.keys(editFields).length) { setEditMode(false); return; }
    setActionLoading('save');
    try {
      await api.put(`/transactions/${txId}`, editFields);
      toast.success('Guardado');
      setEditMode(false); setEditFields({});
      loadData(); onUpdated();
    } catch (err) { toast.error('Error al guardar'); }
    finally { setActionLoading(null); }
  };

  const handleAction = async (action) => {
    setActionLoading(action);
    try {
      if (action === 'review') {
        const r = await api.post(`/transactions/${txId}/mark-reviewed`);
        if (r.data.status === 'blocked') { toast.error(`No se puede revisar: ${r.data.blockers.join(', ')}`); return; }
        toast.success('Marcada como revisada');
      } else if (action === 'ready') {
        const r = await api.post(`/transactions/${txId}/mark-ready-for-cis`);
        if (r.data.status === 'blocked') { toast.error(`No cumple requisitos: ${r.data.missing_requirements.join(', ')}`); return; }
        toast.success('Preparada para publicar');
      } else if (action === 'publish') {
        const r = await api.post(`/transactions/${txId}/approve-for-cis`);
        if (r.data.status === 'rejected') { toast.error(`No cumple: ${r.data.missing_requirements.join(', ')}`); return; }
        toast.success('Publicada en CIS');
      } else if (action === 'update') {
        await api.post(`/transactions/${txId}/update-cis`);
        toast.success('Actualizada en CIS');
      } else if (action === 'suggest') {
        await api.post(`/transactions/${txId}/suggest-classification`);
        toast.success('Sugerencia generada');
      }
      loadData(); onUpdated();
    } catch (err) { toast.error(err.response?.data?.detail || 'Error'); }
    finally { setActionLoading(null); }
  };

  const handleAddSource = async () => {
    if (!newSource.url && !newSource.publisher) { toast.error('URL o publisher requerido'); return; }
    setActionLoading('add-src');
    try {
      await api.post(`/transactions/sources/${txId}`, newSource);
      toast.success('Fuente añadida');
      setShowAddSource(false);
      setNewSource({ title: '', publisher: '', url: '', source_type: 'press_article', is_primary: false });
      loadData(); onUpdated();
    } catch (_) { toast.error('Error'); }
    finally { setActionLoading(null); }
  };

  const handleEntityAction = async (linkId, action, companyId) => {
    setActionLoading(linkId);
    try {
      if (action === 'confirm') await api.post(`/transactions/matching/${linkId}/confirm`);
      else if (action === 'reject') await api.post(`/transactions/matching/${linkId}/reject`);
      else if (action === 'external') await api.post(`/transactions/matching/${linkId}/external-entity`);
      else if (action === 'needs_new') await api.post(`/transactions/matching/${linkId}/needs-new`);
      else if (action === 'manual_link') await api.post(`/transactions/matching/${linkId}/manual-link?company_id=${companyId}`);
      toast.success('Entidad actualizada');
      loadData(); onUpdated();
    } catch (_) { toast.error('Error'); }
    finally { setActionLoading(null); }
  };

  const handleEntitySearch = async (q) => {
    if (!q || q.length < 2) return;
    setEntitySearch(p => ({ ...p, loading: true, searched: false }));
    try {
      const r = await api.get(`/transactions/matching/search?q=${encodeURIComponent(q)}`);
      setEntitySearch(p => ({ ...p, results: r.data.results || [], loading: false, searched: true }));
    } catch (_) {
      setEntitySearch(p => ({ ...p, results: [], loading: false, searched: true }));
      toast.error('Error al buscar');
    }
  };

  const openEntitySearch = (linkId, rawName) => {
    setEntitySearch({ open: true, linkId, query: rawName || '', results: [], loading: false, searched: false });
    // Auto-search after a tick
    if (rawName && rawName.length >= 2) {
      setTimeout(() => handleEntitySearch(rawName), 100);
    }
  };

  const handleWithdraw = async () => {
    setActionLoading('withdraw');
    try {
      await api.post(`/transactions/${txId}/withdraw-from-cis`, { reason: withdrawReason, notes: withdrawNotes });
      toast.success('Retirada del CIS');
      setWithdrawOpen(false);
      loadData(); onUpdated();
    } catch (_) { toast.error('Error'); }
    finally { setActionLoading(null); }
  };

  const scrollTo = (block) => blockRefs[block]?.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  if (loading) return <div className="fixed inset-0 z-50 bg-zinc-950/80 flex items-center justify-center"><Loader2 className="w-6 h-6 animate-spin text-zinc-400" /></div>;
  if (!tx) return null;

  const vs = tx.visible_status;
  const activeSug = suggestions.find(s => s.status === 'suggested' && s.validation_status === 'valid');
  const selectedCat = val('cis_category_suggested');
  const subcats = taxonomy.find(c => c.name === selectedCat)?.subcategories || [];

  return (
    <div className="fixed inset-0 z-50 bg-zinc-950/90 flex" data-testid="tx-detail-panel">
      <div className="w-full max-w-3xl mx-auto bg-zinc-900 border-x border-zinc-800 overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 z-10 bg-zinc-900 border-b border-zinc-800 px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onClose} className="text-zinc-400 h-7"><ChevronLeft className="w-4 h-4" /></Button>
            <div>
              <h2 className="text-sm font-bold text-zinc-100 font-heading">{tx.buyer_name ? `${tx.buyer_name} adquiere ${tx.target_name}` : tx.target_name || 'Operacion'}</h2>
              <div className="flex items-center gap-2 mt-0.5"><VsBadge status={vs} /><span className="text-[9px] text-zinc-500 font-mono">{tx.transaction_id}</span></div>
            </div>
          </div>
          <div className="flex gap-2">
            {!editMode && <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300 h-7 text-[10px]" onClick={() => setEditMode(true)} data-testid="edit-mode-btn"><Edit2 className="w-3 h-3 mr-1" />Editar</Button>}
            {editMode && <>
              <Button size="sm" className="bg-blue-600 text-white h-7 text-[10px]" onClick={handleSave} disabled={actionLoading === 'save'} data-testid="save-btn">
                {actionLoading === 'save' ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3 mr-1" />}Guardar borrador
              </Button>
              <Button size="sm" variant="ghost" className="text-zinc-400 h-7 text-[10px]" onClick={() => { setEditMode(false); setEditFields({}); }}>Cancelar</Button>
            </>}
          </div>
        </div>

        <div className="px-6 py-4 space-y-5">
          {/* ── 1. DATOS BASICOS ── */}
          <section ref={blockRefs.basics}>
            <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Datos basicos</h3>
            <div className="grid grid-cols-3 gap-3">
              {[['Target *', 'target_name'], ['Buyer', 'buyer_name'], ['Seller', 'seller_name']].map(([label, key]) => (
                <div key={key}><Label className="text-zinc-500 text-[9px]">{label}</Label>
                  {editMode ? <Input value={val(key) || ''} onChange={e => setE(key, e.target.value)} className={inpCls} data-testid={`edit-${key}`} />
                    : <p className="text-xs text-zinc-100">{tx[key] || '—'}</p>}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-4 gap-3 mt-2">
              <div><Label className="text-zinc-500 text-[9px]">Fecha</Label>
                {editMode ? <Input value={val('announcement_date') || ''} onChange={e => setE('announcement_date', e.target.value)} placeholder="2026-01-15" className={`${inpCls} font-mono`} />
                  : <p className="text-[10px] font-mono text-zinc-300">{fmtDate(tx.announcement_date)}</p>}
              </div>
              <div><Label className="text-zinc-500 text-[9px]">Tipo operacion</Label>
                {editMode ? <Select value={val('transaction_type') || 'other'} onValueChange={v => setE('transaction_type', v)}>
                  <SelectTrigger className={inpCls}><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-zinc-900 border-zinc-700">{TX_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                </Select> : <p className="text-[10px] text-zinc-300">{tx.transaction_type}</p>}
              </div>
              <div><Label className="text-zinc-500 text-[9px]">Pais</Label>
                {editMode ? <Input value={val('geography_primary') || ''} onChange={e => setE('geography_primary', e.target.value)} className={inpCls} />
                  : <p className="text-[10px] text-zinc-300">{countryES(tx.geography_primary) || '—'}</p>}
              </div>
              <div><Label className="text-zinc-500 text-[9px]">Estado deal</Label>
                {editMode ? <Select value={val('status') || 'unknown'} onValueChange={v => setE('status', v)}>
                  <SelectTrigger className={inpCls}><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-zinc-900 border-zinc-700">{TX_STATUSES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                </Select> : <p className="text-[10px] text-zinc-300">{tx.status}</p>}
              </div>
            </div>
          </section>

          {/* ── 2. ENTIDADES Y VINCULACION CIS ── */}
          <section ref={blockRefs.entities}>
            <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Entidades y vinculacion CIS</h3>
            <div className="space-y-2">
              {(tx.company_links || []).map(link => {
                const labels = {
                  manual_confirmed: ['Vinculada a ficha CIS', true], external_entity: ['Entidad externa revisada', true],
                  needs_new_company: ['Crear nueva empresa CIS', true], manual_rejected: ['No aplica', true],
                  auto_strong_candidate: ['Candidato fuerte (confirmar)', false], auto_ambiguous_candidate: ['Pendiente de revisar', false],
                  unmatched: ['Pendiente de revisar', false],
                };
                const [statusLabel, isResolved] = labels[link.match_status] || ['Pendiente', false];
                return (
                  <div key={link.link_id} className="bg-zinc-800/30 p-2.5 rounded space-y-1.5" data-testid={`entity-${link.link_id}`}>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[7px] text-zinc-400 border-zinc-600 w-12 justify-center">{link.entity_role}</Badge>
                      <span className="text-xs text-zinc-200 font-medium flex-1">{link.raw_entity_name}</span>
                      {link.matched_company_name && <span className="text-[9px] text-zinc-400">→ {link.matched_company_name}</span>}
                      <Badge className={`text-[7px] border ${isResolved ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>{statusLabel}</Badge>
                    </div>
                    {/* Actions if not resolved */}
                    {!isResolved && (
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {link.matched_company_name && (
                          <Button size="sm" className="h-5 text-[8px] bg-emerald-600/20 text-emerald-400" disabled={actionLoading === link.link_id}
                            onClick={() => handleEntityAction(link.link_id, 'confirm')} data-testid={`confirm-entity-${link.link_id}`}>
                            <UserCheck className="w-3 h-3 mr-0.5" />Vincular
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" className="h-5 text-[8px] text-blue-400"
                          onClick={() => openEntitySearch(link.link_id, link.raw_entity_name)} data-testid={`search-entity-${link.link_id}`}>
                          <Search className="w-3 h-3 mr-0.5" />Buscar en CIS
                        </Button>
                        <Button size="sm" variant="ghost" className="h-5 text-[8px] text-zinc-400" disabled={actionLoading === link.link_id}
                          onClick={() => handleEntityAction(link.link_id, 'external')} data-testid={`external-entity-${link.link_id}`}>
                          <Globe className="w-3 h-3 mr-0.5" />Entidad externa
                        </Button>
                        <Button size="sm" variant="ghost" className="h-5 text-[8px] text-zinc-400" disabled={actionLoading === link.link_id}
                          onClick={() => handleEntityAction(link.link_id, 'needs_new')}>
                          <PlusCircle className="w-3 h-3 mr-0.5" />Crear nueva
                        </Button>
                      </div>
                    )}
                    {/* Change resolved entity */}
                    {isResolved && editMode && (
                      <div className="flex gap-1.5 pt-1">
                        <Button size="sm" variant="ghost" className="h-5 text-[8px] text-zinc-500"
                          onClick={() => openEntitySearch(link.link_id, link.raw_entity_name)}>
                          <Edit2 className="w-3 h-3 mr-0.5" />Cambiar vinculacion
                        </Button>
                      </div>
                    )}
                  </div>
                );
              })}
              {(!tx.company_links || tx.company_links.length === 0) && (
                <p className="text-[10px] text-zinc-500 italic">Sin entidades. Ejecuta matching desde Avanzado o añade entidades.</p>
              )}
            </div>
          </section>

          {/* Entity Search Dialog */}
          <Dialog open={entitySearch.open} onOpenChange={() => setEntitySearch(p => ({ ...p, open: false }))}>
            <DialogContent className="bg-zinc-900 border-zinc-700 max-w-lg">
              <DialogHeader><DialogTitle className="text-zinc-50 font-heading text-sm">Buscar empresa CIS</DialogTitle></DialogHeader>
              {entitySearch.linkId && (() => {
                const link = (tx.company_links || []).find(l => l.link_id === entitySearch.linkId);
                return link ? <p className="text-[10px] text-zinc-400 -mt-1">Vinculando: <strong className="text-zinc-200">{link.raw_entity_name}</strong> ({link.entity_role})</p> : null;
              })()}
              <div className="flex gap-2 mt-1">
                <Input value={entitySearch.query} onChange={e => setEntitySearch(p => ({ ...p, query: e.target.value }))}
                  placeholder="Nombre, CIF, razon social o dominio..." className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs flex-1"
                  onKeyDown={e => e.key === 'Enter' && handleEntitySearch(entitySearch.query)} data-testid="entity-search-input" />
                <Button size="sm" onClick={() => handleEntitySearch(entitySearch.query)} disabled={entitySearch.loading}
                  className="bg-zinc-800 text-zinc-300 h-8" data-testid="entity-search-btn">
                  {entitySearch.loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
                </Button>
              </div>

              <div className="mt-2 max-h-64 overflow-y-auto">
                {/* Loading */}
                {entitySearch.loading && (
                  <div className="flex items-center justify-center py-6 gap-2">
                    <Loader2 className="w-4 h-4 animate-spin text-zinc-400" />
                    <span className="text-[10px] text-zinc-500">Buscando empresas CIS...</span>
                  </div>
                )}

                {/* Results */}
                {!entitySearch.loading && entitySearch.results.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-[9px] text-zinc-500 mb-1">{entitySearch.results.length} resultado{entitySearch.results.length !== 1 ? 's' : ''}</p>
                    {entitySearch.results.map(r => (
                      <div key={r.id} className="flex items-center justify-between bg-zinc-800/30 p-2.5 rounded hover:bg-zinc-800/50 transition-colors" data-testid={`search-result-${r.id}`}>
                        <div className="flex-1 min-w-0 mr-3">
                          <p className="text-xs text-zinc-100 font-medium">{r.company_name || '(sin nombre)'}</p>
                          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                            {r.input_url && <span className="text-[9px] text-blue-400/70 truncate max-w-[180px]">{r.input_url}</span>}
                            {r.cif && <span className="text-[9px] text-zinc-500">CIF: {r.cif}</span>}
                            {r.category && <Badge variant="outline" className="text-[7px] text-zinc-400 border-zinc-600">{r.category}</Badge>}
                            {r.country && <span className="text-[8px] text-zinc-600">{r.country}</span>}
                          </div>
                        </div>
                        <Button size="sm" className="h-7 text-[9px] bg-blue-600/20 text-blue-400 flex-shrink-0"
                          disabled={actionLoading === entitySearch.linkId}
                          onClick={() => { handleEntityAction(entitySearch.linkId, 'manual_link', r.id); setEntitySearch(p => ({ ...p, open: false })); }}
                          data-testid={`link-company-${r.id}`}>
                          {actionLoading === entitySearch.linkId ? <Loader2 className="w-3 h-3 animate-spin" /> : <Link2 className="w-3 h-3 mr-1" />}Vincular
                        </Button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Empty state */}
                {!entitySearch.loading && entitySearch.searched && entitySearch.results.length === 0 && (
                  <div className="text-center py-6">
                    <p className="text-xs text-zinc-400 mb-2">No se han encontrado empresas en CIS para esta busqueda.</p>
                    <p className="text-[10px] text-zinc-500 mb-3">Prueba con otro termino, o elige una de estas opciones:</p>
                    <div className="flex justify-center gap-2">
                      <Button size="sm" variant="outline" className="h-7 text-[9px] text-zinc-300 border-zinc-600"
                        disabled={actionLoading === entitySearch.linkId}
                        onClick={() => { handleEntityAction(entitySearch.linkId, 'external'); setEntitySearch(p => ({ ...p, open: false })); }}
                        data-testid="empty-state-external">
                        <Globe className="w-3 h-3 mr-1" />Entidad externa
                      </Button>
                      <Button size="sm" variant="outline" className="h-7 text-[9px] text-zinc-300 border-zinc-600"
                        disabled={actionLoading === entitySearch.linkId}
                        onClick={() => { handleEntityAction(entitySearch.linkId, 'needs_new'); setEntitySearch(p => ({ ...p, open: false })); }}
                        data-testid="empty-state-new">
                        <PlusCircle className="w-3 h-3 mr-1" />Crear nueva empresa
                      </Button>
                    </div>
                  </div>
                )}

                {/* Initial state (not searched yet) */}
                {!entitySearch.loading && !entitySearch.searched && entitySearch.results.length === 0 && (
                  <p className="text-[10px] text-zinc-600 text-center py-4">Escribe un termino y pulsa buscar o Enter.</p>
                )}
              </div>
            </DialogContent>
          </Dialog>

          {/* ── 3. CLASIFICACION CIS ── */}
          <section ref={blockRefs.classification}>
            <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Clasificacion CIS</h3>
            {editMode ? (
              <div className="space-y-2">
                <div className="grid grid-cols-2 gap-3">
                  <div><Label className="text-zinc-500 text-[9px]">Categoria CIS</Label>
                    <Select value={val('cis_category_suggested') || '_none'} onValueChange={v => { setE('cis_category_suggested', v === '_none' ? null : v); if (v !== val('cis_category_suggested')) setE('cis_subcategory_suggested', null); setE('outside_cis_taxonomy', false); }} data-testid="edit-category">
                      <SelectTrigger className={inpCls}><SelectValue placeholder="Seleccionar categoria" /></SelectTrigger>
                      <SelectContent className="bg-zinc-900 border-zinc-700 max-h-60">
                        <SelectItem value="_none">Sin categoria</SelectItem>
                        {taxonomy.map(c => <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div><Label className="text-zinc-500 text-[9px]">Subcategoria</Label>
                    <Select value={val('cis_subcategory_suggested') || '_none'} onValueChange={v => setE('cis_subcategory_suggested', v === '_none' ? null : v)} disabled={!selectedCat || val('outside_cis_taxonomy')}>
                      <SelectTrigger className={inpCls}><SelectValue placeholder="Seleccionar subcategoria" /></SelectTrigger>
                      <SelectContent className="bg-zinc-900 border-zinc-700 max-h-60">
                        <SelectItem value="_none">Sin subcategoria</SelectItem>
                        {subcats.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Switch checked={val('outside_cis_taxonomy') || false} onCheckedChange={v => { setE('outside_cis_taxonomy', v); if (v) { setE('cis_category_suggested', null); setE('cis_subcategory_suggested', null); } }} />
                  <Label className="text-zinc-400 text-[10px]">Fuera de taxonomia CIS</Label>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 flex-wrap">
                {tx.cis_category_suggested && <Badge className="text-[9px] border bg-blue-500/10 text-blue-400 border-blue-500/20">{tx.cis_category_suggested}</Badge>}
                {tx.cis_subcategory_suggested && <Badge variant="outline" className="text-[8px] text-zinc-300 border-zinc-600">{tx.cis_subcategory_suggested}</Badge>}
                {tx.outside_cis_taxonomy && <Badge className="text-[8px] border bg-zinc-500/10 text-zinc-400 border-zinc-500/20">Fuera de taxonomia CIS</Badge>}
                {!tx.cis_category_suggested && !tx.outside_cis_taxonomy && <span className="text-[10px] text-zinc-500">Sin clasificar</span>}
              </div>
            )}
            {/* AI Suggestion */}
            {activeSug && (
              <div className="border border-zinc-700/40 rounded p-2 bg-zinc-800/20 mt-2">
                <div className="flex items-center gap-2 mb-1">
                  <Sparkles className="w-3 h-3 text-blue-400" /><span className="text-[9px] text-zinc-400">Sugerencia IA:</span>
                  <Badge className="text-[8px] bg-blue-500/10 text-blue-400 border border-blue-500/20">{activeSug.suggested_category}</Badge>
                  <Badge variant="outline" className="text-[7px] text-zinc-300 border-zinc-600">{activeSug.suggested_subcategory}</Badge>
                  <span className="text-[8px] text-zinc-500">({(activeSug.confidence * 100).toFixed(0)}%)</span>
                </div>
                <p className="text-[9px] text-zinc-400 mb-1">{activeSug.reasoning}</p>
                <div className="flex gap-2">
                  <Button size="sm" className="h-5 text-[8px] bg-emerald-600/20 text-emerald-400" disabled={actionLoading === 'accept-sug'}
                    onClick={async () => { setActionLoading('accept-sug'); try { await api.post(`/transactions/${txId}/classification-suggestions/${activeSug.suggestion_id}/accept`); toast.success('Aplicada'); loadData(); onUpdated(); } catch (_) { toast.error('Error'); } finally { setActionLoading(null); } }} data-testid="accept-suggestion">
                    <CheckCircle className="w-3 h-3 mr-0.5" />Aplicar sugerencia
                  </Button>
                  <Button size="sm" variant="ghost" className="h-5 text-[8px] text-zinc-400"
                    onClick={async () => { try { await api.post(`/transactions/${txId}/classification-suggestions/${activeSug.suggestion_id}/reject`); loadData(); } catch (_) {} }}>
                    <XCircle className="w-3 h-3 mr-0.5" />Rechazar
                  </Button>
                </div>
              </div>
            )}
            <Button size="sm" variant="ghost" className="h-6 text-[9px] text-blue-400 mt-1" disabled={actionLoading === 'suggest'}
              onClick={() => handleAction('suggest')} data-testid="suggest-btn">
              {actionLoading === 'suggest' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Sparkles className="w-3 h-3 mr-1" />}Sugerir clasificacion
            </Button>
          </section>

          {/* ── 4. FUENTES Y ARTICULOS ── */}
          <section ref={blockRefs.sources}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">Fuentes y articulos</h3>
              <Button size="sm" variant="ghost" className="h-6 text-[9px] text-blue-400" onClick={() => setShowAddSource(true)} data-testid="add-source-btn">
                <Plus className="w-3 h-3 mr-1" />Añadir fuente
              </Button>
            </div>
            {sources.length === 0 && !tx.source && <p className="text-[10px] text-rose-400">Sin fuentes. Añade al menos una para poder publicar.</p>}
            {sources.length === 0 && tx.source && (
              <div className="flex items-center gap-2 bg-zinc-800/30 p-2 rounded mb-1">
                <FileText className="w-3 h-3 text-zinc-500" /><span className="text-xs text-zinc-200">{tx.source}</span>
                {tx.source_url && <a href={tx.source_url} target="_blank" rel="noopener noreferrer" className="text-blue-400"><ExternalLink className="w-3 h-3" /></a>}
                <Badge className="text-[7px] bg-blue-500/10 text-blue-400 border border-blue-500/20 ml-auto">Principal</Badge>
              </div>
            )}
            {sources.map(src => (
              <div key={src.source_id} className="flex items-center gap-2 bg-zinc-800/30 p-2 rounded mb-1" data-testid={`source-${src.source_id}`}>
                <FileText className="w-3 h-3 text-zinc-500 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-zinc-200 truncate">{src.title || src.publisher || src.url}</p>
                  <p className="text-[9px] text-zinc-500">{src.publisher} {src.published_at ? `· ${src.published_at.substring(0, 10)}` : ''} · {src.source_type}</p>
                </div>
                {src.url && <a href={src.url} target="_blank" rel="noopener noreferrer" className="text-blue-400"><ExternalLink className="w-3 h-3" /></a>}
                {src.is_primary ? <Badge className="text-[7px] bg-blue-500/10 text-blue-400 border border-blue-500/20">Principal</Badge>
                  : <Button size="sm" variant="ghost" className="h-5 text-[7px] text-zinc-500"
                      onClick={async () => { await api.put(`/transactions/sources/${txId}/${src.source_id}`, { is_primary: true }); loadData(); onUpdated(); }}>Hacer principal</Button>}
                <Button size="sm" variant="ghost" className="h-5 w-5 p-0 text-zinc-500 hover:text-rose-400"
                  onClick={async () => { await api.delete(`/transactions/sources/${txId}/${src.source_id}`); loadData(); onUpdated(); }}>
                  <Trash2 className="w-3 h-3" />
                </Button>
              </div>
            ))}
            {showAddSource && (
              <div className="border border-zinc-700/40 rounded p-3 mt-2 space-y-2">
                <div className="grid grid-cols-2 gap-2">
                  <Input value={newSource.publisher} onChange={e => setNewSource(p => ({ ...p, publisher: e.target.value }))} placeholder="Publisher (ej: Expansion)" className="bg-zinc-950 border-zinc-700 text-zinc-50 h-7 text-xs" data-testid="new-source-publisher" />
                  <Input value={newSource.url} onChange={e => setNewSource(p => ({ ...p, url: e.target.value }))} placeholder="URL del articulo" className="bg-zinc-950 border-zinc-700 text-zinc-50 h-7 text-xs" data-testid="new-source-url" />
                </div>
                <Input value={newSource.title} onChange={e => setNewSource(p => ({ ...p, title: e.target.value }))} placeholder="Titulo (opcional)" className="bg-zinc-950 border-zinc-700 text-zinc-50 h-7 text-xs" />
                <div className="flex items-center gap-3">
                  <Switch checked={newSource.is_primary} onCheckedChange={v => setNewSource(p => ({ ...p, is_primary: v }))} /><Label className="text-zinc-400 text-[10px]">Principal</Label>
                  <Button size="sm" className="ml-auto bg-blue-600 text-white h-6 text-[9px]" onClick={handleAddSource} disabled={actionLoading === 'add-src'} data-testid="save-source-btn">Guardar</Button>
                  <Button size="sm" variant="ghost" className="h-6 text-[9px] text-zinc-400" onClick={() => setShowAddSource(false)}>Cancelar</Button>
                </div>
              </div>
            )}
          </section>

          {/* ── 5. DESCRIPCION EDITORIAL ── */}
          <section ref={blockRefs.description}>
            <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Descripcion editorial</h3>
            <div className="space-y-2">
              <div><Label className="text-zinc-500 text-[9px]">Descripcion (publica en CIS) *</Label>
                {editMode ? <Textarea value={val('summary') || ''} onChange={e => setE('summary', e.target.value)} rows={2} className="bg-zinc-950 border-zinc-700 text-zinc-50 text-xs" data-testid="edit-summary" />
                  : <p className="text-xs text-zinc-300 leading-relaxed">{tx.summary || <span className="text-rose-400/70 italic">Sin descripcion — obligatoria para publicar</span>}</p>}
              </div>
              <div><Label className="text-zinc-500 text-[9px]">Lectura estrategica (publica en CIS si existe)</Label>
                {editMode ? <Textarea value={val('strategic_rationale') || ''} onChange={e => setE('strategic_rationale', e.target.value)} rows={2} className="bg-zinc-950 border-zinc-700 text-zinc-50 text-xs" />
                  : <p className="text-xs text-zinc-300">{tx.strategic_rationale || <span className="text-zinc-600 italic">Opcional</span>}</p>}
              </div>
              <div><Label className="text-zinc-500 text-[9px]">Notas internas (no se publica)</Label>
                {editMode ? <Textarea value={val('editorial_notes') || ''} onChange={e => setE('editorial_notes', e.target.value)} rows={2} className="bg-zinc-950 border-zinc-700 text-zinc-50 text-xs" />
                  : tx.editorial_notes ? <p className="text-xs text-zinc-400 italic">{tx.editorial_notes}</p> : null}
              </div>
            </div>
          </section>

          {/* ── 6. DATOS ECONOMICOS ── */}
          <section ref={blockRefs.economics}>
            <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Datos economicos</h3>
            <div className="grid grid-cols-4 gap-3">
              {[['Importe EURm', 'value_eurm'], ['Revenue EURm', 'revenue_eurm'], ['EBITDA EURm', 'ebitda_eurm'], ['EV EURm', 'ev_eurm']].map(([label, key]) => (
                <div key={key}><Label className="text-zinc-500 text-[9px]">{label}</Label>
                  {editMode ? <Input value={val(key) ?? ''} onChange={e => setE(key, e.target.value ? parseFloat(e.target.value) : null)} type="number" step="0.1" className={`${inpCls} font-mono`} />
                    : <p className="text-xs font-mono text-zinc-300">{tx[key] ?? '—'}</p>}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-4 gap-3 mt-2">
              <div><Label className="text-zinc-500 text-[9px]">VE/Ventas</Label><p className="text-xs font-mono text-zinc-300">{editMode ? <Input value={val('ve_sales') ?? ''} onChange={e => setE('ve_sales', e.target.value ? parseFloat(e.target.value) : null)} type="number" step="0.01" className={`${inpCls} font-mono`} /> : (tx.ve_sales ?? '—')}</p></div>
              <div><Label className="text-zinc-500 text-[9px]">VE/EBITDA</Label><p className="text-xs font-mono text-zinc-300">{editMode ? <Input value={val('ve_ebitda') ?? ''} onChange={e => setE('ve_ebitda', e.target.value ? parseFloat(e.target.value) : null)} type="number" step="0.01" className={`${inpCls} font-mono`} /> : (tx.ve_ebitda ?? '—')}</p></div>
              <div><Label className="text-zinc-500 text-[9px]">Base valoracion</Label><p className="text-[10px] text-zinc-300">{tx.valuation_basis || 'unknown'}</p></div>
              <div><Label className="text-zinc-500 text-[9px]">Estado importe</Label><p className="text-[10px] text-zinc-300">{tx.amount_status || 'undisclosed'}</p></div>
            </div>
          </section>

          {/* ── 7. CALIDAD Y PUBLICACION CIS ── */}
          <section ref={blockRefs.quality}>
            <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Calidad y publicacion CIS</h3>
            {checklist && (
              <div className="space-y-1 mb-3">
                {checklist.requirements.map(req => (
                  <div key={req.key} className="flex items-center gap-2 text-[10px]">
                    {req.status === 'ok' ? <CheckCircle className="w-3 h-3 text-emerald-400 flex-shrink-0" />
                      : req.status === 'warning' ? <AlertTriangle className="w-3 h-3 text-amber-400 flex-shrink-0" />
                      : <XCircle className="w-3 h-3 text-rose-400 flex-shrink-0" />}
                    <span className={req.status === 'ok' ? 'text-zinc-300' : req.status === 'error' ? 'text-rose-300' : 'text-amber-300'}>{req.label}</span>
                    {req.status === 'error' && (
                      <Button size="sm" variant="ghost" className="h-4 text-[8px] text-blue-400 ml-auto px-1" onClick={() => scrollTo(req.block)} data-testid={`resolve-${req.key}`}>
                        Resolver
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}
            {/* Action buttons */}
            <div className="flex flex-wrap gap-2">
              {tx.review_status !== 'approved' && tx.review_status !== 'reviewed' && (
                <Button size="sm" className="h-7 text-[10px] bg-zinc-800 text-zinc-200" onClick={() => handleAction('review')} disabled={actionLoading === 'review'} data-testid="mark-reviewed-btn">
                  {actionLoading === 'review' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <CheckCircle className="w-3 h-3 mr-1" />}Marcar como revisada
                </Button>
              )}
              {vs !== 'ready_for_cis' && vs !== 'published_in_cis' && vs !== 'pending_sync' && tx.publish_status !== 'approved_for_cis' && tx.publish_status !== 'ready_to_publish' && (
                <Button size="sm" className="h-7 text-[10px] bg-blue-600/20 text-blue-400" onClick={async () => {
                  try { await api.post(`/transactions/${txId}/mark-ready`); toast.success('Marcada como preparada'); loadData(); onUpdated(); } catch (_) { toast.error('Error'); }
                }} data-testid="mark-ready-btn">
                  <CheckCircle className="w-3 h-3 mr-1" />Marcar como preparada
                </Button>
              )}
              {(vs === 'ready_for_cis' || checklist?.can_publish) && vs !== 'published_in_cis' && vs !== 'pending_sync' && !tx.visible_in_cis && tx.publish_status !== 'approved_for_cis' && (
                <Button size="sm" className="h-7 text-[10px] bg-cyan-600 hover:bg-cyan-500 text-white" onClick={() => handleAction('publish')} disabled={actionLoading === 'publish'} data-testid="publish-cis-btn">
                  {actionLoading === 'publish' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Shield className="w-3 h-3 mr-1" />}Publicar en CIS
                </Button>
              )}
              {vs === 'pending_sync' && (
                <Button size="sm" className="h-7 text-[10px] bg-amber-600 hover:bg-amber-500 text-white" onClick={() => handleAction('update')} disabled={actionLoading === 'update'} data-testid="update-cis-btn">
                  {actionLoading === 'update' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <RefreshCw className="w-3 h-3 mr-1" />}Actualizar en CIS
                </Button>
              )}
              {vs === 'published_in_cis' && <Badge className="text-[9px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 py-1"><Shield className="w-3 h-3 mr-1" />Publicada en CIS</Badge>}
              {(vs === 'published_in_cis' || vs === 'pending_sync') && (
                <Button size="sm" variant="ghost" className="h-7 text-[10px] text-rose-400" onClick={() => setWithdrawOpen(true)} data-testid="withdraw-btn">
                  <XCircle className="w-3 h-3 mr-1" />Retirar del CIS
                </Button>
              )}
              {!tx.deleted && (
                <Button size="sm" variant="ghost" className="h-7 text-[10px] text-rose-400" onClick={async () => {
                  const msg = (tx.visible_in_cis || tx.publish_status === 'approved_for_cis')
                    ? 'Esta operacion esta publicada en CIS. Al eliminarla tambien se retirara del CIS. ¿Continuar?'
                    : 'Eliminar esta operacion?';
                  if (!window.confirm(msg)) return;
                  try { await api.post(`/transactions/${txId}/soft-delete`, { reason: 'manual' }); toast.success('Eliminada'); onClose(); onUpdated(); } catch (err) { toast.error(err.response?.data?.detail || 'Error'); }
                }} data-testid="delete-tx-btn">
                  <Trash2 className="w-3 h-3 mr-1" />Eliminar operacion
                </Button>
              )}
            </div>
            {tx.approved_for_cis_at && <p className="text-[9px] text-zinc-500 mt-1">Publicada: {fmtDate(tx.approved_for_cis_at)} por {tx.approved_for_cis_by}</p>}
          </section>

          {/* ── 8. HISTORIAL ── */}
          <section ref={blockRefs.history}>
            <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Historial</h3>
            <div className="space-y-0.5 max-h-48 overflow-y-auto">
              {logs.slice(0, 25).map((l, i) => (
                <div key={i} className="flex items-center gap-2 text-[9px] text-zinc-400 py-0.5 border-b border-zinc-800/30">
                  <span className="font-mono text-zinc-500 w-24 flex-shrink-0">{fmtDate(l.changed_at)}</span>
                  <Badge variant="outline" className={`text-[7px] border-zinc-700 ${
                    l.action?.includes('cis') ? 'text-cyan-400' : l.action?.includes('withdrawn') ? 'text-rose-400' :
                    l.action?.includes('created') || l.action?.includes('accepted') ? 'text-emerald-400' : 'text-zinc-400'
                  }`}>{l.action}</Badge>
                  <span className="truncate">{l.changed_by}</span>
                </div>
              ))}
              {logs.length === 0 && <p className="text-[10px] text-zinc-600">Sin historial</p>}
            </div>
          </section>
        </div>
      </div>

      {/* Withdraw dialog */}
      <Dialog open={withdrawOpen} onOpenChange={setWithdrawOpen}>
        <DialogContent className="bg-zinc-900 border-zinc-700 max-w-sm">
          <DialogHeader><DialogTitle className="text-zinc-50 font-heading text-sm">Retirar del CIS</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label className="text-zinc-400 text-[11px]">Motivo *</Label>
              <Select value={withdrawReason} onValueChange={setWithdrawReason}>
                <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-8 text-xs" data-testid="withdraw-reason">
                  <SelectValue /></SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-700">
                  <SelectItem value="incorrect_information">Informacion incorrecta</SelectItem>
                  <SelectItem value="duplicate_operation">Operacion duplicada</SelectItem>
                  <SelectItem value="unconfirmed_operation">Operacion no confirmada</SelectItem>
                  <SelectItem value="out_of_scope">Fuera de scope</SelectItem>
                  <SelectItem value="import_error">Error de importacion</SelectItem>
                  <SelectItem value="other">Otro</SelectItem>
                </SelectContent>
              </Select></div>
            <div><Label className="text-zinc-400 text-[11px]">Notas</Label>
              <Textarea value={withdrawNotes} onChange={e => setWithdrawNotes(e.target.value)} rows={2} className="bg-zinc-950 border-zinc-700 text-zinc-50 text-xs" /></div>
            <Button className="w-full bg-rose-600 hover:bg-rose-500 text-white text-[10px]" onClick={handleWithdraw} disabled={actionLoading === 'withdraw'} data-testid="confirm-withdraw-btn">
              {actionLoading === 'withdraw' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <XCircle className="w-3 h-3 mr-1" />}Confirmar retirada
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
