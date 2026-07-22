import { useState, useEffect } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Loader2, BarChart3, TrendingUp, DollarSign, AlertTriangle, RefreshCw, Clock } from 'lucide-react';

function fmtM(v) {
  if (!v && v !== 0) return '—';
  if (v >= 1000) return `${(v/1000).toFixed(1)}B`;
  return `${v.toFixed(1)}M`;
}
function fmtX(v) { return v != null ? `${v.toFixed(1)}x` : '—'; }

const HEAT_COLOR = (v) => {
  if (!v) return 'bg-zinc-800';
  if (v >= 12) return 'bg-emerald-600';
  if (v >= 9) return 'bg-emerald-700';
  if (v >= 7) return 'bg-yellow-600';
  if (v >= 5) return 'bg-amber-600';
  return 'bg-rose-600';
};

export default function ValuationsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [rebuilding, setRebuilding] = useState(false);

  const loadData = () => {
    setLoading(true);
    api.get('/valuations/by-category').then(r => setData(r.data)).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { loadData(); }, []);

  const handleRebuild = async () => {
    setRebuilding(true);
    try {
      await api.post('/valuations/rebuild');
      loadData();
    } catch { /* */ }
    setRebuilding(false);
  };

  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>;

  const categories = data?.categories || [];
  const heatmap = data?.heatmap || [];
  const s = data?.summary || {};
  const fmtDate = (iso) => { if (!iso) return '—'; try { return new Date(iso).toLocaleDateString('es-ES', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}); } catch { return '—'; } };

  return (
    <div className="space-y-5" data-testid="valuations-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-zinc-100">Valoraciones por Categoria</h1>
          <p className="text-xs text-zinc-500 mt-0.5">M&A Radar — Multiplos observados por categoria</p>
        </div>
        <Button variant="outline" size="sm" onClick={handleRebuild} disabled={rebuilding}
          className="border-zinc-700 text-zinc-300 h-7 text-xs">
          {rebuilding ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <RefreshCw className="w-3 h-3 mr-1.5" />}
          Reconstruir valoraciones
        </Button>
      </div>

      {/* Last rebuild info */}
      <div className="flex items-center gap-3 bg-zinc-900/40 border border-zinc-800/50 rounded-lg px-3 py-2">
        <Clock className="w-3.5 h-3.5 text-zinc-600" />
        <span className="text-xs text-zinc-400">Ultima reconstruccion:</span>
        <span className="text-xs text-zinc-200">{fmtDate(s.last_rebuilt)}</span>
        {s.rebuild_trigger && <Badge variant="outline" className="text-[9px] text-zinc-400 border-zinc-600">{s.rebuild_trigger}</Badge>}
        <span className="text-[10px] text-zinc-600">{s.total_deals || 0} operaciones analizadas</span>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <BarChart3 className="w-4 h-4 text-zinc-400 mx-auto mb-1" />
            <p className="text-xl font-bold text-zinc-100 tabular-nums">{s.total_deals || 0}</p>
            <p className="text-[10px] text-zinc-500">Operaciones totales</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <DollarSign className="w-4 h-4 text-emerald-400 mx-auto mb-1" />
            <p className="text-xl font-bold text-emerald-400 tabular-nums">{s.deals_with_ev || 0}</p>
            <p className="text-[10px] text-zinc-500">Con Enterprise Value</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <TrendingUp className="w-4 h-4 text-blue-400 mx-auto mb-1" />
            <p className="text-xl font-bold text-zinc-100 tabular-nums">{s.deals_with_ebitda || 0}</p>
            <p className="text-[10px] text-zinc-500">Con EBITDA</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <p className="text-xl font-bold text-zinc-100 tabular-nums">{s.categories_covered || 0}</p>
            <p className="text-[10px] text-zinc-500">Categorias cubiertas</p>
          </CardContent>
        </Card>
      </div>

      {/* No data notice */}
      {!s.data_available && (
        <Card className="bg-amber-500/5 border-amber-500/20">
          <CardContent className="p-4 flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0" />
            <div>
              <p className="text-sm text-amber-300 font-medium">Datos insuficientes</p>
              <p className="text-xs text-amber-400/70 mt-0.5">
                Las operaciones cargadas actualmente no incluyen Enterprise Value ni EBITDA.
                A medida que se carguen operaciones con datos financieros, los multiplos se calcularan automaticamente.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Heatmap */}
      {heatmap.length > 0 && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs text-zinc-400">EV/EBITDA por categoria</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {heatmap.sort((a, b) => (b.ev_ebitda || 0) - (a.ev_ebitda || 0)).map((h, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-[10px] text-zinc-400 w-40 truncate">{h.category}</span>
                  <div className={`h-5 rounded ${HEAT_COLOR(h.ev_ebitda)} flex items-center px-2`}
                    style={{ width: `${Math.min(100, (h.ev_ebitda || 0) / 15 * 100)}%`, minWidth: 40 }}>
                    <span className="text-[9px] text-white font-bold">{fmtX(h.ev_ebitda)}</span>
                  </div>
                  <span className="text-[9px] text-zinc-600">{h.deals} ops</span>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-3 mt-3 text-[8px] text-zinc-600">
              <span className="flex items-center gap-1"><span className="w-3 h-2 rounded bg-rose-600" /> Bajo</span>
              <span className="flex items-center gap-1"><span className="w-3 h-2 rounded bg-amber-600" /> Medio</span>
              <span className="flex items-center gap-1"><span className="w-3 h-2 rounded bg-yellow-600" /> Alto</span>
              <span className="flex items-center gap-1"><span className="w-3 h-2 rounded bg-emerald-600" /> Premium</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Category cards */}
      {categories.length > 0 ? (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          {categories.map((cat, i) => (
            <Card key={i} className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-4">
                <h3 className="text-sm font-semibold text-zinc-200 mb-3">{cat.category}</h3>
                <Badge variant="outline" className="text-[9px] text-zinc-400 border-zinc-600 mb-3">{cat.deals_count} operaciones</Badge>

                <div className="grid grid-cols-2 gap-2 text-[10px]">
                  {cat.sum_ev_eurm && (
                    <div><span className="text-zinc-500 block">EV agregado</span><span className="text-zinc-200 font-semibold">{fmtM(cat.sum_ev_eurm)} EUR</span></div>
                  )}
                  {cat.average_ev_eurm && (
                    <div><span className="text-zinc-500 block">Ticket medio</span><span className="text-zinc-200 font-semibold">{fmtM(cat.average_ev_eurm)} EUR</span></div>
                  )}
                  {cat.median_ev_eurm && (
                    <div><span className="text-zinc-500 block">Ticket mediano</span><span className="text-zinc-200 font-semibold">{fmtM(cat.median_ev_eurm)} EUR</span></div>
                  )}
                  {cat.ev_revenue_aggregate && (
                    <div><span className="text-zinc-500 block">EV/Revenue</span><span className="text-emerald-400 font-semibold">{fmtX(cat.ev_revenue_aggregate)}</span></div>
                  )}
                  {cat.ev_ebitda_aggregate && (
                    <div><span className="text-zinc-500 block">EV/EBITDA agg.</span><span className="text-blue-400 font-bold text-sm">{fmtX(cat.ev_ebitda_aggregate)}</span></div>
                  )}
                  {cat.ev_ebitda_median && (
                    <div><span className="text-zinc-500 block">EV/EBITDA med.</span><span className="text-zinc-200 font-semibold">{fmtX(cat.ev_ebitda_median)}</span></div>
                  )}
                </div>

                {cat.ev_ebitda_range && (
                  <div className="mt-3 pt-2 border-t border-zinc-800">
                    <span className="text-[9px] text-zinc-500">Rango habitual</span>
                    <p className="text-xs text-zinc-300 font-medium">{cat.ev_ebitda_range}</p>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="py-8 text-center">
            <p className="text-xs text-zinc-600">Las tarjetas de valoracion apareceran cuando se carguen operaciones con datos financieros en M&A Radar.</p>
          </CardContent>
        </Card>
      )}

      {/* Attribution */}
      <p className="text-[9px] text-zinc-700 text-center">
        Basado en {data?.total_deals || 0} operaciones. Multiplos calculados como SUM(EV)/SUM(metrica), no como media de ratios individuales.
      </p>
    </div>
  );
}
