import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
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
import {
  Newspaper, Plus, Play, CheckCircle, XCircle, Eye, Loader2,
  ExternalLink, Rss, Globe, Download, FileText, ChevronLeft,
  ChevronRight, Bookmark, RefreshCw, Activity, Calendar,
  Inbox, Archive, Zap, PauseCircle, Copy
} from 'lucide-react';
import { toast } from 'sonner';

// Format date as DD/MM/YYYY (Spanish format, no time)
function fmtDate(isoStr) {
  if (!isoStr) return null;
  const d = isoStr.substring(0, 10); // "2026-04-24"
  const [y, m, dd] = d.split('-');
  if (!y || !m || !dd) return d;
  return `${dd}/${m}/${y}`;
}

const SL = {
  cifras_resultados: { l: "Cifras y Resultados", e: "💰💹", c: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" },
  indies: { l: "Indies", e: "🎸✨", c: "bg-violet-500/15 text-violet-400 border-violet-500/25" },
  noticias_semana: { l: "Noticias de la semana", e: "💡", c: "bg-blue-500/15 text-blue-400 border-blue-500/25" },
  ma_vc_pe_alianzas: { l: "M&A, VC, PE y alianzas", e: "🚀", c: "bg-amber-500/15 text-amber-400 border-amber-500/25" },
  podcasts_entrevistas: { l: "Podcasts y entrevistas", e: "🎧", c: "bg-pink-500/15 text-pink-400 border-pink-500/25" },
  lecturas_interesantes: { l: "Lecturas interesantes", e: "🤓", c: "bg-indigo-500/15 text-indigo-400 border-indigo-500/25" },
  mirada_control: { l: "La mirada de Control", e: "🧭", c: "bg-teal-500/15 text-teal-400 border-teal-500/25" },
  palabra_de_dani: { l: "Palabra de Dani", e: "💬", c: "bg-orange-500/15 text-orange-400 border-orange-500/25" },
  nombramientos_reconocimientos: { l: "Nombramientos", e: "🏅👤", c: "bg-cyan-500/15 text-cyan-400 border-cyan-500/25" },
  eventos: { l: "Eventos", e: "🕰🎉🇪🇸", c: "bg-rose-500/15 text-rose-400 border-rose-500/25" },
};

export default function EditorialPage() {
  const [tab, setTab] = useState('dashboard');
  const [sources, setSources] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [items, setItems] = useState([]);
  const [itemsTotal, setItemsTotal] = useState(0);
  const [digests, setDigests] = useState([]);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);

  const [showAddSource, setShowAddSource] = useState(false);
  const [srcName, setSrcName] = useState(''); const [srcUrl, setSrcUrl] = useState('');
  const [srcType, setSrcType] = useState('rss'); const [srcFreq, setSrcFreq] = useState('12h');
  const [testResult, setTestResult] = useState(null); const [testing, setTesting] = useState(false);

  const [iView, setIView] = useState('pending');
  const [iSection, setISection] = useState('all');
  const [iSearch, setISearch] = useState(''); const [iOffset, setIOffset] = useState(0);

  const [showNewDigest, setShowNewDigest] = useState(false);
  const [digTitle, setDigTitle] = useState(''); const [digWeek, setDigWeek] = useState('');
  const [digIntro, setDigIntro] = useState('');
  const [activeDigest, setActiveDigest] = useState(null);
  const [digestOutput, setDigestOutput] = useState(null);
  const [approvedItems, setApprovedItems] = useState([]);

  const fetchAll = useCallback(async () => {
    try {
      const [src, jbs, hlth, dgs] = await Promise.all([
        api.get('/editorial/sources'), api.get('/editorial/jobs'),
        api.get('/editorial/health'), api.get('/editorial/digests'),
      ]);
      setSources(src.data.sources || []); setJobs(jbs.data.jobs || []);
      setHealth(hlth.data); setDigests(dgs.data.digests || []);
    } catch (_) {} finally { setLoading(false); }
  }, []);

  const fetchItems = useCallback(async () => {
    const params = { limit: 40, offset: iOffset };
    if (iView === 'pending') params.status = 'new';
    if (iSection !== 'all') params.section = iSection;
    if (iSearch) params.search = iSearch;
    try { const r = await api.get('/editorial/items', { params }); setItems(r.data.items || []); setItemsTotal(r.data.total || 0); } catch (_) {}
  }, [iOffset, iView, iSection, iSearch]);

  const fetchApproved = useCallback(async () => {
    try { const r = await api.get('/editorial/items', { params: { status: 'approved', limit: 100 } }); setApprovedItems(r.data.items || []); } catch (_) {}
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);
  useEffect(() => { if (tab === 'items') fetchItems(); }, [tab, fetchItems]);
  useEffect(() => { if (tab === 'digest') fetchApproved(); }, [tab, fetchApproved]);

  // Source actions
  const handleTestUrl = async () => { if (!srcUrl) return; setTesting(true); setTestResult(null); try { const r = await api.post('/editorial/sources/test-url', { url: srcUrl, source_type: srcType }); setTestResult(r.data); if (r.data.detected_type) setSrcType(r.data.detected_type); } catch (_) { toast.error('Test fallido'); } finally { setTesting(false); } };
  const handleAddSource = async () => { if (!srcName || !srcUrl) { toast.error('Nombre y URL obligatorios'); return; } try { await api.post('/editorial/sources', { name: srcName, url: srcUrl, source_type: srcType, crawl_frequency: srcFreq }); toast.success('Fuente creada'); setShowAddSource(false); setSrcName(''); setSrcUrl(''); setTestResult(null); fetchAll(); } catch (_) { toast.error('Error'); } };
  const handleCrawl = async (sid) => { setActionLoading(`c-${sid}`); try { await api.post(`/editorial/sources/${sid}/crawl`); toast.success('Scrapeo lanzado'); setTimeout(() => { fetchAll(); if (tab === 'items') fetchItems(); }, 4000); } catch (_) { toast.error('Error'); } finally { setActionLoading(null); } };

  // Bulk source actions
  const handleBulkActivate = async () => { setActionLoading('bulk-act'); for (const s of sources.filter(s => !s.active)) { await api.post(`/editorial/sources/${s.source_id}/activate`); } toast.success('Todas activadas'); fetchAll(); setActionLoading(null); };
  const handleBulkDeactivate = async () => { setActionLoading('bulk-deact'); for (const s of sources.filter(s => s.active)) { await api.post(`/editorial/sources/${s.source_id}/deactivate`); } toast.success('Todas desactivadas'); fetchAll(); setActionLoading(null); };
  const handleBulkCrawl = async () => { setActionLoading('bulk-crawl'); for (const s of sources.filter(s => s.active)) { await api.post(`/editorial/sources/${s.source_id}/crawl`); } toast.success(`Scrapeo lanzado en ${sources.filter(s=>s.active).length} fuentes`); setTimeout(fetchAll, 5000); setActionLoading(null); };

  // Item actions
  const handleItemAction = async (id, action) => { try { if (action === 'approve') await api.post(`/editorial/items/${id}/approve`); else await api.post(`/editorial/items/${id}/discard`); toast.success(action === 'approve' ? 'Aprobado' : 'Descartado'); fetchItems(); fetchApproved(); fetchAll(); } catch (_) {} };
  const addToDigest = async (id) => { if (!activeDigest) { toast.error('Selecciona una edicion'); return; } try { await api.post(`/editorial/items/${id}/mark-for-digest`, { digest_id: activeDigest.digest_id }); const nids = [...(activeDigest.selected_item_ids || []), id]; await api.put(`/editorial/digests/${activeDigest.digest_id}`, { selected_item_ids: nids }); setActiveDigest(p => ({ ...p, selected_item_ids: nids })); toast.success('Anadido a la edicion'); fetchApproved(); } catch (_) {} };

  // Digest
  const handleCreateDigest = async () => { try { const r = await api.post('/editorial/digests', { week_label: digWeek, title: digTitle, intro_text: digIntro }); setActiveDigest(r.data); setShowNewDigest(false); fetchAll(); toast.success('Edicion creada'); } catch (_) {} };
  const handleGenerateOutput = async (dId) => { try { const r = await api.post(`/editorial/digests/${dId}/generate-output`); setDigestOutput(r.data); toast.success(`Generado: ${r.data.items_count} items`); } catch (_) { toast.error('Error'); } };

  const copyHtmlToClipboard = async (html) => {
    try {
      const blob = new Blob([html], { type: 'text/html' });
      await navigator.clipboard.write([new window.ClipboardItem({ 'text/html': blob, 'text/plain': new Blob([html], { type: 'text/plain' }) })]);
      toast.success('Copiado para Substack (con enlaces)');
    } catch (_) {
      navigator.clipboard.writeText(html);
      toast.success('Copiado como HTML');
    }
  };

  const h = health || {};
  const activeSources = sources.filter(s => s.active).length;

  return (
    <TooltipProvider>
    <div className="space-y-4" data-testid="editorial-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-zinc-50 font-heading">Editorial Intelligence</h1>
          <p className="text-xs text-zinc-400">Curar senales sectoriales y construir edicion semanal</p>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="dashboard" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-xs"><Activity className="w-3 h-3 mr-1" />Panel</TabsTrigger>
          <TabsTrigger value="sources" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-xs"><Rss className="w-3 h-3 mr-1" />Fuentes</TabsTrigger>
          <TabsTrigger value="items" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-xs"><Inbox className="w-3 h-3 mr-1" />Items{h.items?.new ? ` (${h.items.new})` : ''}</TabsTrigger>
          <TabsTrigger value="email" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-xs"><Globe className="w-3 h-3 mr-1" />Newsletters</TabsTrigger>
          <TabsTrigger value="digest" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-xs"><Newspaper className="w-3 h-3 mr-1" />Edicion semanal</TabsTrigger>
        </TabsList>

        {/* ═══ DASHBOARD ═══ */}
        <TabsContent value="dashboard">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
            {[
              { l: 'Fuentes activas', v: activeSources, c: 'text-blue-400' },
              { l: 'Items pendientes', v: h.items?.new || 0, c: 'text-amber-400' },
              { l: 'Aprobados', v: h.items?.approved || 0, c: 'text-emerald-400' },
              { l: 'Ediciones', v: h.digests?.total || 0, c: 'text-violet-400' },
            ].map(k => (
              <Card key={k.l} className="bg-zinc-900 border-zinc-800"><CardContent className="p-4">
                <p className="text-[9px] uppercase tracking-[0.12em] text-zinc-500">{k.l}</p>
                <p className={`text-2xl font-bold font-mono mt-1 ${k.c}`}>{k.v}</p>
              </CardContent></Card>
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-1 pt-3 px-4"><CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500">Actividad reciente</CardTitle></CardHeader>
              <CardContent className="px-4 pb-3 space-y-1">
                {jobs.slice(0, 6).map(j => (
                  <div key={j.job_id} className="flex items-center gap-2 py-1">
                    {j.status === 'completed' ? <CheckCircle className="w-3 h-3 text-emerald-400 shrink-0" /> : j.status === 'failed' ? <XCircle className="w-3 h-3 text-rose-400 shrink-0" /> : <Loader2 className="w-3 h-3 text-blue-400 animate-spin shrink-0" />}
                    <span className="text-[11px] text-zinc-300 truncate flex-1">{j.source_name}</span>
                    <span className="text-[10px] font-mono text-emerald-400">{j.items_new || 0} nuevos</span>
                    <span className="text-[10px] text-zinc-600 font-mono">{fmtDate(j.created_at) || '—'}</span>
                  </div>
                ))}
                {jobs.length === 0 && <p className="text-xs text-zinc-600 py-4 text-center">Sin actividad</p>}
              </CardContent>
            </Card>
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-1 pt-3 px-4"><CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500">Salud de fuentes</CardTitle></CardHeader>
              <CardContent className="px-4 pb-3 space-y-1">
                {sources.slice(0, 8).map(s => (
                  <div key={s.source_id} className="flex items-center gap-2 py-0.5">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${s.active ? (s.last_error ? 'bg-rose-500' : 'bg-emerald-500') : 'bg-zinc-600'}`} />
                    <span className="text-[11px] text-zinc-300 truncate flex-1">{s.name}</span>
                    <span className="text-[10px] text-zinc-500">{s.total_items_generated || 0}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ═══ FUENTES ═══ */}
        <TabsContent value="sources">
          <div className="flex items-center justify-between mb-3">
            <div className="flex gap-1.5">
              <Tooltip><TooltipTrigger asChild>
                <Button size="sm" variant="outline" onClick={handleBulkActivate} disabled={!!actionLoading} className="border-zinc-700 text-zinc-300 h-7 text-[10px]"><Zap className="w-3 h-3 mr-1" />Activar todas</Button>
              </TooltipTrigger><TooltipContent className="bg-zinc-800 text-zinc-200 text-xs border-zinc-700">Activa todas las fuentes para que puedan usarse en scrapeos</TooltipContent></Tooltip>
              <Tooltip><TooltipTrigger asChild>
                <Button size="sm" variant="outline" onClick={handleBulkDeactivate} disabled={!!actionLoading} className="border-zinc-700 text-zinc-300 h-7 text-[10px]"><PauseCircle className="w-3 h-3 mr-1" />Desactivar todas</Button>
              </TooltipTrigger><TooltipContent className="bg-zinc-800 text-zinc-200 text-xs border-zinc-700">Desactiva todas las fuentes</TooltipContent></Tooltip>
              <Tooltip><TooltipTrigger asChild>
                <Button size="sm" variant="outline" onClick={handleBulkCrawl} disabled={!!actionLoading} className="border-zinc-700 text-zinc-300 h-7 text-[10px]">
                  {actionLoading === 'bulk-crawl' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Play className="w-3 h-3 mr-1" />}Scrapear todas ({activeSources})
                </Button>
              </TooltipTrigger><TooltipContent className="bg-zinc-800 text-zinc-200 text-xs border-zinc-700">Lanza un scrapeo manual sobre todas las fuentes activas</TooltipContent></Tooltip>
            </div>
            <Button size="sm" onClick={() => setShowAddSource(true)} className="bg-blue-600 hover:bg-blue-500 text-white"><Plus className="w-3.5 h-3.5 mr-1" />Anadir fuente</Button>
          </div>
          <div className="rounded border border-zinc-800 overflow-hidden">
            <Table><TableHeader><TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900">
              <TableHead className="text-[9px] uppercase tracking-wider text-zinc-500 py-1.5">Fuente</TableHead>
              <TableHead className="text-[9px] uppercase tracking-wider text-zinc-500 py-1.5 w-16">Tipo</TableHead>
              <TableHead className="text-[9px] uppercase tracking-wider text-zinc-500 py-1.5 w-14">Estado</TableHead>
              <TableHead className="text-[9px] uppercase tracking-wider text-zinc-500 py-1.5 w-14">Items</TableHead>
              <TableHead className="text-[9px] uppercase tracking-wider text-zinc-500 py-1.5 w-24">Ultimo scrapeo</TableHead>
              <TableHead className="text-[9px] uppercase tracking-wider text-zinc-500 py-1.5 w-20">Acciones</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {sources.map(s => (
                <TableRow key={s.source_id} className="border-zinc-800 hover:bg-zinc-800/20">
                  <TableCell className="py-1.5">
                    <p className="text-xs text-zinc-100 font-medium">{s.name}</p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className="text-[8px] text-zinc-500 truncate max-w-[120px]">{s.domain}</span>
                      {s.rss_validated && <Badge className="text-[7px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1 py-0">RSS</Badge>}
                      {s.ingestion_mode === 'html_only' && <Badge className="text-[7px] bg-zinc-500/10 text-zinc-400 border border-zinc-500/20 px-1 py-0">HTML</Badge>}
                    </div>
                  </TableCell>
                  <TableCell className="py-1.5"><Badge variant="outline" className="text-[8px] text-zinc-300 border-zinc-600">{s.source_type}</Badge></TableCell>
                  <TableCell className="py-1.5">{s.active ? <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" title="Activa" /> : s.status === 'archived' ? <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" title="Archivada" /> : <span className="w-2.5 h-2.5 rounded-full bg-zinc-600 inline-block" title="Inactiva" />}</TableCell>
                  <TableCell className="py-1.5 text-xs font-mono text-zinc-300">{s.total_items_generated || 0}</TableCell>
                  <TableCell className="py-1.5 text-[9px] text-zinc-500 font-mono">{fmtDate(s.last_crawled_at) || '—'}</TableCell>
                  <TableCell className="py-1.5"><div className="flex gap-0.5">
                    <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="sm" className="h-5 px-1 text-zinc-400 hover:text-blue-400" onClick={() => handleCrawl(s.source_id)} disabled={!!actionLoading}><Play className="w-3 h-3" /></Button></TooltipTrigger>
                      <TooltipContent className="bg-zinc-800 text-zinc-200 text-xs border-zinc-700">Ejecutar scrapeo manual</TooltipContent></Tooltip>
                    <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="sm" className="h-5 px-1 text-zinc-400 hover:text-emerald-400"
                      onClick={async () => { await api.post(`/editorial/sources/${s.source_id}/${s.active ? 'deactivate' : 'activate'}`); fetchAll(); }}><CheckCircle className="w-3 h-3" /></Button></TooltipTrigger>
                      <TooltipContent className="bg-zinc-800 text-zinc-200 text-xs border-zinc-700">{s.active ? 'Desactivar' : 'Activar'}</TooltipContent></Tooltip>
                    <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="sm" className="h-5 px-1 text-zinc-400 hover:text-cyan-400"
                      onClick={async () => { try { const r = await api.post(`/editorial/sources/${s.source_id}/analyze`); toast.success(`Analizado: ${r.data.detection_reason}`); fetchAll(); } catch (_) { toast.error('Error'); } }}><Eye className="w-3 h-3" /></Button></TooltipTrigger>
                      <TooltipContent className="bg-zinc-800 text-zinc-200 text-xs border-zinc-700">Analizar metodo de ingestion</TooltipContent></Tooltip>
                    <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="sm" className="h-5 px-1 text-zinc-400 hover:text-rose-400"
                      onClick={async () => { if (window.confirm('Archivar esta fuente?')) { await api.post(`/editorial/sources/${s.source_id}/archive`); fetchAll(); } }}><XCircle className="w-3 h-3" /></Button></TooltipTrigger>
                      <TooltipContent className="bg-zinc-800 text-zinc-200 text-xs border-zinc-700">Archivar fuente</TooltipContent></Tooltip>
                  </div></TableCell>
                </TableRow>))}
            </TableBody></Table>
          </div>
          <Dialog open={showAddSource} onOpenChange={setShowAddSource}>
            <DialogContent className="bg-zinc-900 border-zinc-700 max-w-lg">
              <DialogHeader><DialogTitle className="text-zinc-50 font-heading">Anadir fuente</DialogTitle></DialogHeader>
              <div className="space-y-3 pt-2">
                <div className="space-y-1"><Label className="text-zinc-400 text-xs">Nombre</Label><Input value={srcName} onChange={e => setSrcName(e.target.value)} placeholder="MarketingDirecto" className="bg-zinc-950 border-zinc-700 text-zinc-50" /></div>
                <div className="space-y-1"><Label className="text-zinc-400 text-xs">URL</Label><div className="flex gap-2"><Input value={srcUrl} onChange={e => setSrcUrl(e.target.value)} placeholder="https://..." className="bg-zinc-950 border-zinc-700 text-zinc-50 flex-1" /><Button variant="outline" size="sm" onClick={handleTestUrl} disabled={testing} className="border-zinc-700 text-zinc-300 shrink-0">{testing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Eye className="w-3 h-3" />} Probar</Button></div></div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1"><Label className="text-zinc-400 text-xs">Tipo</Label><Select value={srcType} onValueChange={setSrcType}><SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200"><SelectValue /></SelectTrigger><SelectContent className="bg-zinc-900 border-zinc-700">{['rss','html','press_room'].map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select></div>
                  <div className="space-y-1"><Label className="text-zinc-400 text-xs">Frecuencia</Label><Select value={srcFreq} onValueChange={setSrcFreq}><SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200"><SelectValue /></SelectTrigger><SelectContent className="bg-zinc-900 border-zinc-700">{['6h','12h','24h','48h'].map(f => <SelectItem key={f} value={f}>{f}</SelectItem>)}</SelectContent></Select></div>
                </div>
                {testResult && (<Card className={`border ${testResult.accessible ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-rose-500/30 bg-rose-500/5'}`}><CardContent className="p-3 text-xs"><p className={testResult.accessible ? 'text-emerald-400' : 'text-rose-400'}>{testResult.accessible ? 'Accesible' : 'No accesible'} — {testResult.detected_type}</p>{testResult.items_preview?.slice(0, 3).map((it, i) => <p key={i} className="text-zinc-300 truncate mt-1">{it.title_raw}</p>)}</CardContent></Card>)}
                <Button onClick={handleAddSource} className="w-full bg-blue-600 hover:bg-blue-500 text-white">Crear fuente</Button>
              </div>
            </DialogContent>
          </Dialog>
        </TabsContent>

        {/* ═══ ITEMS ═══ */}
        <TabsContent value="items">
          <div className="flex items-center gap-3 mb-3">
            <div className="flex gap-1 bg-zinc-900 border border-zinc-800 rounded p-0.5">
              <Button size="sm" variant={iView === 'pending' ? 'default' : 'ghost'} onClick={() => { setIView('pending'); setIOffset(0); }} className={`h-7 text-xs ${iView === 'pending' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400'}`}><Inbox className="w-3 h-3 mr-1" />Pendientes</Button>
              <Button size="sm" variant={iView === 'all' ? 'default' : 'ghost'} onClick={() => { setIView('all'); setIOffset(0); }} className={`h-7 text-xs ${iView === 'all' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400'}`}><Archive className="w-3 h-3 mr-1" />Todos</Button>
            </div>
            <Input value={iSearch} onChange={e => { setISearch(e.target.value); setIOffset(0); }} placeholder="Buscar..." className="bg-zinc-950 border-zinc-700 text-zinc-50 h-7 text-xs flex-1" />
            <Select value={iSection} onValueChange={v => { setISection(v); setIOffset(0); }}>
              <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-7 text-xs w-44"><SelectValue placeholder="Seccion" /></SelectTrigger>
              <SelectContent className="bg-zinc-900 border-zinc-700"><SelectItem value="all">Todas las secciones</SelectItem>{Object.entries(SL).map(([k, v]) => <SelectItem key={k} value={k}>{v.l} {v.e}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <p className="text-[10px] text-zinc-500 mb-1.5">{itemsTotal} {iView === 'pending' ? 'pendientes de revision' : 'items en total'}</p>
          <div className="space-y-1.5">
            {items.length === 0 && <Card className="bg-zinc-900 border-zinc-800"><CardContent className="p-8 text-center text-zinc-500 text-xs">{iView === 'pending' ? 'Todo revisado. Sin items pendientes.' : 'Sin items.'}</CardContent></Card>}
            {items.map(it => (
              <Card key={it.item_id} className="bg-zinc-900 border-zinc-800 hover:border-zinc-700 transition-colors">
                <CardContent className="p-3">
                  <div className="flex items-start gap-3">
                    {/* Left: category + dates */}
                    <div className="w-32 shrink-0 pt-0.5">
                      {/* AI suggested category (read-only label) */}
                      <p className="text-[7px] text-zinc-600 text-center mb-0.5">IA: {SL[it.ai_suggested_category || it.section_primary]?.l || it.section_primary}</p>
                      {/* Editable editorial category dropdown */}
                      <Select value={it.editorial_category || it.section_primary || 'noticias_semana'}
                        onValueChange={async (v) => {
                          try {
                            await api.put(`/editorial/items/${it.item_id}`, { editorial_category: v });
                            fetchItems(); fetchAll();
                          } catch (_) {}
                        }}>
                        <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-6 text-[8px] w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-zinc-900 border-zinc-700 max-h-64">
                          {Object.entries(SL).map(([k, v]) => <SelectItem key={k} value={k} className="text-[9px]">{v.l} {v.e}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      {/* Dates: published + scraped */}
                      <div className="mt-1.5 text-center">
                        {it.published_at ? (
                          <p className="text-[11px] text-zinc-100 font-mono font-bold">{fmtDate(it.published_at)}</p>
                        ) : it.news_date ? (
                          <p className="text-[11px] text-zinc-200 font-mono">{fmtDate(it.news_date)}</p>
                        ) : (
                          <p className="text-[10px] text-zinc-500 italic">Fecha no detectada</p>
                        )}
                        {!it.date_reliable && it.date_reliable !== undefined && (
                          <p className="text-[7px] text-amber-500 mt-0.5">fecha estimada</p>
                        )}
                        <p className="text-[7px] text-zinc-600 mt-0.5">Scrapeado: {fmtDate(it.fetched_at) || '—'}</p>
                      </div>
                    </div>
                    {/* Center: title + translation + metadata */}
                    <div className="flex-1 min-w-0">
                      {/* Title: show translation if English */}
                      {it.title_language === 'en' && it.title_translated_es ? (
                        <>
                          <p className="text-[13px] text-zinc-50 font-medium leading-snug">{it.title_translated_es}</p>
                          <p className="text-[10px] text-zinc-500 mt-0.5 italic">EN: {it.title_raw || it.title_clean}</p>
                        </>
                      ) : it.title_language === 'en' && !it.title_translated_es ? (
                        <>
                          <p className="text-[13px] text-zinc-50 font-medium leading-snug">{it.editorial_bullet || it.title_clean}</p>
                          <Button size="sm" variant="ghost" className="h-4 text-[8px] text-blue-400 mt-0.5 px-0"
                            onClick={async () => {
                              try {
                                const r = await api.post(`/editorial/items/${it.item_id}/translate`);
                                if (r.data.translated) { toast.success('Traducido'); fetchItems(); fetchAll(); }
                                else toast.error('No se pudo traducir');
                              } catch (_) { toast.error('Error'); }
                            }}>Traducir al espanol</Button>
                        </>
                      ) : (
                        <p className="text-[13px] text-zinc-50 font-medium leading-snug">{it.editorial_bullet || it.title_clean}</p>
                      )}
                      <div className="flex items-center gap-3 mt-1.5">
                        <span className="text-[10px] text-zinc-500">{it.source_name}</span>
                        {it.action_detected && <Badge variant="outline" className="text-[8px] text-zinc-400 border-zinc-700 px-1.5 py-0">{it.action_detected}</Badge>}
                        {it.url && <a href={it.url} target="_blank" rel="noopener noreferrer" className="text-[9px] text-blue-400 hover:text-blue-300 flex items-center gap-0.5"><ExternalLink className="w-2.5 h-2.5" />ver fuente</a>}
                        {it.category_changed_by_user && <Badge variant="outline" className="text-[7px] text-amber-400 border-amber-500/20">categoria editada</Badge>}
                      </div>
                    </div>
                    {/* Right: actions */}
                    <div className="flex flex-col gap-1 shrink-0">
                      {it.status === 'new' && (<>
                        <Tooltip><TooltipTrigger asChild><Button size="sm" className="h-6 px-2 text-[10px] bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30" onClick={() => handleItemAction(it.item_id, 'approve')}><CheckCircle className="w-3 h-3 mr-1" />Aprobar</Button></TooltipTrigger>
                          <TooltipContent className="bg-zinc-800 text-zinc-200 text-xs border-zinc-700">Aprobar este item para la edicion semanal</TooltipContent></Tooltip>
                        <Tooltip><TooltipTrigger asChild><Button size="sm" variant="ghost" className="h-6 px-2 text-[10px] text-zinc-500 hover:text-rose-400" onClick={() => handleItemAction(it.item_id, 'discard')}><XCircle className="w-3 h-3 mr-1" />Descartar</Button></TooltipTrigger>
                          <TooltipContent className="bg-zinc-800 text-zinc-200 text-xs border-zinc-700">Descartar este item</TooltipContent></Tooltip>
                      </>)}
                      {it.status === 'approved' && activeDigest && (
                        <Button size="sm" className="h-6 px-2 text-[10px] bg-blue-600/20 text-blue-400 hover:bg-blue-600/30" onClick={() => addToDigest(it.item_id)}><Bookmark className="w-3 h-3 mr-1" />Edicion</Button>
                      )}
                      {it.status !== 'new' && <Badge className={`text-[7px] border ${it.status === 'approved' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : it.status === 'discarded' ? 'bg-zinc-700/30 text-zinc-500 border-zinc-600/20' : 'bg-blue-500/10 text-blue-400 border-blue-500/20'}`}>{it.status === 'approved' ? 'Aprobado' : it.status === 'discarded' ? 'Descartado' : it.status === 'added_to_digest' ? 'En edicion' : it.status}</Badge>}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          {itemsTotal > 40 && <div className="flex justify-between mt-2"><span className="text-[10px] text-zinc-500">{iOffset + 1}-{Math.min(iOffset + 40, itemsTotal)} de {itemsTotal}</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={iOffset === 0} onClick={() => setIOffset(o => Math.max(0, o - 40))} className="border-zinc-700 text-zinc-300 h-6 text-xs"><ChevronLeft className="w-3 h-3" /></Button><Button variant="outline" size="sm" disabled={iOffset + 40 >= itemsTotal} onClick={() => setIOffset(o => o + 40)} className="border-zinc-700 text-zinc-300 h-6 text-xs"><ChevronRight className="w-3 h-3" /></Button></div></div>}
        </TabsContent>

        {/* ═══ NEWSLETTERS EMAIL ═══ */}
        <TabsContent value="email">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-zinc-400">Ingestión de newsletters por email (editorial@wearebudadvisors.com)</p>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300 h-7 text-[10px]"
                  onClick={async () => { try { const r = await api.get('/editorial/email/status'); toast.success(r.data.connected ? `Conectado (${r.data.inbox_count} emails)` : `Error: ${r.data.error}`); } catch (_) { toast.error('Error de conexion'); } }}>
                  <Eye className="w-3 h-3 mr-1" />Comprobar conexion
                </Button>
                <Button size="sm" className="bg-blue-600 hover:bg-blue-500 text-white h-7 text-[10px]"
                  onClick={async () => {
                    setActionLoading('email-sync');
                    try { const r = await api.post('/editorial/email/sync?max_emails=20'); toast.success(`Sincronizado: ${r.data.new} nuevos, ${r.data.items_created} items creados`); fetchAll(); }
                    catch (_) { toast.error('Error de sincronizacion'); }
                    finally { setActionLoading(null); }
                  }} disabled={actionLoading === 'email-sync'}>
                  {actionLoading === 'email-sync' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Download className="w-3 h-3 mr-1" />}
                  Sincronizar newsletters
                </Button>
              </div>
            </div>
            <Card className="bg-zinc-900 border-zinc-800">
              <CardContent className="p-6 text-center text-zinc-400 text-xs">
                <Globe className="w-8 h-8 mx-auto text-zinc-600 mb-2" />
                <p>Reenvia newsletters a <span className="text-zinc-200 font-mono">editorial@wearebudadvisors.com</span></p>
                <p className="mt-1">Pulsa "Sincronizar newsletters" para importar los enlaces detectados como items editoriales.</p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ═══ EDICION SEMANAL ═══ */}
        <TabsContent value="digest">
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
            <div className="lg:col-span-2 space-y-3">
              <Button size="sm" onClick={() => setShowNewDigest(true)} className="bg-blue-600 hover:bg-blue-500 text-white w-full"><Plus className="w-3.5 h-3.5 mr-1" />Nueva edicion</Button>
              {digests.map(d => (
                <Card key={d.digest_id} className={`bg-zinc-900 border-zinc-800 cursor-pointer hover:border-zinc-600 ${activeDigest?.digest_id === d.digest_id ? 'border-blue-500/50' : ''}`}
                  onClick={async () => { const r = await api.get(`/editorial/digests/${d.digest_id}`); setActiveDigest(r.data); setDigestOutput(null); }}>
                  <CardContent className="p-3"><p className="text-xs font-medium text-zinc-100">{d.title}</p><div className="flex gap-2 mt-1 text-[9px] text-zinc-500"><span>{d.week_label}</span><Badge className={`text-[7px] border ${d.status === 'generated' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20'}`}>{d.status === 'generated' ? 'Generado' : 'Borrador'}</Badge><span>{(d.selected_item_ids || []).length} items</span></div></CardContent></Card>
              ))}
              {activeDigest && approvedItems.length > 0 && (
                <Card className="bg-zinc-900 border-zinc-800">
                  <CardHeader className="pb-1 pt-3 px-4"><CardTitle className="text-[9px] uppercase tracking-[0.1em] text-emerald-400">Aprobados disponibles ({approvedItems.filter(it => !(activeDigest.selected_item_ids || []).includes(it.item_id)).length})</CardTitle></CardHeader>
                  <CardContent className="px-4 pb-3 space-y-1">
                    {approvedItems.filter(it => !(activeDigest.selected_item_ids || []).includes(it.item_id)).slice(0, 15).map(it => (
                      <div key={it.item_id} className="flex items-center gap-2 py-0.5">
                        <span className="text-[10px] text-zinc-300 truncate flex-1">{it.editorial_bullet || it.title_clean}</span>
                        <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="sm" className="h-5 w-5 p-0 text-zinc-500 hover:text-blue-400 shrink-0" onClick={() => addToDigest(it.item_id)}><Plus className="w-3 h-3" /></Button></TooltipTrigger>
                          <TooltipContent className="bg-zinc-800 text-zinc-200 text-xs border-zinc-700">Anadir a la edicion</TooltipContent></Tooltip>
                      </div>))}
                  </CardContent>
                </Card>
              )}
            </div>
            <div className="lg:col-span-3">
              {activeDigest ? (
                <Card className="bg-zinc-900 border-zinc-800">
                  <CardHeader className="pb-2 pt-3 px-4">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-heading text-zinc-100">{activeDigest.title}</CardTitle>
                      <Button size="sm" onClick={() => handleGenerateOutput(activeDigest.digest_id)} className="bg-emerald-600 hover:bg-emerald-500 text-white"><Download className="w-3 h-3 mr-1" />Generar salida</Button>
                    </div>
                  </CardHeader>
                  <CardContent className="px-4 pb-4 space-y-3">
                    <p className="text-[10px] text-zinc-400">{activeDigest.week_label} — {(activeDigest.selected_item_ids || []).length} items seleccionados</p>

                    {/* Intro editor */}
                    <div className="space-y-1">
                      <Label className="text-zinc-500 text-[9px] uppercase tracking-wider">Cabecera / Intro</Label>
                      <Textarea value={activeDigest.intro_text || ''} rows={4}
                        onChange={e => setActiveDigest(p => ({...p, intro_text: e.target.value}))}
                        onBlur={() => api.put(`/editorial/digests/${activeDigest.digest_id}`, { intro_text: activeDigest.intro_text })}
                        className="bg-zinc-950 border-zinc-700 text-zinc-200 text-[11px] leading-relaxed" />
                    </div>

                    {/* Items in digest */}
                    {activeDigest.items?.length > 0 && (<div className="space-y-1">{activeDigest.items.map(it => (
                      <div key={it.item_id} className="flex items-center gap-2 py-1 px-2 rounded bg-zinc-800/30">
                        <Badge className={`text-[6px] border shrink-0 ${SL[it.section_primary]?.c || ''}`}>{(SL[it.section_primary]?.l || '').substring(0, 15)}</Badge>
                        <span className="text-[10px] text-zinc-200 truncate flex-1">{it.editorial_bullet || it.title_clean}</span>
                      </div>))}</div>)}

                    {/* Manual blocks */}
                    <Separator className="bg-zinc-800" />
                    <p className="text-[9px] uppercase tracking-[0.12em] text-zinc-500">Bloques manuales</p>
                    <div className="space-y-2">
                      <div className="space-y-1">
                        <Label className="text-zinc-400 text-[10px]">La mirada de Control 🧭 <span className="text-zinc-600">(opcional)</span></Label>
                        <Textarea rows={3} placeholder="Escribe aqui el contenido de La mirada de Control..."
                          value={activeDigest.manual_blocks?.mirada_control || ''}
                          onChange={e => setActiveDigest(p => ({...p, manual_blocks: {...(p.manual_blocks||{}), mirada_control: e.target.value}}))}
                          onBlur={() => api.put(`/editorial/digests/${activeDigest.digest_id}`, { manual_blocks: activeDigest.manual_blocks })}
                          className="bg-zinc-950 border-zinc-700 text-zinc-200 text-[11px]" />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-zinc-400 text-[10px]">Palabra de Dani 💬 <span className="text-zinc-600">(opcional)</span></Label>
                        <Textarea rows={3} placeholder="Escribe aqui tu reflexion semanal..."
                          value={activeDigest.manual_blocks?.palabra_de_dani || ''}
                          onChange={e => setActiveDigest(p => ({...p, manual_blocks: {...(p.manual_blocks||{}), palabra_de_dani: e.target.value}}))}
                          onBlur={() => api.put(`/editorial/digests/${activeDigest.digest_id}`, { manual_blocks: activeDigest.manual_blocks })}
                          className="bg-zinc-950 border-zinc-700 text-zinc-200 text-[11px]" />
                      </div>
                    </div>

                    {/* Output */}
                    {digestOutput && (<>
                      <Separator className="bg-zinc-800" />
                      <div className="space-y-2">
                        <p className="text-[9px] uppercase tracking-[0.12em] text-zinc-500">Salida para Substack</p>
                        <div className="bg-zinc-950 border border-zinc-800 rounded p-4 text-[12px] text-zinc-200 max-h-[350px] overflow-y-auto leading-relaxed [&_h3]:text-[13px] [&_h3]:font-bold [&_h3]:text-zinc-100 [&_h3]:mt-3 [&_h3]:mb-1.5 [&_a]:text-blue-400 [&_a]:underline [&_hr]:border-zinc-700 [&_hr]:my-3" dangerouslySetInnerHTML={{ __html: digestOutput.html }} />
                        <div className="flex gap-2">
                          <Tooltip><TooltipTrigger asChild>
                            <Button size="sm" className="bg-blue-600 hover:bg-blue-500 text-white" onClick={() => copyHtmlToClipboard(digestOutput.html)}>
                              <Copy className="w-3 h-3 mr-1.5" />Copiar para Substack
                            </Button>
                          </TooltipTrigger><TooltipContent className="bg-zinc-800 text-zinc-200 text-xs border-zinc-700">Copia HTML con enlaces embebidos listo para pegar en Substack</TooltipContent></Tooltip>
                          <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300" onClick={() => { navigator.clipboard.writeText(digestOutput.markdown); toast.success('Markdown copiado'); }}>Copiar Markdown</Button>
                        </div>
                      </div>
                    </>)}
                  </CardContent>
                </Card>
              ) : <Card className="bg-zinc-900 border-zinc-800"><CardContent className="p-10 text-center text-zinc-500 text-xs">Selecciona o crea una edicion</CardContent></Card>}
            </div>
          </div>
          <Dialog open={showNewDigest} onOpenChange={setShowNewDigest}>
            <DialogContent className="bg-zinc-900 border-zinc-700">
              <DialogHeader><DialogTitle className="text-zinc-50 font-heading">Nueva edicion</DialogTitle></DialogHeader>
              <div className="space-y-3 pt-2">
                <div className="grid grid-cols-2 gap-3"><div className="space-y-1"><Label className="text-zinc-400 text-xs">Semana</Label><Input value={digWeek} onChange={e => setDigWeek(e.target.value)} placeholder="S16 2026" className="bg-zinc-950 border-zinc-700 text-zinc-50" /></div><div className="space-y-1"><Label className="text-zinc-400 text-xs">Titulo</Label><Input value={digTitle} onChange={e => setDigTitle(e.target.value)} placeholder="Digest semanal" className="bg-zinc-950 border-zinc-700 text-zinc-50" /></div></div>
                <div className="space-y-1"><Label className="text-zinc-400 text-xs">Intro</Label><Textarea value={digIntro} onChange={e => setDigIntro(e.target.value)} rows={3} placeholder="Esta semana..." className="bg-zinc-950 border-zinc-700 text-zinc-50" /></div>
                <Button onClick={handleCreateDigest} className="w-full bg-blue-600 hover:bg-blue-500 text-white">Crear edicion</Button>
              </div>
            </DialogContent>
          </Dialog>
        </TabsContent>
      </Tabs>
    </div>
    </TooltipProvider>
  );
}
