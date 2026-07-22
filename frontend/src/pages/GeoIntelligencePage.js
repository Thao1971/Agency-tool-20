import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Loader2, TrendingUp, TrendingDown, Minus, ChevronRight, ArrowLeft, MapPin, Building2, BarChart3 } from 'lucide-react';
import { toast } from 'sonner';
import { SyncBar } from '@/components/SyncBar';

const TREND_ICON = { up: TrendingUp, down: TrendingDown, stable: Minus };
const TREND_COLOR = { up: 'text-emerald-400', down: 'text-rose-400', stable: 'text-zinc-500' };
const SIGNAL_LABELS = {
  territory_expansion: 'Expansion', territory_contraction: 'Contraccion',
  high_creation: 'Alta creacion', high_dissolution: 'Alta disolucion',
  public_investment_hub: 'Inversion publica', corporate_hub: 'Hub corporativo',
  stable_territory: 'Estable',
};
const SIGNAL_COLORS = {
  territory_expansion: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  territory_contraction: 'bg-rose-500/15 text-rose-400 border-rose-500/20',
  high_creation: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
  corporate_hub: 'bg-violet-500/15 text-violet-400 border-violet-500/20',
  public_investment_hub: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
  stable_territory: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/20',
};

function ScoreBar({ value, color = 'bg-blue-500' }) {
  const pct = Math.min(100, Math.max(0, value));
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-zinc-300 tabular-nums w-6 text-right">{value}</span>
    </div>
  );
}

function ScoreCell({ value }) {
  const color = value >= 80 ? 'bg-emerald-500' : value >= 60 ? 'bg-blue-500' : value >= 40 ? 'bg-amber-500' : 'bg-rose-500';
  return <ScoreBar value={value} color={color} />;
}

function GeoRow({ territory, onClick, showDrilldown = true }) {
  const TIcon = TREND_ICON[territory.trend_direction] || Minus;
  const tColor = TREND_COLOR[territory.trend_direction] || 'text-zinc-500';
  return (
    <TableRow
      className={`border-zinc-800/50 ${showDrilldown ? 'cursor-pointer hover:bg-zinc-800/30' : ''}`}
      onClick={showDrilldown ? () => onClick?.(territory) : undefined}
      data-testid={`geo-row-${territory.geo_id}`}
    >
      <TableCell className="py-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-zinc-500 w-5">{territory.geo_id}</span>
          <span className="text-sm text-zinc-200">{territory.geo_name}</span>
        </div>
      </TableCell>
      <TableCell className="py-2"><ScoreCell value={territory.dynamism_score} /></TableCell>
      <TableCell className="py-2"><ScoreCell value={territory.size_score} /></TableCell>
      <TableCell className="py-2"><ScoreCell value={territory.growth_score} /></TableCell>
      <TableCell className="py-2"><ScoreCell value={territory.activity_score} /></TableCell>
      <TableCell className="py-2">
        <div className="flex items-center gap-1.5">
          <TIcon className={`w-3 h-3 ${tColor}`} />
          <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${SIGNAL_COLORS[territory.signal] || ''}`}>
            {SIGNAL_LABELS[territory.signal] || territory.signal}
          </Badge>
        </div>
      </TableCell>
      <TableCell className="py-2 text-right">
        <span className="text-xs text-zinc-400 tabular-nums">
          {territory.active_companies > 0 ? territory.active_companies.toLocaleString('es-ES') : '—'}
        </span>
      </TableCell>
      <TableCell className="py-2 text-right">
        <span className="text-xs text-zinc-400 tabular-nums">
          {territory.borme_activity_count > 0 ? territory.borme_activity_count.toLocaleString('es-ES') : '—'}
        </span>
      </TableCell>
      {showDrilldown && (
        <TableCell className="py-2 w-8"><ChevronRight className="w-3.5 h-3.5 text-zinc-600" /></TableCell>
      )}
    </TableRow>
  );
}

function GeoStats({ territories }) {
  if (!territories?.length) return null;
  const avgDyn = Math.round(territories.reduce((s, x) => s + x.dynamism_score, 0) / territories.length);
  const totalCompanies = territories.reduce((s, x) => s + (x.active_companies || 0), 0);
  const totalBorme = territories.reduce((s, x) => s + (x.borme_activity_count || 0), 0);
  const expanding = territories.filter(t => t.signal === 'territory_expansion').length;

  return (
    <div className="grid grid-cols-4 gap-3 mb-5">
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3">
          <div className="flex items-center gap-2 mb-1"><BarChart3 className="w-3.5 h-3.5 text-blue-400" /><span className="text-[10px] uppercase tracking-wider text-zinc-500">Dynamism medio</span></div>
          <p className="text-xl font-bold text-zinc-100 tabular-nums" data-testid="geo-avg-dynamism">{avgDyn}</p>
        </CardContent>
      </Card>
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3">
          <div className="flex items-center gap-2 mb-1"><Building2 className="w-3.5 h-3.5 text-zinc-400" /><span className="text-[10px] uppercase tracking-wider text-zinc-500">Empresas activas</span></div>
          <p className="text-xl font-bold text-zinc-100 tabular-nums" data-testid="geo-total-companies">{totalCompanies.toLocaleString('es-ES')}</p>
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
          <div className="flex items-center gap-2 mb-1"><MapPin className="w-3.5 h-3.5 text-amber-400" /><span className="text-[10px] uppercase tracking-wider text-zinc-500">Eventos BORME</span></div>
          <p className="text-xl font-bold text-zinc-100 tabular-nums">{totalBorme.toLocaleString('es-ES')}</p>
        </CardContent>
      </Card>
    </div>
  );
}

export default function GeoIntelligencePage() {
  const [territories, setTerritories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [drilldown, setDrilldown] = useState(null);
  const [drillData, setDrillData] = useState(null);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/public/geo-intelligence/overview?level=ccaa');
      setTerritories(data.territories || []);
    } catch (e) { toast.error('Error cargando territorios'); }
    setLoading(false);
  }, []);

  const loadCCAA = useCallback(async (territory) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/public/geo-intelligence/ccaa/${territory.geo_id}`);
      setDrillData(data);
      setDrilldown(territory);
    } catch (e) { toast.error('Error en drill-down'); }
    setLoading(false);
  }, []);

  const goHome = () => { setDrilldown(null); setDrillData(null); };

  useEffect(() => { loadOverview(); }, [loadOverview]);

  const provinces = drillData?.provinces || [];
  const parentCCAA = drillData?.ccaa || null;

  return (
    <div className="space-y-4" data-testid="geo-intelligence-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Geo Intelligence</h1>
        <p className="text-xs text-zinc-500 mt-0.5">
          Dinamismo territorial — {drilldown ? `${provinces.length} provincias` : `${territories.length} comunidades`}
        </p>
      </div>

      <SyncBar
        module="geo_intelligence"
        syncEndpoint="/public/geo-intelligence/sync"
        onSyncComplete={() => { goHome(); loadOverview(); }}
      />

      {drilldown && (
        <div className="flex items-center gap-2 text-xs">
          <Button variant="ghost" size="sm" onClick={goHome} className="h-6 px-2 text-xs text-zinc-400 hover:text-zinc-200">
            CCAA
          </Button>
          <ChevronRight className="w-3 h-3 text-zinc-600" />
          <span className="text-zinc-200">{drilldown.geo_name}</span>
        </div>
      )}

      {!drilldown ? (
        <>
          <GeoStats territories={territories} />
          {loading ? (
            <div className="flex items-center justify-center py-12"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>
          ) : (
            <Card className="bg-zinc-900/50 border-zinc-800">
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800 hover:bg-transparent">
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Territorio</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Dynamism</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Size</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Growth</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Activity</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Signal</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Empresas</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">BORME</TableHead>
                    <TableHead className="w-8" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {territories.map(t => <GeoRow key={t.geo_id} territory={t} onClick={loadCCAA} />)}
                </TableBody>
              </Table>
            </Card>
          )}
        </>
      ) : (
        <>
          {parentCCAA && <GeoStats territories={[parentCCAA]} />}
          <div className="flex items-center gap-2 mb-2">
            <Button variant="ghost" size="sm" onClick={goHome} className="h-7 px-2 text-xs text-zinc-400 hover:text-zinc-200">
              <ArrowLeft className="w-3 h-3 mr-1" /> Volver a CCAA
            </Button>
          </div>
          {loading ? (
            <div className="flex items-center justify-center py-12"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>
          ) : (
            <Card className="bg-zinc-900/50 border-zinc-800">
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800 hover:bg-transparent">
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Provincia</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Dynamism</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Size</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Growth</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Activity</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Signal</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Empresas</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">BORME</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {provinces.map(p => <GeoRow key={p.geo_id} territory={p} showDrilldown={false} />)}
                  {provinces.length === 0 && (
                    <TableRow><TableCell colSpan={8} className="text-center text-xs text-zinc-500 py-8">Sin provincias</TableCell></TableRow>
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
