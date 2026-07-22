import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Loader2, Search, CheckCircle, Shield, RefreshCw, Layers, History, AlertTriangle, Globe, ChevronLeft, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';

function fmtDate(iso) { if (!iso) return '—'; const [y, m, d] = (iso || '').substring(0, 10).split('-'); return d && m && y ? `${d}/${m}/${y}` : iso?.substring(0, 10); }

const MS_BADGE = {
  discovered: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  auto_merged: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  verified: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  conflict: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
};

export default function MasterEntitiesPage() {
  const [tab, setTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [entities, setEntities] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [conflicts, setConflicts] = useState([]);
  const [conflictsTotal, setConflictsTotal] = useState(0);
  const [pipeline, setPipeline] = useState(null);

  const fetchStats = useCallback(async () => {
    try { const r = await api.get('/master/stats'); setStats(r.data); } catch (_) {}
    finally { setLoading(false); }
  }, []);

  const fetchEntities = useCallback(async () => {
    const params = { limit: 50, search: search || undefined };
    if (statusFilter !== 'all') params.merge_status = statusFilter;
    try { const r = await api.get('/master', { params }); setEntities(r.data.companies || []); setTotal(r.data.total || 0); } catch (_) {}
  }, [search, statusFilter]);

  const fetchAudit = useCallback(async () => {
    try { const r = await api.get('/master/audit-log', { params: { limit: 100 } }); setAuditLogs(r.data.logs || []); setAuditTotal(r.data.total || 0); } catch (_) {}
  }, []);

  const fetchConflicts = useCallback(async () => {
    try { const r = await api.get('/master/conflicts'); setConflicts(r.data.conflicts || []); setConflictsTotal(r.data.total || 0); } catch (_) {}
  }, []);

  const fetchPipeline = useCallback(async () => {
    try { const r = await api.get('/master/pipeline'); setPipeline(r.data); } catch (_) {}
  }, []);

  useEffect(() => { fetchStats(); }, [fetchStats]);
  useEffect(() => { if (tab === 'entities') fetchEntities(); }, [tab, fetchEntities]);
  useEffect(() => { if (tab === 'audit') fetchAudit(); }, [tab, fetchAudit]);
  useEffect(() => { if (tab === 'conflicts') fetchConflicts(); }, [tab, fetchConflicts]);
  useEffect(() => { if (tab === 'pipeline') fetchPipeline(); }, [tab, fetchPipeline]);

  const refreshAll = () => { fetchStats(); fetchEntities(); };

  const s = stats || {};

  return (
    <div className="space-y-4" data-testid="master-entities-page">
      <div>
        <h1 className="text-xl font-bold tracking-tight text-zinc-50 font-heading">Master Entities</h1>
        <p className="text-xs text-zinc-400">Entidades canonicas resueltas — fuente de verdad para Valuo</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800 p-1 flex-wrap h-auto gap-0.5">
          <TabsTrigger value="overview" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><Layers className="w-3 h-3 mr-1" />Overview</TabsTrigger>
          <TabsTrigger value="entities" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><Search className="w-3 h-3 mr-1" />Entidades</TabsTrigger>
          <TabsTrigger value="conflicts" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><AlertTriangle className="w-3 h-3 mr-1" />Conflicts{conflictsTotal > 0 ? ` (${conflictsTotal})` : ''}</TabsTrigger>
          <TabsTrigger value="pipeline" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><Shield className="w-3 h-3 mr-1" />Pipeline</TabsTrigger>
          <TabsTrigger value="audit" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400 text-[10px]"><History className="w-3 h-3 mr-1" />Audit Trail</TabsTrigger>
        </TabsList>

        {/* OVERVIEW */}
        <TabsContent value="overview">
          {loading ? <Loader2 className="w-5 h-5 animate-spin text-zinc-400 mx-auto mt-8" /> : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {[
                  ['Total entidades', s.total, 'text-zinc-100'],
                  ['Discovered', s.discovered, 'text-zinc-400'],
                  ['Auto-merged', s.auto_merged, 'text-blue-400'],
                  ['Verificadas', s.verified, 'text-emerald-400'],
                  ['Conflictos', s.conflict, s.conflict > 0 ? 'text-rose-400' : 'text-zinc-500'],
                  ['Con CIF', s.with_cif, 'text-zinc-300'],
                  ['Publicadas Valuo', s.published_to_valuo, 'text-cyan-400'],
                  ['Pendientes pub.', s.pending_publication, s.pending_publication > 0 ? 'text-amber-400' : 'text-zinc-500'],
                ].map(([l, v, c]) => (
                  <Card key={l} className="bg-zinc-900 border-zinc-800"><CardContent className="p-3">
                    <p className="text-[8px] uppercase text-zinc-500">{l}</p>
                    <p className={`text-xl font-bold font-mono ${c}`}>{v ?? 0}</p>
                  </CardContent></Card>
                ))}
              </div>

              {/* Quick actions */}
              <Card className="bg-zinc-900 border-zinc-800"><CardContent className="p-3">
                <p className="text-[9px] uppercase text-zinc-500 font-semibold mb-2">Acciones rapidas</p>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300 text-[10px] h-7" disabled={actionLoading === 'ingest'}
                    onClick={async () => { setActionLoading('ingest'); try { const r = await api.post('/master/ingest-all-scraper'); toast.success(`Ingestados: ${r.data.created} nuevos, ${r.data.merged} merged`); refreshAll(); } catch (_) { toast.error('Error'); } finally { setActionLoading(null); } }}>
                    <RefreshCw className="w-3 h-3 mr-1" />{actionLoading === 'ingest' ? 'Procesando...' : 'Ingestar scraper'}
                  </Button>
                  <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300 text-[10px] h-7" disabled={actionLoading === 'verify'}
                    onClick={async () => { setActionLoading('verify'); try { const r = await api.post('/master/bulk-verify'); toast.success(`${r.data.count} verificadas`); refreshAll(); } catch (_) { toast.error('Error'); } finally { setActionLoading(null); } }}>
                    <CheckCircle className="w-3 h-3 mr-1" />{actionLoading === 'verify' ? 'Verificando...' : 'Bulk verify'}
                  </Button>
                  <Button size="sm" className="bg-cyan-600/20 text-cyan-400 text-[10px] h-7" disabled={actionLoading === 'publish'}
                    onClick={async () => { setActionLoading('publish'); try { const r = await api.post('/master/bulk-publish-to-valuo'); toast.success(`${r.data.count} publicadas a Valuo`); refreshAll(); } catch (_) { toast.error('Error'); } finally { setActionLoading(null); } }}>
                    <Shield className="w-3 h-3 mr-1" />{actionLoading === 'publish' ? 'Publicando...' : 'Publicar en Valuo'}
                  </Button>
                </div>
              </CardContent></Card>

              {/* Valuo requests */}
              {(s.valuo_requests || 0) > 0 && (
                <Card className="bg-zinc-900 border-zinc-800"><CardContent className="p-3">
                  <p className="text-[9px] uppercase text-zinc-500 font-semibold mb-1">Solicitudes Valuo</p>
                  <p className="text-[10px] text-zinc-400">{s.valuo_requests} total, {s.valuo_requests_pending} pendientes</p>
                </CardContent></Card>
              )}
            </div>
          )}
        </TabsContent>

        {/* ENTITIES */}
        <TabsContent value="entities">
          <div className="flex gap-2 mb-3">
            <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar nombre, CIF, alias..." className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs flex-1" />
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-8 w-40 text-xs"><SelectValue placeholder="Estado" /></SelectTrigger>
              <SelectContent className="bg-zinc-900 border-zinc-700">
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="discovered">Discovered</SelectItem>
                <SelectItem value="auto_merged">Auto-merged</SelectItem>
                <SelectItem value="verified">Verified</SelectItem>
                <SelectItem value="conflict">Conflict</SelectItem>
              </SelectContent>
            </Select>
            <span className="text-[10px] text-zinc-500 self-center">{total}</span>
          </div>
          <div className="rounded border border-zinc-800 overflow-hidden">
            <Table><TableHeader><TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900">
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5">Nombre</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-24">CIF</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-28">Dominio</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-20">Estado</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Valuo</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Sources</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-20">Accion</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {entities.length === 0 && <TableRow><TableCell colSpan={7} className="text-center text-zinc-500 py-6 text-xs">Sin entidades</TableCell></TableRow>}
              {entities.map(e => (
                <TableRow key={e.master_company_id} className="border-zinc-800 cursor-pointer hover:bg-zinc-800/20" onClick={() => setDetailId(e.master_company_id)}>
                  <TableCell className="py-1">
                    <p className="text-xs text-zinc-100">{e.normalized_name || e.legal_name || '—'}</p>
                    {e.commercial_names?.length > 0 && <p className="text-[8px] text-zinc-500">{e.commercial_names.join(', ')}</p>}
                  </TableCell>
                  <TableCell className="py-1 text-[10px] font-mono text-zinc-400">{e.cif || '—'}</TableCell>
                  <TableCell className="py-1 text-[10px] text-zinc-400 truncate max-w-[110px]">{e.domain || '—'}</TableCell>
                  <TableCell className="py-1"><Badge className={`text-[7px] border ${MS_BADGE[e.merge_status] || MS_BADGE.discovered}`}>{e.merge_status}</Badge></TableCell>
                  <TableCell className="py-1">{e.published_to_valuo ? <CheckCircle className="w-3 h-3 text-cyan-400" /> : <span className="text-zinc-600 text-[10px]">—</span>}</TableCell>
                  <TableCell className="py-1 text-[10px] font-mono text-zinc-500">{e.source_trace?.length || 0}</TableCell>
                  <TableCell className="py-1" onClick={ev => ev.stopPropagation()}>
                    {e.merge_status !== 'verified' && (
                      <Button size="sm" variant="ghost" className="h-5 text-[8px] text-emerald-400" onClick={async () => {
                        await api.post(`/master/${e.master_company_id}/verify`); toast.success('Verificada'); fetchEntities(); fetchStats();
                      }}><CheckCircle className="w-3 h-3" /></Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody></Table>
          </div>
        </TabsContent>

        {/* CONFLICTS */}
        <TabsContent value="conflicts">
          <p className="text-[10px] text-zinc-500 mb-3">{conflictsTotal} entidades con conflictos o baja confianza</p>
          <div className="rounded border border-zinc-800 overflow-hidden">
            <Table><TableHeader><TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900">
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5">Entidad</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-28">Conflictos</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-16">Score</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-28">Signals</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-28">Acciones</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {conflicts.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-zinc-500 py-6 text-xs">Sin conflictos pendientes</TableCell></TableRow>}
              {conflicts.map(c => (
                <TableRow key={c.master_company_id} className="border-zinc-800">
                  <TableCell className="py-1.5">
                    <p className="text-xs text-zinc-100">{c.normalized_name || c.legal_name}</p>
                    <p className="text-[8px] text-zinc-500">{c.cif || '—'} · {c.domain || '—'}</p>
                  </TableCell>
                  <TableCell className="py-1.5">
                    <div className="flex flex-wrap gap-1">
                      {(c.conflict_types || []).map(ct => (
                        <Badge key={ct} className="text-[7px] border bg-rose-500/10 text-rose-400 border-rose-500/20">{ct.replace('_', ' ')}</Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="py-1.5 text-[11px] font-mono text-zinc-300">{(c.confidence_score || 0).toFixed(2)}</TableCell>
                  <TableCell className="py-1.5">
                    <div className="flex gap-1">
                      {(c.matching_signals || []).map((s, i) => (
                        <Badge key={i} variant="outline" className="text-[7px] text-zinc-400 border-zinc-700">{s.type}</Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="py-1.5">
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" className="h-5 text-[8px] text-emerald-400" onClick={async () => {
                        await api.post(`/master/conflicts/${c.master_company_id}/resolve?action=verify`);
                        toast.success('Verificada'); fetchConflicts(); fetchStats();
                      }}><CheckCircle className="w-3 h-3 mr-0.5" />Verify</Button>
                      <Button size="sm" variant="ghost" className="h-5 text-[8px] text-rose-400" onClick={async () => {
                        await api.post(`/master/conflicts/${c.master_company_id}/resolve?action=reject`);
                        toast.success('Rechazada'); fetchConflicts(); fetchStats();
                      }}>Reject</Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody></Table>
          </div>
        </TabsContent>

        {/* PIPELINE */}
        <TabsContent value="pipeline">
          {!pipeline ? <Loader2 className="w-4 h-4 animate-spin text-zinc-400 mx-auto mt-4" /> : (
            <div className="space-y-4">
              {/* Pipeline stages */}
              <div className="flex items-center gap-1">
                {pipeline.stages.map((stage, i) => {
                  const colors = { zinc: 'bg-zinc-700', blue: 'bg-blue-600', emerald: 'bg-emerald-600', rose: 'bg-rose-600', cyan: 'bg-cyan-600' };
                  const maxCount = Math.max(...pipeline.stages.map(s => s.count), 1);
                  const pct = Math.max(stage.count / maxCount * 100, stage.count > 0 ? 12 : 4);
                  return (
                    <div key={stage.key} className="text-center" style={{ flex: pct }}>
                      <div className={`${colors[stage.color] || 'bg-zinc-700'} h-12 rounded flex items-center justify-center`}>
                        <span className="text-[11px] font-bold text-white">{stage.count}</span>
                      </div>
                      <p className="text-[8px] text-zinc-500 mt-1 leading-tight">{stage.label}</p>
                    </div>
                  );
                })}
              </div>

              {/* Recent activity */}
              {pipeline.recent_activity?.length > 0 && (
                <Card className="bg-zinc-900 border-zinc-800"><CardContent className="p-3">
                  <p className="text-[9px] uppercase text-zinc-500 font-semibold mb-2">Actividad reciente</p>
                  <div className="space-y-0.5">
                    {pipeline.recent_activity.map((a, i) => (
                      <div key={i} className="flex items-center gap-2 text-[10px] py-0.5 border-b border-zinc-800/30">
                        <span className="text-zinc-500 font-mono w-20">{fmtDate(a.at)}</span>
                        <Badge variant="outline" className={`text-[7px] border-zinc-700 ${a.action?.includes('publish') ? 'text-cyan-400' : a.action?.includes('verif') ? 'text-emerald-400' : 'text-zinc-400'}`}>{a.action}</Badge>
                        <span className="text-zinc-400 font-mono">{a.entity}</span>
                        <span className="text-zinc-600 ml-auto">{a.by}</span>
                      </div>
                    ))}
                  </div>
                </CardContent></Card>
              )}
            </div>
          )}
        </TabsContent>

        {/* AUDIT TRAIL */}
        <TabsContent value="audit">
          <p className="text-[10px] text-zinc-500 mb-2">{auditTotal} registros de auditoria</p>
          <div className="rounded border border-zinc-800 overflow-hidden">
            <Table><TableHeader><TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900">
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-24">Fecha</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-28">Accion</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5">Entidad</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-20">Fuente</TableHead>
              <TableHead className="text-[8px] uppercase text-zinc-500 py-1.5 w-28">Usuario</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {auditLogs.map((l, i) => (
                <TableRow key={l.log_id || i} className="border-zinc-800">
                  <TableCell className="py-1 text-[9px] font-mono text-zinc-500">{fmtDate(l.timestamp)}</TableCell>
                  <TableCell className="py-1"><Badge variant="outline" className={`text-[7px] border-zinc-700 ${l.action?.includes('verified') || l.action?.includes('publish') ? 'text-emerald-400' : l.action?.includes('merge') ? 'text-blue-400' : 'text-zinc-400'}`}>{l.action}</Badge></TableCell>
                  <TableCell className="py-1 text-[9px] font-mono text-zinc-400 truncate max-w-[120px]">{l.master_company_id?.substring(0, 16)}</TableCell>
                  <TableCell className="py-1 text-[9px] text-zinc-500">{l.source || '—'}</TableCell>
                  <TableCell className="py-1 text-[9px] text-zinc-500 truncate">{l.performed_by}</TableCell>
                </TableRow>
              ))}
            </TableBody></Table>
          </div>
        </TabsContent>
      </Tabs>

      {/* Detail Dialog */}
      <EntityDetail id={detailId} onClose={() => setDetailId(null)} onAction={refreshAll} />
    </div>
  );
}

function EntityDetail({ id, onClose, onAction }) {
  const [entity, setEntity] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api.get(`/master/${id}`).then(r => setEntity(r.data)).catch(() => toast.error('Error')).finally(() => setLoading(false));
  }, [id]);

  if (!id) return null;

  return (
    <Dialog open={!!id} onOpenChange={onClose}>
      <DialogContent className="bg-zinc-900 border-zinc-700 max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader><DialogTitle className="text-zinc-50 font-heading text-sm">Detalle entidad master</DialogTitle></DialogHeader>
        {loading ? <Loader2 className="w-5 h-5 animate-spin text-zinc-400 mx-auto mt-4" /> : entity && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Badge className={`text-[8px] border ${MS_BADGE[entity.merge_status] || MS_BADGE.discovered}`}>{entity.merge_status}</Badge>
              {entity.published_to_valuo && <Badge className="text-[8px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">En Valuo</Badge>}
              <span className="text-[9px] font-mono text-zinc-500 ml-auto">{entity.master_company_id}</span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-[10px]">
              <div><span className="text-zinc-500">Nombre:</span> <span className="text-zinc-200">{entity.normalized_name || entity.legal_name || '—'}</span></div>
              <div><span className="text-zinc-500">CIF:</span> <span className="text-zinc-200 font-mono">{entity.cif || '—'}</span></div>
              <div><span className="text-zinc-500">Dominio:</span> <span className="text-zinc-200">{entity.domain || '—'}</span></div>
              <div><span className="text-zinc-500">Categoria:</span> <span className="text-zinc-200">{entity.category_name || '—'}</span></div>
              <div><span className="text-zinc-500">Comerciales:</span> <span className="text-zinc-200">{entity.commercial_names?.join(', ') || '—'}</span></div>
              <div><span className="text-zinc-500">Aliases:</span> <span className="text-zinc-200">{entity.aliases?.join(', ') || '—'}</span></div>
            </div>

            {/* Source trace */}
            {entity.source_trace?.length > 0 && (
              <div>
                <p className="text-[9px] uppercase text-zinc-500 font-semibold mb-1">Fuentes del dato</p>
                {entity.source_trace.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 text-[9px] py-0.5 border-b border-zinc-800/30">
                    <Badge variant="outline" className="text-[7px] text-zinc-400 border-zinc-700">{s.source}</Badge>
                    <span className="text-zinc-500">{s.fields_contributed?.join(', ')}</span>
                    <span className="text-zinc-600 ml-auto">{fmtDate(s.timestamp)}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Linked results */}
            {entity.linked_agency_results?.length > 0 && (
              <div>
                <p className="text-[9px] uppercase text-zinc-500 font-semibold mb-1">Resultados scraper vinculados</p>
                {entity.linked_agency_results.map(ar => (
                  <div key={ar.id} className="flex items-center gap-2 text-[9px] py-0.5 border-b border-zinc-800/30">
                    <span className="text-zinc-200">{ar.company_name || ar.input_url}</span>
                    <Badge variant="outline" className="text-[7px] text-zinc-500 border-zinc-700">{ar.status}</Badge>
                  </div>
                ))}
              </div>
            )}

            {/* Audit */}
            {entity.audit_history?.length > 0 && (
              <div>
                <p className="text-[9px] uppercase text-zinc-500 font-semibold mb-1">Historial</p>
                {entity.audit_history.map((a, i) => (
                  <div key={i} className="flex items-center gap-2 text-[9px] py-0.5 border-b border-zinc-800/30">
                    <span className="text-zinc-500 font-mono">{fmtDate(a.timestamp)}</span>
                    <Badge variant="outline" className="text-[7px] text-zinc-400 border-zinc-700">{a.action}</Badge>
                    <span className="text-zinc-500">{a.performed_by}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2 pt-2">
              {entity.merge_status !== 'verified' && (
                <Button size="sm" className="h-7 text-[10px] bg-emerald-600/20 text-emerald-400" onClick={async () => {
                  await api.post(`/master/${entity.master_company_id}/verify`); toast.success('Verificada'); onAction(); onClose();
                }}><CheckCircle className="w-3 h-3 mr-1" />Verificar</Button>
              )}
              {!entity.published_to_valuo && entity.merge_status === 'verified' && (
                <Button size="sm" className="h-7 text-[10px] bg-cyan-600/20 text-cyan-400" onClick={async () => {
                  await api.post(`/master/${entity.master_company_id}/publish-to-valuo`); toast.success('Publicada en Valuo'); onAction(); onClose();
                }}><Shield className="w-3 h-3 mr-1" />Publicar en Valuo</Button>
              )}
              {entity.published_to_valuo && (
                <Button size="sm" variant="ghost" className="h-7 text-[10px] text-rose-400" onClick={async () => {
                  await api.post(`/master/${entity.master_company_id}/unpublish-from-valuo`); toast.success('Retirada de Valuo'); onAction(); onClose();
                }}>Retirar de Valuo</Button>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
