import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, Building2, TrendingUp, TrendingDown, Minus, RefreshCw, PlusCircle, MinusCircle, Scale } from 'lucide-react';
import { toast } from 'sonner';

function fmtNum(v) { return v != null ? Math.round(v).toLocaleString('es-ES') : '—'; }
function fmtPct(v) {
  if (v == null) return null;
  const pct = v * 100;
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
}

const TREND_CFG = {
  up: { icon: TrendingUp, color: 'text-emerald-400' },
  down: { icon: TrendingDown, color: 'text-rose-400' },
  stable: { icon: Minus, color: 'text-zinc-400' },
};

function KpiCard({ icon: Icon, iconColor, label, card, period }) {
  const trend = TREND_CFG[card?.trend];
  const TrendIcon = trend?.icon;
  return (
    <Card className="bg-zinc-900/50 border-zinc-800">
      <CardContent className="p-3 text-center">
        <Icon className={`w-4 h-4 mx-auto mb-1 ${iconColor}`} />
        <p className="text-xl font-bold text-zinc-100 tabular-nums">{fmtNum(card?.value)}</p>
        <p className="text-[10px] text-zinc-500">{label}</p>
        {card?.change_pct != null && (
          <p className={`text-[9px] mt-0.5 flex items-center justify-center gap-1 ${trend?.color || 'text-zinc-500'}`}>
            {TrendIcon && <TrendIcon className="w-2.5 h-2.5" />}{fmtPct(card.change_pct)} interanual
          </p>
        )}
        {period && <p className="text-[9px] text-zinc-700 mt-0.5">{period}</p>}
      </CardContent>
    </Card>
  );
}

function MonthlyBars({ months, created, closed }) {
  if (!months?.length) return null;
  const max = Math.max(1, ...created, ...closed);
  const shown = months.slice(-12);
  const createdShown = created.slice(-12);
  const closedShown = closed.slice(-12);
  return (
    <div className="space-y-2">
      {shown.map((m, i) => (
        <div key={m + i} className="flex items-center gap-2">
          <span className="text-[9px] text-zinc-500 w-16 shrink-0">{m}</span>
          <div className="flex-1 flex items-center gap-1">
            <div className="flex-1 h-3 bg-zinc-800 rounded-sm overflow-hidden flex">
              <div className="h-full bg-emerald-500/70" style={{ width: `${(createdShown[i] / max) * 100}%` }} />
            </div>
            <span className="text-[9px] text-emerald-400 w-12 text-right tabular-nums">{fmtNum(createdShown[i])}</span>
          </div>
          <div className="flex-1 flex items-center gap-1">
            <div className="flex-1 h-3 bg-zinc-800 rounded-sm overflow-hidden flex">
              <div className="h-full bg-rose-500/70" style={{ width: `${(closedShown[i] / max) * 100}%` }} />
            </div>
            <span className="text-[9px] text-rose-400 w-12 text-right tabular-nums">{fmtNum(closedShown[i])}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function BusinessDemographyPage() {
  const [overview, setOverview] = useState(null);
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [ovR, histR] = await Promise.all([
        api.get('/public/business-demography/overview'),
        api.get('/public/business-demography/history', { params: { limit: 12 } }),
      ]);
      setOverview(ovR.data);
      setHistory(histR.data);
    } catch (e) {
      toast.error('Error cargando datos de DIRCE');
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const { data: result } = await api.post('/public/business-demography/sync');
      if (result.status === 'error') {
        toast.error('Error sincronizando DIRCE: ' + (result.error || 'desconocido'));
      } else {
        toast.success('DIRCE sincronizado correctamente');
      }
      await load();
    } catch (e) {
      toast.error('Error sincronizando DIRCE');
    } finally {
      setSyncing(false);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>;
  }

  const o = overview || {};

  return (
    <div className="space-y-5" data-testid="business-demography-page">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-zinc-100">DIRCE — Demografia Empresarial</h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            Directorio Central de Empresas (INE) + Sociedades Mercantiles — estadisticas agregadas del tejido
            empresarial espanol, usadas como contexto/base nacional por Sector x Geo Intelligence
          </p>
          {o.period && <p className="text-[10px] text-zinc-600 mt-1">Periodo mas reciente: {o.period}</p>}
        </div>
        <Button size="sm" variant="outline" className="border-zinc-700 text-zinc-300 h-7 text-[10px] shrink-0"
          onClick={handleSync} disabled={syncing}>
          {syncing ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <RefreshCw className="w-3 h-3 mr-1" />}
          Sincronizar DIRCE
        </Button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard icon={Building2} iconColor="text-blue-400" label="Empresas activas" card={o.active_companies} />
        <KpiCard icon={PlusCircle} iconColor="text-emerald-400" label="Sociedades constituidas" card={o.new_companies} period={o.period} />
        <KpiCard icon={MinusCircle} iconColor="text-rose-400" label="Sociedades disueltas" card={o.closed_companies} period={o.period} />
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <Scale className="w-4 h-4 mx-auto mb-1 text-violet-400" />
            <p className={`text-xl font-bold tabular-nums ${(o.net_balance?.value || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {o.net_balance?.value != null ? (o.net_balance.value >= 0 ? '+' : '') + fmtNum(o.net_balance.value) : '—'}
            </p>
            <p className="text-[10px] text-zinc-500">Balance neto (constituidas - disueltas)</p>
          </CardContent>
        </Card>
      </div>

      {/* Historical */}
      {history?.months?.length > 0 ? (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs font-semibold text-zinc-300">Constituidas vs disueltas (ultimos 12 meses)</p>
              <div className="flex items-center gap-3 text-[9px]">
                <span className="flex items-center gap-1 text-emerald-400"><span className="w-2 h-2 rounded-sm bg-emerald-500/70 inline-block" />Constituidas</span>
                <span className="flex items-center gap-1 text-rose-400"><span className="w-2 h-2 rounded-sm bg-rose-500/70 inline-block" />Disueltas</span>
              </div>
            </div>
            <MonthlyBars months={history.months} created={history.created} closed={history.closed} />
          </CardContent>
        </Card>
      ) : (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-8 text-center text-xs text-zinc-500">
            Sin historico disponible. Pulsa "Sincronizar DIRCE" para cargar los datos del INE.
          </CardContent>
        </Card>
      )}

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3 text-[10px] text-zinc-600">
          Fuente: {o.source || 'Instituto Nacional de Estadistica (INE) — DIRCE + Sociedades Mercantiles'}.
          Sin sincronizacion automatica todavia — usa el boton "Sincronizar DIRCE" para refrescar.
        </CardContent>
      </Card>
    </div>
  );
}
