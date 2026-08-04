import { useState, useEffect } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Loader2, RefreshCw, PieChart, AlertTriangle, CheckCircle2, PlayCircle, Download } from 'lucide-react';
import { toast } from 'sonner';

const SECTOR_COLORS = {
  S01: 'bg-sky-500', S02: 'bg-violet-500', S03: 'bg-pink-500', S04: 'bg-amber-500',
  S05: 'bg-emerald-500', S06: 'bg-orange-500', S07: 'bg-lime-500', S08: 'bg-cyan-500',
  S09: 'bg-indigo-500', S10: 'bg-teal-500', S11: 'bg-rose-500',
};

function StatCard({ label, value, sub, tone = 'text-zinc-100', testid }) {
  return (
    <Card className="bg-zinc-900/50 border-zinc-800">
      <CardContent className="p-4 text-center">
        <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">{label}</p>
        <p className={`text-3xl font-bold tabular-nums ${tone}`} data-testid={testid}>{value}</p>
        {sub && <p className="text-xs text-zinc-500 mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

export default function TaxonomyAuditPage() {
  const [audit, setAudit] = useState(null);
  const [unclassified, setUnclassified] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reclassifying, setReclassifying] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [a, u] = await Promise.all([
        api.get('/company-taxonomy-ui/audit'),
        api.get('/company-taxonomy-ui/unclassified?limit=300'),
      ]);
      setAudit(a.data);
      setUnclassified(u.data);
    } catch (e) {
      toast.error('Error cargando la auditoría de taxonomía');
    }
    setLoading(false);
  };

  useEffect(() => { loadData(); }, []);

  const downloadTriage = async () => {
    toast.info('Generando export de triaje…');
    try {
      const r = await api.get('/company-taxonomy-ui/triage-low-confidence');
      const blob = new Blob([JSON.stringify(r.data, null, 1)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `taxonomy_triage_lowconf_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      const b = r.data?.triage_breakdown || {};
      toast.success(`Triaje: ${r.data?.count} filas · falta_alias ${b.con_texto_pero_baja_conf || 0} · solo_cnae ${b.solo_cnae_sin_texto_libre || 0} · vacío ${b.vacio_sin_cnae_ni_texto || 0}`);
    } catch (e) {
      toast.error('No se pudo generar el triaje');
    }
  };

  const reclassify = async () => {
    setReclassifying(true);
    toast.info('Reclasificando el universo… (~40s)');
    try {
      const r = await api.post('/company-taxonomy-ui/reclassify');
      toast.success(`Reclasificadas ${r.data?.classified?.toLocaleString('es-ES') || '—'} empresas`);
      await loadData();
    } catch (e) {
      toast.error('No se pudo reclasificar');
    }
    setReclassifying(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-5 h-5 animate-spin text-zinc-500" />
      </div>
    );
  }

  const dist = audit?.distribution_by_sector || [];
  const maxCount = dist.length ? Math.max(...dist.map(d => d.count)) : 1;
  const total = audit?.total_classified || 0;
  const avgPct = Math.round((audit?.avg_confidence || 0) * 100);

  return (
    <div className="space-y-6" data-testid="taxonomy-audit-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
            <PieChart className="w-5 h-5 text-violet-400" /> Auditoría de Taxonomía ARROBA
          </h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            Distribución por sector y empresas sin clasificar · taxonomía {audit?.taxonomy_version}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={downloadTriage}
            className="border-amber-700 text-amber-300 h-7 text-xs" data-testid="download-triage-btn">
            <Download className="w-3 h-3 mr-1.5" /> Descargar triaje
          </Button>
          <Button variant="outline" size="sm" onClick={reclassify} disabled={reclassifying}
            className="border-violet-700 text-violet-300 h-7 text-xs" data-testid="reclassify-btn">
            {reclassifying ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <PlayCircle className="w-3 h-3 mr-1.5" />}
            Reclasificar
          </Button>
          <Button variant="outline" size="sm" onClick={loadData}
            className="border-zinc-700 text-zinc-300 h-7 text-xs" data-testid="refresh-btn">
            <RefreshCw className="w-3 h-3 mr-1.5" /> Actualizar
          </Button>
        </div>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Clasificadas" value={total.toLocaleString('es-ES')} sub="con sector principal"
          tone="text-emerald-400" testid="total-classified" />
        <StatCard label="Confianza media" value={`${avgPct}%`} sub="overall_confidence"
          tone={avgPct >= 70 ? 'text-emerald-400' : 'text-amber-400'} testid="avg-confidence" />
        <StatCard label="Baja confianza" value={(audit?.low_confidence || 0).toLocaleString('es-ES')} sub="< 0,5"
          tone="text-amber-400" testid="low-confidence" />
        <StatCard label="Sin clasificar" value={(audit?.unclassified || 0).toLocaleString('es-ES')} sub="sin sector"
          tone="text-rose-400" testid="unclassified-count" />
      </div>

      {/* Distribution by sector */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
            <PieChart className="w-4 h-4 text-zinc-500" /> Distribución por sector
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2.5" data-testid="sector-distribution">
          {dist.map((d) => (
            <div key={d.sector} className="space-y-1" data-testid={`sector-row-${d.sector}`}>
              <div className="flex items-center justify-between text-xs">
                <span className="text-zinc-300">
                  <span className="text-zinc-500 font-mono mr-1.5">{d.sector}</span>{d.label}
                </span>
                <span className="text-zinc-400 tabular-nums">
                  {d.count.toLocaleString('es-ES')} <span className="text-zinc-600">({d.pct}%)</span>
                </span>
              </div>
              <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${SECTOR_COLORS[d.sector] || 'bg-zinc-500'}`}
                  style={{ width: `${(d.count / maxCount) * 100}%` }} />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Unclassified companies */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400" /> Sin clasificar
            <Badge variant="outline" className="text-[10px] text-rose-400 border-rose-500/20 ml-1">
              {unclassified?.total_unclassified || 0}
            </Badge>
            <span className="text-[10px] text-zinc-600 font-normal">
              (mostrando {unclassified?.returned || 0})
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {(unclassified?.items || []).length === 0 ? (
            <div className="flex items-center gap-2 text-sm text-emerald-400 py-4">
              <CheckCircle2 className="w-4 h-4" /> Todo el universo está clasificado.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs" data-testid="unclassified-table">
                <thead>
                  <tr className="text-zinc-500 border-b border-zinc-800">
                    <th className="text-left font-medium py-2 px-2">Empresa</th>
                    <th className="text-left font-medium py-2 px-2">CIF</th>
                    <th className="text-left font-medium py-2 px-2">CNAE</th>
                    <th className="text-left font-medium py-2 px-2">Provincia</th>
                    <th className="text-left font-medium py-2 px-2">Objeto social</th>
                  </tr>
                </thead>
                <tbody>
                  {(unclassified?.items || []).map((it) => (
                    <tr key={it.company_id} className="border-b border-zinc-900 hover:bg-zinc-800/40"
                      data-testid={`unclassified-row-${it.company_id}`}>
                      <td className="py-1.5 px-2 text-zinc-200">{it.legal_name || <span className="text-zinc-600">— sin nombre</span>}</td>
                      <td className="py-1.5 px-2 text-zinc-500 font-mono">{it.cif || '—'}</td>
                      <td className="py-1.5 px-2 text-zinc-400">{it.cnae_code || <span className="text-rose-400/70">sin CNAE</span>}</td>
                      <td className="py-1.5 px-2 text-zinc-500">{it.provincia || '—'}</td>
                      <td className="py-1.5 px-2 text-zinc-500 max-w-md truncate">
                        {it.objeto_social_preview || <span className="text-zinc-700">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
