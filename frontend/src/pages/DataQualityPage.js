import { useState, useEffect } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, CheckCircle2, AlertTriangle, XCircle, Database, BarChart3, Building2, FileText, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';

const STATUS_CONFIG = {
  real: { icon: CheckCircle2, color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20', label: 'Real', dot: 'bg-emerald-500' },
  synthetic: { icon: AlertTriangle, color: 'text-amber-400', bg: 'bg-amber-500/10 border-amber-500/20', label: 'Sintetico', dot: 'bg-amber-500' },
  empty: { icon: XCircle, color: 'text-rose-400', bg: 'bg-rose-500/10 border-rose-500/20', label: 'Sin datos', dot: 'bg-rose-500' },
};

function SourceCard({ name, status, records, lastUpdate, description }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.empty;
  const Icon = cfg.icon;
  return (
    <Card className={`border ${cfg.bg}`} data-testid={`source-${name.toLowerCase().replace(/\s+/g, '-')}`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${cfg.dot}`} />
            <h3 className="text-sm font-semibold text-zinc-100">{name}</h3>
          </div>
          <Badge variant="outline" className={`text-[10px] ${cfg.color} border-current/20`}>{cfg.label}</Badge>
        </div>
        <p className="text-xs text-zinc-500 mb-3">{description}</p>
        <div className="flex items-center justify-between">
          <span className="text-xs text-zinc-400">{records?.toLocaleString('es-ES') || '0'} registros</span>
          {lastUpdate && <span className="text-[10px] text-zinc-600">Ult. act: {lastUpdate}</span>}
        </div>
      </CardContent>
    </Card>
  );
}

function CoverageBar({ label, real, synthetic, total }) {
  const realPct = total > 0 ? (real / total) * 100 : 0;
  const synthPct = total > 0 ? (synthetic / total) * 100 : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-400">{label}</span>
        <span className="text-xs text-zinc-300 tabular-nums">{total.toLocaleString('es-ES')}</span>
      </div>
      <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden flex">
        <div className="h-full bg-emerald-500 rounded-l-full" style={{ width: `${realPct}%` }} />
        <div className="h-full bg-amber-500" style={{ width: `${synthPct}%` }} />
      </div>
      <div className="flex items-center gap-3 text-[10px]">
        <span className="text-emerald-400">{real.toLocaleString('es-ES')} real ({realPct.toFixed(0)}%)</span>
        {synthetic > 0 && <span className="text-amber-400">{synthetic.toLocaleString('es-ES')} sintetico ({synthPct.toFixed(0)}%)</span>}
      </div>
    </div>
  );
}

function ScoreTraceCard({ scoreName, label, realPct, components }) {
  return (
    <Card className="bg-zinc-900/50 border-zinc-800">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-zinc-100">{label}</h3>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-zinc-500">Datos reales:</span>
            <span className={`text-sm font-bold tabular-nums ${realPct >= 80 ? 'text-emerald-400' : realPct >= 50 ? 'text-amber-400' : 'text-rose-400'}`}>
              {realPct}%
            </span>
          </div>
        </div>
        <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden mb-3">
          <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${realPct}%` }} />
        </div>
        <div className="space-y-1">
          {components.map((c, i) => (
            <div key={i} className="flex items-center justify-between text-[11px]">
              <span className="text-zinc-500">{c.source}</span>
              <Badge variant="outline" className={`text-[9px] px-1.5 py-0 ${c.real ? 'text-emerald-400 border-emerald-500/20' : 'text-amber-400 border-amber-500/20'}`}>
                {c.real ? 'Real' : 'Estimado'}
              </Badge>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export default function DataQualityPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [ibRes, healthRes] = await Promise.all([
        api.get('/admin/iberinform/stats').catch(() => ({ data: null })),
        api.get('/data-providers/health').catch(() => ({ data: null })),
      ]);

      // Gather counts from various endpoints
      const counts = {};
      try {
        const sectorRes = await api.get('/public/sector-intelligence/overview');
        counts.sectors = sectorRes.data?.count || 0;
      } catch { counts.sectors = 0; }
      try {
        const geoRes = await api.get('/public/geo-intelligence/overview');
        counts.territories = geoRes.data?.count || 0;
      } catch { counts.territories = 0; }

      setData({
        iberinform: ibRes.data,
        health: healthRes.data,
        counts,
      });
    } catch (e) {
      toast.error('Error cargando datos de calidad');
    }
    setLoading(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-5 h-5 animate-spin text-zinc-500" />
      </div>
    );
  }

  const ib = data?.iberinform?.iberinform || {};
  const cm = data?.iberinform?.companies_master || {};
  const providers = data?.health?.providers || [];

  // Extract provider data
  const getProvider = (id) => providers.find(p => p.provider_id === id || p.provider === id) || {};
  const bormeP = getProvider('borme');
  const ineP = getProvider('ine');
  const macroRecords = 1742; // Known from audit
  const borme = bormeP;

  // Real vs synthetic breakdown — read explicit backend counts (data_source-based), never
  // inferred by subtraction. Subtracting cm.total - ib.total_companies broke the moment real
  // Iberinform data became the near-totality of companies_master (both counts converge to the
  // same ~25k, making the subtraction ~0 and mislabeling real data as synthetic).
  const realCompanies = ib.real_companies ?? 0;
  const synthCompanies = ib.synthetic_companies ?? 0;
  const hasIberinformStats = ib.total_companies !== undefined;
  const ibFullyReal = hasIberinformStats && synthCompanies === 0 && realCompanies > 0;

  // Score traceability
  const realDataPct = 83;

  return (
    <div className="space-y-6" data-testid="data-quality-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-zinc-100">Calidad de Datos</h1>
          <p className="text-xs text-zinc-500 mt-0.5">Trazabilidad, cobertura y estado de las fuentes</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadData} className="border-zinc-700 text-zinc-300 h-7 text-xs">
          <RefreshCw className="w-3 h-3 mr-1.5" /> Actualizar
        </Button>
      </div>

      {/* Coverage Summary */}
      <div className="grid grid-cols-3 gap-3">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4 text-center">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Datos reales</p>
            <p className="text-3xl font-bold text-emerald-400" data-testid="real-data-pct">{realDataPct}%</p>
            <p className="text-xs text-zinc-500 mt-1">del dynamism_score</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4 text-center">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Empresas reales</p>
            <p className="text-3xl font-bold text-zinc-100 tabular-nums" data-testid="real-companies">{(hasIberinformStats ? realCompanies : 265).toLocaleString('es-ES')}</p>
            <p className="text-xs text-zinc-500 mt-1">de {(cm.total || 5265).toLocaleString('es-ES')} total</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4 text-center">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Empresas sinteticas</p>
            <p className="text-3xl font-bold text-amber-400 tabular-nums" data-testid="synthetic-companies">{(hasIberinformStats ? synthCompanies : 5000).toLocaleString('es-ES')}</p>
            <p className="text-xs text-zinc-500 mt-1">{synthCompanies > 0 ? 'pendiente de purgar' : 'purgadas — solo datos reales'}</p>
          </CardContent>
        </Card>
      </div>

      {/* Source Status */}
      <div>
        <h2 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
          <Database className="w-4 h-4 text-zinc-500" /> Estado de las fuentes
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          <SourceCard name="Banco de Espana" status="real" records={macroRecords}
            description="Euribor, tipos BCE, credito empresarial, depositos" />
          <SourceCard name="INE" status="real" records={(ib.total_companies ? 101 + 424 : 525)}
            description="DIRCE, IASS, Soc. Mercantiles, demografia empresarial" />
          <SourceCard name="BORME" status="real" records={bormeP.total_records || 39721}
            description="Actos mercantiles del Registro Mercantil (BOE)" />
          <SourceCard name="Contratacion Publica" status="real" records={19}
            description="Contratos con CPV, importes, adjudicatarios" />
          <SourceCard name="Iberinform"
            status={!hasIberinformStats ? 'empty' : synthCompanies > 0 ? 'synthetic' : realCompanies > 0 ? 'real' : 'empty'}
            records={hasIberinformStats ? (ib.total_companies || 0) : 5000}
            description={
              !hasIberinformStats ? 'Esperando fichero real.'
              : synthCompanies > 0 ? `${realCompanies.toLocaleString('es-ES')} reales + ${synthCompanies.toLocaleString('es-ES')} sinteticas pendientes de purgar`
              : realCompanies > 0 ? `${realCompanies.toLocaleString('es-ES')} empresas reales (entrega Iberinform)`
              : 'Esperando fichero real.'
            } />
          <SourceCard name="Agency Scraper" status="real" records={265}
            description="Agencias analizadas con Playwright + GPT-5.2" />
        </div>
      </div>

      {/* Data Coverage */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-zinc-500" /> Cobertura del sistema
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <CoverageBar label="Companies Master" real={hasIberinformStats ? realCompanies : 265} synthetic={hasIberinformStats ? synthCompanies : 5000} total={cm.total || 5265} />
          {/* CNAE/Provincias/Ejercicios below used to always label their coverage as
              "synthetic" — a hardcode left over from when Iberinform WAS always synthetic.
              These three metrics don't have their own real/synthetic split from the backend
              (they're aggregate counts, not per-record), so the closest accurate signal is
              the same real/synthetic split already computed above: if there's no synthetic
              data left at all, the coverage behind these numbers is real too. */}
          <CoverageBar label="Cobertura CNAE"
            real={ibFullyReal ? (ib.cnae_divisions_covered || 0) : 0}
            synthetic={ibFullyReal ? 0 : (ib.cnae_divisions_covered || 83)} total={88} />
          <CoverageBar label="Cobertura Provincias"
            real={ibFullyReal ? (ib.provinces_covered || 0) : 0}
            synthetic={ibFullyReal ? 0 : (ib.provinces_covered || 52)} total={52} />
          <CoverageBar label="Ejercicios Financieros"
            real={ibFullyReal ? (ib.total_fiscal_years || 0) : 0}
            synthetic={ibFullyReal ? 0 : (ib.total_fiscal_years || 11657)}
            total={ib.total_fiscal_years || 11657} />
        </CardContent>
      </Card>

      {/* Score Traceability */}
      <div>
        <h2 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
          <FileText className="w-4 h-4 text-zinc-500" /> Trazabilidad por score
        </h2>
        <div className="grid grid-cols-2 gap-3">
          <ScoreTraceCard scoreName="size_score" label="size_score" realPct={100}
            components={[
              { source: 'INE DIRCE — Total nacional (3.31M)', real: true },
              { source: 'INE DIRCE — Distribucion por CNAE', real: true },
              { source: 'INE DIRCE — Distribucion por provincia', real: true },
              { source: 'Empresas individuales en BD', real: false },
            ]} />
          <ScoreTraceCard scoreName="growth_score" label="growth_score" realPct={80}
            components={[
              { source: 'INE — Sociedades constituidas (mensual)', real: true },
              { source: 'INE — Sociedades disueltas (mensual)', real: true },
              { source: 'INE — Variacion interanual', real: true },
              { source: 'Reparto por CNAE/provincia', real: false },
            ]} />
          <ScoreTraceCard scoreName="activity_score" label="activity_score" realPct={75}
            components={[
              { source: 'BORME — 39.7K actos mercantiles', real: true },
              { source: 'BORME — registry_province', real: true },
              { source: 'Contratacion Publica — 19 contratos', real: true },
              { source: 'Iberinform — sub-score empresarial', real: false },
            ]} />
          <ScoreTraceCard scoreName="dynamism_score" label="dynamism_score" realPct={83}
            components={[
              { source: '25% size_score (100% real)', real: true },
              { source: '40% growth_score (80% real)', real: true },
              { source: '35% activity_score (75% real)', real: true },
              { source: 'Formula: 0.25×S + 0.40×G + 0.35×A', real: true },
            ]} />
        </div>
      </div>
    </div>
  );
}
