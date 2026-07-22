import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Loader2, TrendingUp, TrendingDown, Minus, ChevronRight, ArrowLeft, BarChart3, Building2 } from 'lucide-react';
import { toast } from 'sonner';
import { SyncBar } from '@/components/SyncBar';

const TREND_ICON = { up: TrendingUp, down: TrendingDown, stable: Minus };
const TREND_COLOR = { up: 'text-emerald-400', down: 'text-rose-400', stable: 'text-zinc-500' };
const SIGNAL_LABELS = {
  sector_expansion: 'Expansion', sector_contraction: 'Contraccion', emerging_sector: 'Emergente',
  mature_sector: 'Maduro', high_public_demand: 'Demanda publica', high_corporate_activity: 'Act. corporativa',
  stable_activity: 'Estable',
};
const SIGNAL_COLORS = {
  sector_expansion: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  sector_contraction: 'bg-rose-500/15 text-rose-400 border-rose-500/20',
  emerging_sector: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
  mature_sector: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/20',
  high_public_demand: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
  high_corporate_activity: 'bg-violet-500/15 text-violet-400 border-violet-500/20',
  stable_activity: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/20',
};

function ScoreBar({ value, max = 100, color = 'bg-blue-500' }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-zinc-300 tabular-nums w-6 text-right">{value}</span>
    </div>
  );
}

function ScoreCell({ value, label }) {
  const color = value >= 80 ? 'bg-emerald-500' : value >= 60 ? 'bg-blue-500' : value >= 40 ? 'bg-amber-500' : 'bg-rose-500';
  return <ScoreBar value={value} color={color} />;
}

function SectorRow({ sector, onClick, showDrilldown = true }) {
  const TIcon = TREND_ICON[sector.trend_direction] || Minus;
  const tColor = TREND_COLOR[sector.trend_direction] || 'text-zinc-500';
  return (
    <TableRow
      className={`border-zinc-800/50 ${showDrilldown ? 'cursor-pointer hover:bg-zinc-800/30' : ''}`}
      onClick={showDrilldown ? () => onClick?.(sector) : undefined}
      data-testid={`sector-row-${sector.cnae_code}`}
    >
      <TableCell className="py-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-zinc-500 w-5">{sector.cnae_code}</span>
          <span className="text-sm text-zinc-200 truncate max-w-[280px]">{sector.cnae_label}</span>
        </div>
      </TableCell>
      <TableCell className="py-2"><ScoreCell value={sector.dynamism_score} /></TableCell>
      <TableCell className="py-2"><ScoreCell value={sector.size_score} /></TableCell>
      <TableCell className="py-2"><ScoreCell value={sector.growth_score} /></TableCell>
      <TableCell className="py-2"><ScoreCell value={sector.activity_score} /></TableCell>
      <TableCell className="py-2">
        <div className="flex items-center gap-1.5">
          <TIcon className={`w-3 h-3 ${tColor}`} />
          <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${SIGNAL_COLORS[sector.signal] || ''}`}>
            {SIGNAL_LABELS[sector.signal] || sector.signal}
          </Badge>
        </div>
      </TableCell>
      <TableCell className="py-2 text-right">
        <span className="text-xs text-zinc-400 tabular-nums">
          {sector.active_companies > 0 ? sector.active_companies.toLocaleString('es-ES') : '—'}
        </span>
      </TableCell>
      {showDrilldown && (
        <TableCell className="py-2 w-8">
          <ChevronRight className="w-3.5 h-3.5 text-zinc-600" />
        </TableCell>
      )}
    </TableRow>
  );
}

function StatsCards({ sectors }) {
  if (!sectors?.length) return null;
  const avgDyn = Math.round(sectors.reduce((s, x) => s + x.dynamism_score, 0) / sectors.length);
  const totalCompanies = sectors.reduce((s, x) => s + (x.active_companies || 0), 0);
  const expanding = sectors.filter(s => s.signal === 'sector_expansion' || s.signal === 'emerging_sector').length;
  const contracting = sectors.filter(s => s.signal === 'sector_contraction').length;

  return (
    <div className="grid grid-cols-4 gap-3 mb-5">
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3">
          <div className="flex items-center gap-2 mb-1"><BarChart3 className="w-3.5 h-3.5 text-blue-400" /><span className="text-[10px] uppercase tracking-wider text-zinc-500">Dynamism medio</span></div>
          <p className="text-xl font-bold text-zinc-100 tabular-nums" data-testid="avg-dynamism">{avgDyn}</p>
        </CardContent>
      </Card>
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3">
          <div className="flex items-center gap-2 mb-1"><Building2 className="w-3.5 h-3.5 text-zinc-400" /><span className="text-[10px] uppercase tracking-wider text-zinc-500">Empresas activas</span></div>
          <p className="text-xl font-bold text-zinc-100 tabular-nums" data-testid="total-companies">{totalCompanies.toLocaleString('es-ES')}</p>
        </CardContent>
      </Card>
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3">
          <div className="flex items-center gap-2 mb-1"><TrendingUp className="w-3.5 h-3.5 text-emerald-400" /><span className="text-[10px] uppercase tracking-wider text-zinc-500">En expansion</span></div>
          <p className="text-xl font-bold text-emerald-400 tabular-nums">{expanding}</p>
        </CardContent>
      </Card>
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3">
          <div className="flex items-center gap-2 mb-1"><TrendingDown className="w-3.5 h-3.5 text-rose-400" /><span className="text-[10px] uppercase tracking-wider text-zinc-500">En contraccion</span></div>
          <p className="text-xl font-bold text-rose-400 tabular-nums">{contracting}</p>
        </CardContent>
      </Card>
    </div>
  );
}

function fmtEUR(v) {
  if (v === null || v === undefined) return '—';
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M €`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)}k €`;
  return `${v.toLocaleString('es-ES')} €`;
}

function CompaniesTable({ data, loading, onLoadMore }) {
  const companies = data?.companies || [];
  const pagination = data?.pagination || {};

  return (
    <div className="space-y-3">
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3 flex items-center gap-2">
          <Building2 className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-xs text-zinc-400">
            {pagination.total_in_arroba_universe ?? companies.length} empresas reales en el universo ARROBA
            para este sector (no es la estimación DIRCE/INE nacional que se ve arriba).
          </span>
        </CardContent>
      </Card>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800 hover:bg-transparent">
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Empresa</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Provincia</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Facturacion</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">EBITDA</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-center">Senales</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Senal principal</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {companies.map((c) => (
              <TableRow key={c.master_id} className="border-zinc-800/50">
                <TableCell className="py-2 text-sm text-zinc-200">{c.legal_name || c.master_id}</TableCell>
                <TableCell className="py-2 text-xs text-zinc-400">{c.provincia || '—'}</TableCell>
                <TableCell className="py-2 text-xs text-zinc-300 text-right tabular-nums">{fmtEUR(c.revenue)}</TableCell>
                <TableCell className="py-2 text-xs text-zinc-300 text-right tabular-nums">{fmtEUR(c.ebitda)}</TableCell>
                <TableCell className="py-2 text-center">
                  <Badge variant="outline" className="text-[10px] border-zinc-700 text-zinc-400">
                    {c.active_signals_count ?? 0}
                  </Badge>
                </TableCell>
                <TableCell className="py-2">
                  {c.top_signal ? (
                    <Badge variant="outline" className="text-[10px] border-blue-500/30 text-blue-400 bg-blue-500/5">
                      {c.top_signal.signal_type}
                    </Badge>
                  ) : <span className="text-xs text-zinc-600">—</span>}
                </TableCell>
              </TableRow>
            ))}
            {companies.length === 0 && !loading && (
              <TableRow><TableCell colSpan={6} className="text-center text-xs text-zinc-500 py-8">
                Sin empresas reales cargadas para este sector todavia.
              </TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      {loading && (
        <div className="flex items-center justify-center py-6"><Loader2 className="w-4 h-4 animate-spin text-zinc-500" /></div>
      )}

      {!loading && pagination.returned < pagination.total_in_arroba_universe && (
        <div className="flex justify-center">
          <Button variant="outline" size="sm" onClick={onLoadMore} className="border-zinc-700 text-zinc-300 h-7 text-xs">
            Cargar mas empresas
          </Button>
        </div>
      )}

      {data?.data_caveat && (
        <p className="text-[9px] text-zinc-700">{data.data_caveat}</p>
      )}
    </div>
  );
}

export default function SectorIntelligencePage() {
  const [sectors, setSectors] = useState([]);
  const [level, setLevel] = useState('section');
  const [loading, setLoading] = useState(true);
  const [drilldown, setDrilldown] = useState(null);
  const [drillData, setDrillData] = useState(null);
  const [breadcrumbs, setBreadcrumbs] = useState([]);
  const [companiesData, setCompaniesData] = useState(null);
  const [companiesLoading, setCompaniesLoading] = useState(false);

  const loadOverview = useCallback(async (lvl = 'section') => {
    setLoading(true);
    try {
      const { data } = await api.get(`/public/sector-intelligence/overview?level=${lvl}`);
      setSectors(data.sectors || []);
      setLevel(lvl);
    } catch (e) { toast.error('Error cargando sectores'); }
    setLoading(false);
  }, []);

  const loadCompanies = useCallback(async (cnaeCode, offset = 0, append = false) => {
    setCompaniesLoading(true);
    try {
      const { data } = await api.get(`/public/sector-intelligence/detail/${cnaeCode}/companies`, {
        params: { limit: 20, offset },
      });
      setCompaniesData(prev => append && prev ? { ...data, companies: [...prev.companies, ...data.companies] } : data);
    } catch (e) { toast.error('Error cargando empresas del sector'); }
    setCompaniesLoading(false);
  }, []);

  const loadDrilldown = useCallback(async (sector) => {
    setLoading(true);
    setCompaniesData(null);
    try {
      if (sector.cnae_level === 'section') {
        const { data } = await api.get(`/public/sector-intelligence/section/${sector.cnae_code}`);
        setDrillData(data);
        setBreadcrumbs(prev => [...prev, { code: sector.cnae_code, label: sector.cnae_label, level: 'section' }]);
      } else if (sector.cnae_level === 'division') {
        const { data } = await api.get(`/public/sector-intelligence/detail/${sector.cnae_code}`);
        setDrillData(data);
        setBreadcrumbs(prev => [...prev, { code: sector.cnae_code, label: sector.cnae_label, level: 'division' }]);
      } else if (sector.cnae_level === 'group') {
        // Finest CNAE granularity — no more sub-sectors, drill straight into real
        // companies (Q5) instead of another sector table.
        setDrillData(null);
        setBreadcrumbs(prev => [...prev, { code: sector.cnae_code, label: sector.cnae_label, level: 'group' }]);
        await loadCompanies(sector.cnae_code, 0, false);
      }
      setDrilldown(sector);
    } catch (e) { toast.error('Error en drill-down'); }
    setLoading(false);
  }, [loadCompanies]);

  const goBack = () => {
    const newCrumbs = [...breadcrumbs];
    newCrumbs.pop();
    setBreadcrumbs(newCrumbs);
    setCompaniesData(null);
    if (newCrumbs.length === 0) {
      setDrilldown(null);
      setDrillData(null);
    } else {
      const last = newCrumbs[newCrumbs.length - 1];
      loadDrilldown({ cnae_code: last.code, cnae_label: last.label, cnae_level: last.level });
    }
  };

  const goHome = () => {
    setDrilldown(null);
    setDrillData(null);
    setBreadcrumbs([]);
    setCompaniesData(null);
  };

  useEffect(() => { loadOverview(); }, [loadOverview]);

  const children = drillData?.divisions || drillData?.children || [];
  const parentSector = drillData?.section || drillData?.sector || null;

  return (
    <div className="space-y-4" data-testid="sector-intelligence-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Sector Intelligence</h1>
        <p className="text-xs text-zinc-500 mt-0.5">
          Dinamismo sectorial por CNAE — {sectors.length || children.length} sectores
        </p>
      </div>

      <SyncBar
        module="sector_intelligence"
        syncEndpoint="/public/sector-intelligence/sync"
        onSyncComplete={() => { goHome(); loadOverview(); }}
      />

      {drilldown && (
        <div className="flex items-center gap-2 text-xs">
          <Button variant="ghost" size="sm" onClick={goHome} className="h-6 px-2 text-xs text-zinc-400 hover:text-zinc-200">
            Secciones
          </Button>
          {breadcrumbs.map((bc, i) => (
            <span key={bc.code} className="flex items-center gap-1">
              <ChevronRight className="w-3 h-3 text-zinc-600" />
              <span className={`${i === breadcrumbs.length - 1 ? 'text-zinc-200' : 'text-zinc-500'}`}>
                {bc.code} {bc.label?.substring(0, 35)}
              </span>
            </span>
          ))}
        </div>
      )}

      {!drilldown ? (
        <>
          <StatsCards sectors={sectors} />
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-zinc-500" />
            </div>
          ) : (
            <Card className="bg-zinc-900/50 border-zinc-800">
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800 hover:bg-transparent">
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Sector CNAE</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Dynamism</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Size</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Growth</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Activity</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Signal</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Empresas</TableHead>
                    <TableHead className="w-8" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sectors.map(s => <SectorRow key={s.cnae_code} sector={s} onClick={loadDrilldown} />)}
                </TableBody>
              </Table>
            </Card>
          )}
        </>
      ) : (
        <>
          {parentSector && <StatsCards sectors={[parentSector]} />}
          <div className="flex items-center gap-2 mb-2">
            <Button variant="ghost" size="sm" onClick={breadcrumbs.length > 1 ? goBack : goHome}
              className="h-7 px-2 text-xs text-zinc-400 hover:text-zinc-200">
              <ArrowLeft className="w-3 h-3 mr-1" /> Volver
            </Button>
          </div>
          {drilldown?.cnae_level === 'group' ? (
            <CompaniesTable
              data={companiesData}
              loading={companiesLoading}
              onLoadMore={() => loadCompanies(drilldown.cnae_code, companiesData?.companies?.length || 0, true)}
            />
          ) : loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-zinc-500" />
            </div>
          ) : (
            <Card className="bg-zinc-900/50 border-zinc-800">
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800 hover:bg-transparent">
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">CNAE</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Dynamism</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Size</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Growth</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Activity</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Signal</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Empresas</TableHead>
                    {parentSector?.cnae_level !== 'division' && <TableHead className="w-8" />}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {children.map(s => (
                    <SectorRow key={s.cnae_code} sector={s} onClick={loadDrilldown} showDrilldown />
                  ))}
                  {children.length === 0 && (
                    <TableRow><TableCell colSpan={8} className="text-center text-xs text-zinc-500 py-8">Sin sub-sectores</TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
