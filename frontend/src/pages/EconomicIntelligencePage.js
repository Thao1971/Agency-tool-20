import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Loader2, TrendingUp, TrendingDown, Minus, ArrowLeft, BarChart3, Building2, Users, DollarSign, Ship, Briefcase, Zap, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { SyncBar } from '@/components/SyncBar';

function fmtEur(v) {
  if (!v && v !== 0) return '—';
  if (Math.abs(v) >= 1e9) return `${(v/1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `${(v/1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `${(v/1e3).toFixed(0)}K`;
  return v.toLocaleString('es-ES');
}
function fmtNum(v) {
  if (!v && v !== 0) return '—';
  return Math.round(v).toLocaleString('es-ES');
}
function fmtPct(v) {
  if (v === null || v === undefined) return null;
  const color = v > 0 ? 'text-emerald-400' : v < 0 ? 'text-rose-400' : 'text-zinc-400';
  return <span className={`${color} tabular-nums`}>{v > 0 ? '+' : ''}{v.toFixed(1)}%</span>;
}

const SIGNAL_CFG = {
  revenue_boom: { label: 'Revenue Boom', color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20' },
  revenue_decline: { label: 'Revenue Decline', color: 'bg-rose-500/15 text-rose-400 border-rose-500/20' },
  high_corporate_activity: { label: 'Alta act. corporativa', color: 'bg-violet-500/15 text-violet-400 border-violet-500/20' },
  export_powerhouse: { label: 'Potencia exportadora', color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20' },
  trade_surplus: { label: 'Superavit comercial', color: 'bg-blue-500/15 text-blue-400 border-blue-500/20' },
  trade_deficit: { label: 'Deficit comercial', color: 'bg-amber-500/15 text-amber-400 border-amber-500/20' },
  employment_growth: { label: 'Crecimiento empleo', color: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/20' },
  public_demand: { label: 'Demanda publica', color: 'bg-amber-500/15 text-amber-400 border-amber-500/20' },
};

function MetricCard({ icon: Icon, label, value, sub, iconColor = 'text-zinc-400' }) {
  return (
    <Card className="bg-zinc-900/50 border-zinc-800">
      <CardContent className="p-3">
        <div className="flex items-center gap-2 mb-1">
          <Icon className={`w-3.5 h-3.5 ${iconColor}`} />
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</span>
        </div>
        <p className="text-lg font-bold text-zinc-100 tabular-nums">{value}</p>
        {sub && <p className="text-[10px] text-zinc-500 mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function SourceDot({ sources }) {
  const colors = { iberinform: 'bg-amber-500', ine: 'bg-emerald-500', borme: 'bg-blue-500', procurement: 'bg-violet-500', datacomex: 'bg-cyan-500', banco_espana: 'bg-rose-400' };
  return (
    <div className="flex items-center gap-1">
      {sources.map(s => <span key={s} className={`w-1.5 h-1.5 rounded-full ${colors[s] || 'bg-zinc-500'}`} title={s} />)}
    </div>
  );
}

function CNAEProfile({ profile, onBack }) {
  const p = profile;
  const TrendIcon = p.trend === 'up' ? TrendingUp : p.trend === 'down' ? TrendingDown : Minus;
  const trendColor = p.trend === 'up' ? 'text-emerald-400' : p.trend === 'down' ? 'text-rose-400' : 'text-zinc-400';

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack} className="h-7 px-2 text-xs text-zinc-400">
          <ArrowLeft className="w-3 h-3 mr-1" /> Volver
        </Button>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-mono text-zinc-500">{p.cnae_code}</span>
            <h2 className="text-base font-bold text-zinc-100">{p.cnae_label}</h2>
            <TrendIcon className={`w-4 h-4 ${trendColor}`} />
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-[10px] text-zinc-500">Seccion {p.cnae_section}</span>
            <span className="text-zinc-800">|</span>
            <SourceDot sources={p.sources_available || []} />
            <span className="text-[10px] text-zinc-500">{p.sources_available?.length || 0} fuentes, {p.total_metrics} metricas</span>
          </div>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-4 gap-3">
        <MetricCard icon={DollarSign} label="Revenue medio" iconColor="text-emerald-400"
          value={p.revenue ? fmtEur(p.revenue.value) : '—'}
          sub={p.revenue_growth ? <>{fmtPct(p.revenue_growth.yoy_pct)} interanual</> : null} />
        <MetricCard icon={BarChart3} label="EBITDA medio" iconColor="text-blue-400"
          value={p.ebitda ? fmtEur(p.ebitda.value) : '—'}
          sub={p.ebitda_margin ? `Margen ${(p.ebitda_margin.value * 100).toFixed(1)}%` : null} />
        <MetricCard icon={Users} label="Empleados medio" iconColor="text-cyan-400"
          value={p.employment ? fmtNum(p.employment.value) : '—'}
          sub={p.employment_growth ? <>{fmtPct(p.employment_growth.yoy_pct)} interanual</> : null} />
        <MetricCard icon={Building2} label="Empresas activas" iconColor="text-zinc-400"
          value={p.active_companies_national ? fmtNum(p.active_companies_national.value) : '—'}
          sub={p.new_companies_estimate ? `${fmtNum(p.new_companies_estimate.value)} nuevas est.` : null} />
      </div>

      <div className="grid grid-cols-4 gap-3">
        <MetricCard icon={Ship} label="Exportaciones" iconColor="text-emerald-400"
          value={p.exports_eur ? fmtEur(p.exports_eur.value) : '—'}
          sub={p.export_growth ? <>{fmtPct(p.export_growth.yoy_pct)} interanual</> : 'Pendiente DataComex'} />
        <MetricCard icon={Ship} label="Importaciones" iconColor="text-rose-400"
          value={p.imports_eur ? fmtEur(p.imports_eur.value) : '—'}
          sub={p.trade_balance_eur ? `Saldo: ${fmtEur(p.trade_balance_eur.value)}` : null} />
        <MetricCard icon={Zap} label="Eventos BORME" iconColor="text-violet-400"
          value={p.borme_events ? fmtNum(p.borme_events.value) : '—'}
          sub="Actos mercantiles" />
        <MetricCard icon={Briefcase} label="Contratacion publica" iconColor="text-amber-400"
          value={p.procurement_contracts ? fmtNum(p.procurement_contracts.value) : '—'}
          sub={p.procurement_amount_eur ? fmtEur(p.procurement_amount_eur.value) + ' EUR' : null} />
      </div>

      {/* Signals */}
      {p.signals?.length > 0 && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2"><CardTitle className="text-xs text-zinc-400">Senales economicas</CardTitle></CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {p.signals.map((s, i) => {
              const cfg = SIGNAL_CFG[s.signal_type] || { label: s.signal_type, color: 'bg-zinc-500/15 text-zinc-400' };
              return (
                <div key={i} className={`px-3 py-1.5 rounded-lg border ${cfg.color}`}>
                  <p className="text-xs font-medium">{cfg.label}</p>
                  <p className="text-[10px] opacity-75 mt-0.5">{s.description}</p>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function EconomicIntelligencePage() {
  const [overview, setOverview] = useState([]);
  const [signals, setSignals] = useState([]);
  const [stats, setStats] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const [ovRes, sigRes, stRes] = await Promise.all([
        api.get('/economic-intelligence/overview?limit=30'),
        api.get('/economic-intelligence/signals?limit=20'),
        api.get('/economic-intelligence/stats'),
      ]);
      setOverview(ovRes.data.cnae_divisions || []);
      setSignals(sigRes.data.signals || []);
      setStats(stRes.data);
    } catch { toast.error('Error cargando Economic Intelligence'); }
    setLoading(false);
  }, []);

  useEffect(() => { loadOverview(); }, [loadOverview]);

  const loadProfile = async (cnae) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/economic-intelligence/cnae/${cnae}`);
      setProfile(data);
    } catch { toast.error('Error cargando perfil'); }
    setLoading(false);
  };

  if (loading && !profile && !overview.length) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>;
  }

  if (profile) {
    return (
      <div className="space-y-4" data-testid="economic-intelligence-page">
        <CNAEProfile profile={profile} onBack={() => setProfile(null)} />
      </div>
    );
  }

  const s = stats || {};

  return (
    <div className="space-y-4" data-testid="economic-intelligence-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Economic Intelligence</h1>
        <p className="text-xs text-zinc-500 mt-0.5">
          Capa economica unificada — {s.total_metrics?.toLocaleString('es-ES') || 0} metricas, {s.cnae_codes_covered || 0} CNAE, {Object.keys(s.by_source || {}).length} fuentes
        </p>
      </div>

      <SyncBar module="economic_intelligence" syncEndpoint="/economic-intelligence/rebuild" onSyncComplete={loadOverview} />

      {/* Stats */}
      <div className="grid grid-cols-5 gap-3">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Metricas</p>
            <p className="text-xl font-bold text-zinc-100 tabular-nums" data-testid="econ-metrics">{(s.total_metrics || 0).toLocaleString('es-ES')}</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Senales</p>
            <p className="text-xl font-bold text-amber-400 tabular-nums" data-testid="econ-signals">{s.total_signals || 0}</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">CNAE</p>
            <p className="text-xl font-bold text-zinc-100 tabular-nums">{s.cnae_codes_covered || 0}</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Fuentes</p>
            <p className="text-xl font-bold text-zinc-100 tabular-nums">{Object.keys(s.by_source || {}).length}</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Por fuente</p>
            <div className="space-y-0.5">
              {Object.entries(s.by_source || {}).sort((a,b) => b[1]-a[1]).map(([src, count]) => (
                <div key={src} className="flex items-center justify-between text-[10px]">
                  <span className="text-zinc-400">{src}</span>
                  <span className="text-zinc-300 tabular-nums">{count}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Signals strip */}
      {signals.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <Zap className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
          {signals.slice(0, 8).map((sig, i) => {
            const cfg = SIGNAL_CFG[sig.signal_type] || { label: sig.signal_type, color: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/20' };
            return (
              <Badge key={i} variant="outline" className={`text-[10px] px-2 py-0.5 whitespace-nowrap cursor-pointer ${cfg.color}`}
                onClick={() => loadProfile(sig.cnae_code)}>
                {sig.cnae_code} {cfg.label}
              </Badge>
            );
          })}
        </div>
      )}

      {/* CNAE Table */}
      <Card className="bg-zinc-900/50 border-zinc-800">
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
            {overview.map(c => (
              <TableRow key={c.cnae_code} className="border-zinc-800/50 cursor-pointer hover:bg-zinc-800/30"
                onClick={() => loadProfile(c.cnae_code)} data-testid={`econ-row-${c.cnae_code}`}>
                <TableCell className="py-2">
                  <span className="text-xs font-mono text-zinc-500">{c.cnae_code}</span>
                </TableCell>
                <TableCell className="py-2">
                  <span className="text-sm text-zinc-200 truncate max-w-[300px] block">{c.cnae_label}</span>
                  <span className="text-[10px] text-zinc-600">Seccion {c.cnae_section}</span>
                </TableCell>
                <TableCell className="py-2 text-center">
                  <div className="flex items-center justify-center gap-1">
                    <SourceDot sources={c.sources} />
                    <span className="text-[10px] text-zinc-500 ml-1">{c.sources_count}</span>
                  </div>
                </TableCell>
                <TableCell className="py-2 text-right">
                  <span className="text-xs text-zinc-400 tabular-nums">{c.metrics_count}</span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
