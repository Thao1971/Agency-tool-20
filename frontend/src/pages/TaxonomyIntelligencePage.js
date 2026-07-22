import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2, RefreshCw, Activity, PieChart, Unplug, GitFork, AlertTriangle, ShieldCheck, ShieldAlert, ShieldX, Sparkles, Bot } from 'lucide-react';
import { toast } from 'sonner';

const TAX_LABELS = { taric: 'TARIC (DataComex)', cpv: 'CPV (Contratación)', nace: 'NACE', cis_category: 'CIS', cnmv: 'CNMV' };

const VERDICT = {
  healthy: { label: 'Saludable', color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30', Icon: ShieldCheck },
  degraded: { label: 'Degradado', color: 'bg-amber-500/15 text-amber-400 border-amber-500/30', Icon: ShieldAlert },
  critical: { label: 'Crítico', color: 'bg-rose-500/15 text-rose-400 border-rose-500/30', Icon: ShieldX },
};

function Metric({ label, value, accent = 'text-zinc-100', testid }) {
  return (
    <Card className="bg-zinc-900/50 border-zinc-800">
      <CardContent className="p-3 text-center">
        <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">{label}</p>
        <p className={`text-2xl font-bold tabular-nums ${accent}`} data-testid={testid}>{value}</p>
      </CardContent>
    </Card>
  );
}

function WeightBar({ value }) {
  const pct = Math.round((value || 0) * 100);
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-12 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className="h-full rounded-full bg-blue-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-zinc-500 tabular-nums">{pct}%</span>
    </div>
  );
}

export default function TaxonomyIntelligencePage() {
  const [health, setHealth] = useState(null);
  const [coverage, setCoverage] = useState([]);
  const [orphans, setOrphans] = useState(null);
  const [incons, setIncons] = useState(null);
  const [suggStats, setSuggStats] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [accepted, setAccepted] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [tab, setTab] = useState('health');

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [h, c, o, i, ss, cand, acc] = await Promise.all([
        api.get('/taxonomy-intelligence/health'),
        api.get('/taxonomy-intelligence/coverage'),
        api.get('/taxonomy-intelligence/orphans?limit=500'),
        api.get('/taxonomy-intelligence/inconsistencies?limit=500'),
        api.get('/taxonomy-intelligence/suggestions/stats'),
        api.get('/taxonomy-intelligence/suggestions?status=candidate'),
        api.get('/taxonomy-intelligence/suggestions?status=accepted'),
      ]);
      setHealth(h.data);
      setCoverage(c.data.coverage || []);
      setOrphans(o.data);
      setIncons(i.data);
      setSuggStats(ss.data);
      setCandidates(cand.data.suggestions || []);
      setAccepted(acc.data.suggestions || []);
    } catch { toast.error('Error cargando el motor de taxonomía'); }
    setLoading(false);
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const { data } = await api.post('/taxonomy-intelligence/suggest?scope=all&limit=15');
      toast.success(`IA: ${data.suggestions_generated} sugerencias · ${data.auto_accepted} auto-activadas · ${data.candidates} candidatas`);
      await loadAll();
    } catch { toast.error('Error generando sugerencias IA'); }
    setGenerating(false);
  };

  const handleRecompute = async () => {
    try {
      await api.post('/taxonomy-intelligence/recompute-weights');
      toast.success('Pesos re-normalizados');
      loadAll();
    } catch { toast.error('Error'); }
  };

  const handleSeed = async () => {
    try {
      await api.post('/taxonomy-intelligence/seed');
      toast.success('Taxonomías re-sembradas');
      loadAll();
    } catch { toast.error('Error'); }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>;
  }

  const h = health || {};
  const verdict = VERDICT[h.verdict] || VERDICT.degraded;
  const VIcon = verdict.Icon;
  const weak = incons?.weak_mappings || { total: 0, items: [] };
  const conflicts = incons?.conflicts || { total: 0, items: [] };
  const breaches = incons?.weight_breaches || { total: 0, items: [] };

  return (
    <div className="space-y-4" data-testid="taxonomy-intelligence-page">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold text-zinc-100">Taxonomy Governance Engine</h1>
            <Badge variant="outline" className="text-[9px] text-zinc-500 border-zinc-700">v2 · weighted</Badge>
          </div>
          <p className="text-xs text-zinc-500 mt-0.5">
            Resolución automática y ponderada — {h.total_mappings || 0} mappings, {h.source_codes_mapped || 0} códigos, integridad de pesos {h.weight_integrity_pct ?? 0}%
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className={`text-[11px] px-2 py-1 ${verdict.color}`} data-testid="health-verdict">
            <VIcon className="w-3 h-3 mr-1" /> {verdict.label}
          </Badge>
          <Button variant="default" size="sm" onClick={handleGenerate} disabled={generating} className="bg-violet-600 hover:bg-violet-500 text-white h-7 text-xs" data-testid="generate-ai-btn">
            {generating ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <Sparkles className="w-3 h-3 mr-1.5" />} Generar sugerencias IA
          </Button>
          <Button variant="outline" size="sm" onClick={handleRecompute} className="border-zinc-700 text-zinc-300 h-7 text-xs" data-testid="recompute-weights-btn">
            <RefreshCw className="w-3 h-3 mr-1.5" /> Re-normalizar pesos
          </Button>
          <Button variant="outline" size="sm" onClick={handleSeed} className="border-zinc-700 text-zinc-300 h-7 text-xs" data-testid="seed-btn">
            Re-seed
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="health" className="text-xs data-[state=active]:bg-zinc-800" data-testid="tab-health"><Activity className="w-3 h-3 mr-1" /> Salud</TabsTrigger>
          <TabsTrigger value="coverage" className="text-xs data-[state=active]:bg-zinc-800" data-testid="tab-coverage"><PieChart className="w-3 h-3 mr-1" /> Cobertura</TabsTrigger>
          <TabsTrigger value="orphans" className="text-xs data-[state=active]:bg-zinc-800" data-testid="tab-orphans"><Unplug className="w-3 h-3 mr-1" /> Huérfanos ({orphans?.total || 0})</TabsTrigger>
          <TabsTrigger value="weak" className="text-xs data-[state=active]:bg-zinc-800" data-testid="tab-weak"><AlertTriangle className="w-3 h-3 mr-1" /> Mappings débiles ({weak.total})</TabsTrigger>
          <TabsTrigger value="conflicts" className="text-xs data-[state=active]:bg-zinc-800" data-testid="tab-conflicts"><GitFork className="w-3 h-3 mr-1" /> Conflictos ({conflicts.total + breaches.total})</TabsTrigger>
          <TabsTrigger value="suggestions" className="text-xs data-[state=active]:bg-zinc-800" data-testid="tab-suggestions"><Sparkles className="w-3 h-3 mr-1" /> Sugerencias IA ({suggStats?.pending_candidates || 0})</TabsTrigger>
          <TabsTrigger value="autolearn" className="text-xs data-[state=active]:bg-zinc-800" data-testid="tab-autolearn"><Bot className="w-3 h-3 mr-1" /> Auto-learn ({suggStats?.auto_accepted || 0})</TabsTrigger>
        </TabsList>

        {/* HEALTH */}
        <TabsContent value="health" className="mt-3 space-y-3">
          <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
            <Metric label="Total mappings" value={h.total_mappings || 0} testid="m-total" />
            <Metric label="Activos" value={h.active || 0} accent="text-emerald-400" testid="m-active" />
            <Metric label="Códigos mapeados" value={h.source_codes_mapped || 0} testid="m-codes" />
            <Metric label="Integridad pesos" value={`${h.weight_integrity_pct ?? 0}%`} accent={h.weight_integrity_pct >= 95 ? 'text-emerald-400' : 'text-amber-400'} testid="m-integrity" />
            <Metric label="Pérdida de datos" value={h.orphans_with_data_loss || 0} accent={h.orphans_with_data_loss > 0 ? 'text-rose-400' : 'text-emerald-400'} testid="m-dataloss" />
            <Metric label="Mappings débiles" value={h.weak_mappings || 0} accent={h.weak_mappings > 0 ? 'text-amber-400' : 'text-zinc-100'} testid="m-weak" />
          </div>
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-4 space-y-3">
              <p className="text-sm text-zinc-300">
                El motor resuelve correspondencias <span className="text-zinc-100 font-medium">automáticamente y de forma ponderada</span>. No existe aprobación humana: los mappings son <Badge variant="outline" className="text-[9px] bg-emerald-500/15 text-emerald-400 border-emerald-500/20">activos</Badge> o <Badge variant="outline" className="text-[9px] bg-zinc-500/15 text-zinc-400 border-zinc-600">inactivos</Badge>.
              </p>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                <div><span className="text-zinc-500">Taxonomías activas:</span> <span className="text-zinc-200">{(h.taxonomies || []).map(t => TAX_LABELS[t] || t).join(', ') || '—'}</span></div>
                <div><span className="text-zinc-500">Huérfanos totales:</span> <span className="text-zinc-200">{h.orphans_total || 0}</span></div>
                <div><span className="text-zinc-500">Conflictos (fragmentación):</span> <span className="text-zinc-200">{h.conflicts || 0}</span></div>
                <div><span className="text-zinc-500">Origen:</span> <span className="text-zinc-200">{Object.entries(h.by_origin || {}).map(([k, v]) => `${k}: ${v}`).join(' · ') || '—'}</span></div>
              </div>
              <p className="text-[11px] text-zinc-500">
                Signals Weighted Engine: el valor económico de cada código se reparte proporcionalmente al <span className="text-blue-400">peso</span> de cada CNAE (los pesos suman 1.0 por código) → ninguna señal se descarta por mappings imperfectos.
              </p>
              <div className="border-t border-zinc-800 pt-3 grid grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                <div><span className="text-zinc-500">IA · candidatas:</span> <span className="text-violet-400 font-medium">{suggStats?.pending_candidates || 0}</span></div>
                <div><span className="text-zinc-500">IA · auto-activadas:</span> <span className="text-emerald-400 font-medium">{suggStats?.auto_accepted || 0}</span></div>
                <div><span className="text-zinc-500">IA · generadas:</span> <span className="text-zinc-200">{suggStats?.llm_candidates || 0}</span></div>
                <div><span className="text-zinc-500">MetaScore medio:</span> <span className="text-zinc-200">{((suggStats?.average_metascore || 0) * 100).toFixed(0)}%</span></div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* COVERAGE */}
        <TabsContent value="coverage" className="mt-3">
          <Card className="bg-zinc-900/50 border-zinc-800">
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800 hover:bg-transparent">
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Taxonomía</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Universo</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Códigos mapeados</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Mappings</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Cobertura</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Integridad pesos</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {coverage.map((c) => (
                  <TableRow key={c.taxonomy} className="border-zinc-800/50" data-testid={`coverage-row-${c.taxonomy}`}>
                    <TableCell className="py-2 text-xs text-zinc-200 font-medium">{TAX_LABELS[c.taxonomy] || c.taxonomy}</TableCell>
                    <TableCell className="py-2 text-xs text-zinc-400 tabular-nums">{c.universe_known ? c.universe_size : '—'}</TableCell>
                    <TableCell className="py-2 text-xs text-zinc-400 tabular-nums">{c.mapped_codes}</TableCell>
                    <TableCell className="py-2 text-xs text-zinc-400 tabular-nums">{c.total_mappings}</TableCell>
                    <TableCell className="py-2"><Badge variant="outline" className={`text-[10px] ${c.coverage_pct >= 90 ? 'text-emerald-400 border-emerald-500/20' : c.coverage_pct > 0 ? 'text-amber-400 border-amber-500/20' : 'text-zinc-500 border-zinc-700'}`}>{c.coverage_pct}%</Badge></TableCell>
                    <TableCell className="py-2"><Badge variant="outline" className={`text-[10px] ${c.weight_integrity_pct >= 95 ? 'text-emerald-400 border-emerald-500/20' : 'text-amber-400 border-amber-500/20'}`}>{c.weight_integrity_pct}%</Badge></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* ORPHANS */}
        <TabsContent value="orphans" className="mt-3">
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3 text-xs text-zinc-400 border-b border-zinc-800">
              {orphans?.with_data_loss > 0
                ? <span className="text-rose-400"><AlertTriangle className="w-3 h-3 inline mr-1" />{orphans.with_data_loss} código(s) con datos reales SIN mapping → pérdida de señal económica.</span>
                : <span className="text-emerald-400"><ShieldCheck className="w-3 h-3 inline mr-1" />Ningún código con datos reales queda huérfano. Cero pérdida de señal.</span>}
            </CardContent>
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800 hover:bg-transparent">
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Taxonomía</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Código</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Etiqueta</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">¿En datos?</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Ocurrencias</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(orphans?.orphans || []).map((o, i) => (
                  <TableRow key={`${o.taxonomy}-${o.code}-${i}`} className="border-zinc-800/50">
                    <TableCell className="py-1.5"><Badge variant="outline" className="text-[9px] text-zinc-400 border-zinc-600">{o.taxonomy}</Badge></TableCell>
                    <TableCell className="py-1.5 text-xs font-mono text-zinc-300">{o.code}</TableCell>
                    <TableCell className="py-1.5 text-xs text-zinc-400 max-w-[300px] truncate">{o.label || '—'}</TableCell>
                    <TableCell className="py-1.5">{o.seen_in_data ? <Badge variant="outline" className="text-[9px] text-rose-400 border-rose-500/20">Sí</Badge> : <span className="text-[10px] text-zinc-600">No</span>}</TableCell>
                    <TableCell className="py-1.5 text-xs text-zinc-400 tabular-nums">{o.occurrences || 0}</TableCell>
                  </TableRow>
                ))}
                {(!orphans?.orphans || orphans.orphans.length === 0) && (
                  <TableRow><TableCell colSpan={5} className="text-center text-xs text-zinc-600 py-8">Sin huérfanos.</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* WEAK */}
        <TabsContent value="weak" className="mt-3">
          <Card className="bg-zinc-900/50 border-zinc-800">
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800 hover:bg-transparent">
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Taxonomía</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Código</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Etiqueta</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">→ CNAE</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Confianza</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Peso</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Origen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {weak.items.map((m, i) => (
                  <TableRow key={i} className="border-zinc-800/50">
                    <TableCell className="py-1.5"><Badge variant="outline" className="text-[9px] text-zinc-400 border-zinc-600">{m.taxonomy}</Badge></TableCell>
                    <TableCell className="py-1.5 text-xs font-mono text-zinc-300">{m.code}</TableCell>
                    <TableCell className="py-1.5 text-xs text-zinc-400 max-w-[240px] truncate">{m.label || '—'}</TableCell>
                    <TableCell className="py-1.5"><Badge variant="outline" className="text-[10px] text-blue-400 border-blue-500/20 font-mono">{m.cnae_code}</Badge></TableCell>
                    <TableCell className="py-1.5"><span className="text-[11px] text-amber-400 tabular-nums">{(m.confidence_score * 100).toFixed(0)}%</span></TableCell>
                    <TableCell className="py-1.5"><WeightBar value={m.weight} /></TableCell>
                    <TableCell className="py-1.5"><Badge variant="outline" className="text-[9px] text-zinc-500 border-zinc-700">{m.origin}</Badge></TableCell>
                  </TableRow>
                ))}
                {weak.items.length === 0 && (
                  <TableRow><TableCell colSpan={7} className="text-center text-xs text-zinc-600 py-8">Sin mappings débiles.</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* CONFLICTS */}
        <TabsContent value="conflicts" className="mt-3 space-y-3">
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3 text-xs text-zinc-500 border-b border-zinc-800">Códigos fragmentados (mapean a ≥ 3 CNAEs)</CardContent>
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800 hover:bg-transparent">
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Taxonomía</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Código</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Etiqueta</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500"># CNAEs</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Reparto</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {conflicts.items.map((c, i) => (
                  <TableRow key={i} className="border-zinc-800/50">
                    <TableCell className="py-1.5"><Badge variant="outline" className="text-[9px] text-zinc-400 border-zinc-600">{c.taxonomy}</Badge></TableCell>
                    <TableCell className="py-1.5 text-xs font-mono text-zinc-300">{c.code}</TableCell>
                    <TableCell className="py-1.5 text-xs text-zinc-400 max-w-[200px] truncate">{c.label || '—'}</TableCell>
                    <TableCell className="py-1.5 text-xs text-amber-400 tabular-nums">{c.cnae_count}</TableCell>
                    <TableCell className="py-1.5">
                      <div className="flex flex-wrap gap-1">
                        {(c.cnaes || []).map((x, j) => (
                          <Badge key={j} variant="outline" className="text-[9px] text-blue-400 border-blue-500/20 font-mono">{x.cnae} · {(x.weight * 100).toFixed(0)}%</Badge>
                        ))}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {conflicts.items.length === 0 && (
                  <TableRow><TableCell colSpan={5} className="text-center text-xs text-zinc-600 py-8">Sin códigos fragmentados.</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
          {breaches.total > 0 && (
            <Card className="bg-zinc-900/50 border-rose-900/40">
              <CardContent className="p-3 text-xs text-rose-400 border-b border-rose-900/40"><AlertTriangle className="w-3 h-3 inline mr-1" />Brechas de integridad de pesos (suma ≠ 1.0) — usa "Re-normalizar pesos"</CardContent>
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800 hover:bg-transparent">
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Taxonomía</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Código</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Suma pesos</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500"># CNAEs</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {breaches.items.map((b, i) => (
                    <TableRow key={i} className="border-zinc-800/50">
                      <TableCell className="py-1.5"><Badge variant="outline" className="text-[9px] text-zinc-400 border-zinc-600">{b.taxonomy}</Badge></TableCell>
                      <TableCell className="py-1.5 text-xs font-mono text-zinc-300">{b.code}</TableCell>
                      <TableCell className="py-1.5 text-xs text-rose-400 tabular-nums">{b.weight_sum}</TableCell>
                      <TableCell className="py-1.5 text-xs text-zinc-400 tabular-nums">{b.cnae_count}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          )}
        </TabsContent>
        {/* SUGGESTIONS (AI candidates) */}
        <TabsContent value="suggestions" className="mt-3">
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3 text-xs text-zinc-400 border-b border-zinc-800">
              Candidatos generados por GPT-5.2 con MetaScore entre 70% y 90% (revisión humana opcional). El LLM aporta solo el 10% del MetaScore.
            </CardContent>
            <SuggestionTable items={candidates} emptyText="Sin candidatos. Pulsa “Generar sugerencias IA”." />
          </Card>
        </TabsContent>

        {/* AUTO-LEARN (auto-accepted → active llm mappings) */}
        <TabsContent value="autolearn" className="mt-3">
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3 text-xs text-zinc-400 border-b border-zinc-800">
              Mappings creados automáticamente (MetaScore ≥ 90%) → activos con <Badge variant="outline" className="text-[9px] text-violet-400 border-violet-500/30">origin: llm</Badge>. Bucle de gobernanza cerrado sin intervención humana.
            </CardContent>
            <SuggestionTable items={accepted} emptyText="Aún no hay mappings auto-activados por IA." />
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function SuggestionTable({ items, emptyText }) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="border-zinc-800 hover:bg-transparent">
          <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Tax.</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Código</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Etiqueta</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">→ CNAE</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Origen</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Sem.</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">GPT</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">MetaScore</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((s, i) => (
          <TableRow key={s.suggestion_id || i} className="border-zinc-800/50" data-testid={`suggestion-row-${i}`}>
            <TableCell className="py-1.5"><Badge variant="outline" className="text-[9px] text-zinc-400 border-zinc-600">{s.source_taxonomy}</Badge></TableCell>
            <TableCell className="py-1.5 text-xs font-mono text-zinc-300">{s.source_code}</TableCell>
            <TableCell className="py-1.5 text-xs text-zinc-400 max-w-[200px] truncate">{s.source_label || '—'}</TableCell>
            <TableCell className="py-1.5"><Badge variant="outline" className="text-[10px] text-blue-400 border-blue-500/20 font-mono">{s.suggested_cnae}</Badge> <span className="text-[10px] text-zinc-500">{s.suggested_label}</span></TableCell>
            <TableCell className="py-1.5"><Badge variant="outline" className="text-[9px] text-violet-400 border-violet-500/30">{s.origin}</Badge></TableCell>
            <TableCell className="py-1.5 text-[11px] text-zinc-400 tabular-nums">{((s.semantic_similarity || 0) * 100).toFixed(0)}%</TableCell>
            <TableCell className="py-1.5 text-[11px] text-zinc-400 tabular-nums">{((s.gpt_confidence_score || 0) * 100).toFixed(0)}%</TableCell>
            <TableCell className="py-1.5">
              <div className="flex items-center gap-1.5">
                <div className="w-12 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${s.metascore >= 0.9 ? 'bg-emerald-500' : s.metascore >= 0.7 ? 'bg-violet-500' : 'bg-zinc-600'}`} style={{ width: `${(s.metascore || 0) * 100}%` }} />
                </div>
                <span className="text-[11px] text-zinc-300 tabular-nums">{((s.metascore || 0) * 100).toFixed(0)}%</span>
              </div>
            </TableCell>
          </TableRow>
        ))}
        {items.length === 0 && (
          <TableRow><TableCell colSpan={8} className="text-center text-xs text-zinc-600 py-8">{emptyText}</TableCell></TableRow>
        )}
      </TableBody>
    </Table>
  );
}
