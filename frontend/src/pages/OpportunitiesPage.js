import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '@/lib/api';
import { signalLink } from '@/pages/SignalsPage';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { Loader2, Sparkles, TrendingUp, TrendingDown, Minus, Clock, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' }); }
  catch { return '—'; }
}

const TREND_CFG = {
  improving: { icon: TrendingUp, color: 'text-emerald-400', label: 'Mejorando' },
  worsening: { icon: TrendingDown, color: 'text-rose-400', label: 'Empeorando' },
  stable: { icon: Minus, color: 'text-zinc-400', label: 'Estable' },
};

const DIM_LABELS = { impact: 'Impacto', confidence: 'Confianza', urgency: 'Urgencia', persistence: 'Persistencia' };

function DimBar({ label, value }) {
  const pct = Math.round((value || 0) * 100);
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[9px] text-zinc-500 w-16 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[9px] text-zinc-400 w-8 text-right tabular-nums">{pct}%</span>
    </div>
  );
}

function OpportunityCard({ o, typeLabel }) {
  const navigate = useNavigate();
  const trend = TREND_CFG[o.trend];
  const TrendIcon = trend?.icon;
  return (
    <Card
      className={`bg-zinc-900/50 border-zinc-800 ${o.signal_id ? 'cursor-pointer hover:border-zinc-700' : ''}`}
      data-testid="opportunity-card"
      onClick={() => o.signal_id && navigate(signalLink(o.signal_id, o.master_id))}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-zinc-100 truncate">{o.name || o.master_id}</p>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <Badge variant="outline" className="text-[9px] border-blue-500/30 text-blue-400 bg-blue-500/5">
                {typeLabel || o.signal_type}
              </Badge>
              {trend && (
                <span className={`flex items-center gap-1 text-[9px] ${trend.color}`}>
                  <TrendIcon className="w-3 h-3" />{trend.label}
                </span>
              )}
              {o.is_composite && (
                <Badge variant="outline" className="text-[9px] border-violet-500/30 text-violet-400 bg-violet-500/5">
                  Compuesta
                </Badge>
              )}
            </div>
          </div>
          {o.occurrences > 1 && (
            <span className="text-[9px] text-zinc-600 shrink-0">{o.occurrences}x detectada</span>
          )}
        </div>

        <p className="text-xs text-zinc-400 mb-3">{o.explanation}</p>

        <div className="space-y-1 mb-3">
          {Object.entries(DIM_LABELS).map(([k, l]) => (
            <DimBar key={k} label={l} value={o.dimensions?.[k]} />
          ))}
        </div>

        {o.recommended_actions?.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {o.recommended_actions.map((a, i) => (
              <Badge key={i} variant="outline" className="text-[8px] text-zinc-400 border-zinc-700">{a}</Badge>
            ))}
          </div>
        )}

        <div className="flex items-center gap-3 text-[9px] text-zinc-600 pt-1 border-t border-zinc-800/70">
          <span className="flex items-center gap-1"><Clock className="w-2.5 h-2.5" />Detectada: {fmtDate(o.first_detected_at)}</span>
          {o.last_seen_at && <span>Vista por última vez: {fmtDate(o.last_seen_at)}</span>}
        </div>
      </CardContent>
    </Card>
  );
}

export default function OpportunitiesPage() {
  const [mode, setMode] = useState('ranked'); // 'ranked' | 'feed'
  const [sortBy, setSortBy] = useState('impact');
  const [days, setDays] = useState(7);
  const [provincia, setProvincia] = useState('');
  const [signalType, setSignalType] = useState('all');
  const [trend, setTrend] = useState('all');
  const [catalog, setCatalog] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.get('/signal-intelligence/catalog/view').then(r => setCatalog(r.data)).catch(() => setCatalog(null));
    // Real total, NOT capped by the list endpoints' `limit` (this page only ever
    // fetches up to 30 rows to render) — see routes/signal_intelligence.py _signal_stats().
    api.get('/signal-intelligence/stats/view').then(r => setStats(r.data)).catch(() => setStats(null));
  }, []);

  // severity=='opportunity' (NOT category=='opportunity') is the real "M&A opportunity"
  // tag — category=='opportunity' alone only matches opportunity.succession_signal, which
  // made this filter dropdown hide growth.revenue_surge/growth.sustained/ownership.consolidator.
  const opportunityTypes = (catalog?.signal_types || []).filter(t => t.severity === 'opportunity');
  const typeLabel = (st) => opportunityTypes.find(t => t.signal_type === st)?.description || st;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (mode === 'ranked') {
        const { data } = await api.get('/signal-intelligence/opportunities/view', {
          params: {
            sort_by_dimension: sortBy,
            provincia: provincia || undefined,
            signal_types: signalType !== 'all' ? signalType : undefined,
            trend: trend !== 'all' ? trend : undefined,
            limit: 30,
          },
        });
        setItems(data.opportunities || []);
      } else {
        const { data } = await api.get('/signal-intelligence/opportunities/feed/view', {
          params: { days, provincia: provincia || undefined, limit: 30 },
        });
        setItems(data.opportunities || []);
      }
    } catch (e) {
      toast.error('Error cargando oportunidades');
      setItems([]);
    }
    setLoading(false);
  }, [mode, sortBy, days, provincia, signalType, trend]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5" data-testid="opportunities-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-amber-400" /> Oportunidades
          </h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            Señales de crecimiento, consolidación y sucesión detectadas automáticamente sobre las empresas reales (Q4)
            {stats && <span className="text-zinc-400 font-medium"> — {stats.total_opportunities} oportunidades activas en total</span>}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} className="border-zinc-700 text-zinc-300 h-7 text-xs">
          <RefreshCw className="w-3 h-3 mr-1.5" /> Actualizar
        </Button>
      </div>

      {/* Filters */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3 flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 bg-zinc-950 border border-zinc-800 rounded p-0.5">
            <Button size="sm" variant="ghost"
              onClick={() => setMode('ranked')}
              className={`h-7 px-3 text-xs ${mode === 'ranked' ? 'bg-zinc-800 text-zinc-50' : 'text-zinc-500'}`}>
              Por impacto
            </Button>
            <Button size="sm" variant="ghost"
              onClick={() => setMode('feed')}
              className={`h-7 px-3 text-xs ${mode === 'feed' ? 'bg-zinc-800 text-zinc-50' : 'text-zinc-500'}`}>
              Más recientes
            </Button>
          </div>

          {mode === 'ranked' ? (
            <>
              <Select value={sortBy} onValueChange={setSortBy}>
                <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-8 w-40 text-xs">
                  <SelectValue placeholder="Ordenar por" />
                </SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-700">
                  <SelectItem value="impact">Impacto</SelectItem>
                  <SelectItem value="confidence">Confianza</SelectItem>
                  <SelectItem value="urgency">Urgencia</SelectItem>
                  <SelectItem value="persistence">Persistencia</SelectItem>
                </SelectContent>
              </Select>
              <Select value={trend} onValueChange={setTrend}>
                <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-8 w-36 text-xs">
                  <SelectValue placeholder="Tendencia" />
                </SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-700">
                  <SelectItem value="all">Cualquier tendencia</SelectItem>
                  <SelectItem value="improving">Mejorando</SelectItem>
                  <SelectItem value="worsening">Empeorando</SelectItem>
                  <SelectItem value="stable">Estable</SelectItem>
                </SelectContent>
              </Select>
            </>
          ) : (
            <Select value={String(days)} onValueChange={v => setDays(Number(v))}>
              <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-8 w-40 text-xs">
                <SelectValue placeholder="Ventana" />
              </SelectTrigger>
              <SelectContent className="bg-zinc-900 border-zinc-700">
                <SelectItem value="7">Últimos 7 días</SelectItem>
                <SelectItem value="30">Últimos 30 días</SelectItem>
                <SelectItem value="90">Últimos 90 días</SelectItem>
              </SelectContent>
            </Select>
          )}

          <Select value={signalType} onValueChange={setSignalType}>
            <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-8 w-56 text-xs">
              <SelectValue placeholder="Tipo de señal" />
            </SelectTrigger>
            <SelectContent className="bg-zinc-900 border-zinc-700">
              <SelectItem value="all">Todos los tipos</SelectItem>
              {opportunityTypes.map(t => (
                <SelectItem key={t.signal_type} value={t.signal_type}>{t.description || t.signal_type}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Input value={provincia} onChange={e => setProvincia(e.target.value)}
            placeholder="Provincia (ej. MADRID)"
            className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs w-48" />
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex items-center justify-center py-16"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>
      ) : items.length === 0 ? (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-8 text-center text-xs text-zinc-500">
            Sin oportunidades para estos filtros. Si el motor de señales aún no se ha ejecutado sobre el dataset real,
            hace falta correr /bootstrap o recalcular señales primero.
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {items.map((o, i) => (
            <OpportunityCard key={o.master_id + o.signal_type + i} o={o} typeLabel={typeLabel(o.signal_type)} />
          ))}
        </div>
      )}
    </div>
  );
}
