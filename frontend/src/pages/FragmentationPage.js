import { useState } from 'react';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, Search, Layers, Building2, TrendingUp } from 'lucide-react';
import { toast } from 'sonner';

const CONCENTRATION_LABEL = {
  unconcentrated: 'No concentrado', moderately_concentrated: 'Moderadamente concentrado',
  highly_concentrated: 'Altamente concentrado',
};
const CONCENTRATION_COLOR = {
  unconcentrated: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/5',
  moderately_concentrated: 'text-amber-400 border-amber-500/30 bg-amber-500/5',
  highly_concentrated: 'text-rose-400 border-rose-500/30 bg-rose-500/5',
};

export default function FragmentationPage() {
  const [cnaeField, setCnaeField] = useState('cnae_code');
  const [cnaeValue, setCnaeValue] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const search = async () => {
    if (!cnaeValue.trim()) return;
    setLoading(true);
    try {
      const { data } = await api.get('/investment-intelligence/fragmentation/view', {
        params: { cnae_field: cnaeField, cnae_value: cnaeValue.trim(), limit_companies: 500 },
      });
      setData(data);
    } catch (e) { toast.error('Error calculando fragmentacion'); setData(null); }
    setLoading(false);
  };

  return (
    <div className="space-y-5" data-testid="fragmentation-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Fragmentacion sectorial</h1>
        <p className="text-xs text-zinc-500 mt-0.5">E7 — Indice de concentracion (HHI) y targets de add-on reales por sector CNAE</p>
      </div>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3 flex items-center gap-2">
          <Select value={cnaeField} onValueChange={setCnaeField}>
            <SelectTrigger className="w-40 h-8 text-xs bg-zinc-950 border-zinc-700 text-zinc-200">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-zinc-900 border-zinc-700 text-zinc-200">
              <SelectItem value="cnae_code">CNAE codigo (4 digitos)</SelectItem>
              <SelectItem value="cnae_division">CNAE division (2 digitos)</SelectItem>
              <SelectItem value="cnae_section">CNAE seccion</SelectItem>
            </SelectContent>
          </Select>
          <Input value={cnaeValue} onChange={e => setCnaeValue(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
            placeholder="Ej. 4711, 47, G..."
            className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs flex-1" />
          <Button size="sm" onClick={search} disabled={loading} className="h-8 text-xs">
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5 mr-1" />}
            Analizar
          </Button>
        </CardContent>
      </Card>

      {data && (
        <>
          <div className="grid grid-cols-4 gap-3">
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-3 text-center">
                <Building2 className="w-4 h-4 text-zinc-400 mx-auto mb-1" />
                <p className="text-xl font-bold text-zinc-100 tabular-nums">{data.total_companies_in_arroba_universe}</p>
                <p className="text-[10px] text-zinc-500">Empresas reales</p>
              </CardContent>
            </Card>
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-3 text-center">
                <Layers className="w-4 h-4 text-blue-400 mx-auto mb-1" />
                <p className="text-xl font-bold text-zinc-100 tabular-nums">{data.market_actors_count}</p>
                <p className="text-[10px] text-zinc-500">Actores de mercado (Q2)</p>
              </CardContent>
            </Card>
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-3 text-center">
                <TrendingUp className="w-4 h-4 text-emerald-400 mx-auto mb-1" />
                <p className="text-xl font-bold text-emerald-400 tabular-nums">{data.standalone_targets_count}</p>
                <p className="text-[10px] text-zinc-500">Targets add-on reales</p>
              </CardContent>
            </Card>
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-3 text-center">
                <p className="text-xl font-bold text-zinc-100 tabular-nums">{data.hhi ?? '—'}</p>
                <p className="text-[10px] text-zinc-500">HHI (0-10000)</p>
              </CardContent>
            </Card>
          </div>

          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-4 space-y-3">
              {data.concentration_label ? (
                <Badge variant="outline" className={`text-xs px-2 py-1 ${CONCENTRATION_COLOR[data.concentration_label]}`}>
                  {CONCENTRATION_LABEL[data.concentration_label]}
                </Badge>
              ) : (
                <p className="text-xs text-amber-400">Sin datos de facturacion suficientes para calcular HHI.</p>
              )}
              <p className="text-[10px] text-zinc-600">{data.hhi_methodology}</p>

              <div className="pt-2 border-t border-zinc-800">
                <p className="text-xs text-zinc-400">
                  Dispersion de multiplos: {data.multiple_dispersion !== null ? data.multiple_dispersion : '—'}
                </p>
                <p className="text-[10px] text-zinc-600 mt-0.5">{data.multiple_dispersion_caveat}</p>
              </div>
            </CardContent>
          </Card>

          {data.truncated && (
            <p className="text-[10px] text-amber-500">
              Resultado truncado — hay mas empresas en este sector de las que se han analizado.
            </p>
          )}
        </>
      )}

      {!data && !loading && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="py-8 text-center">
            <p className="text-xs text-zinc-600">Introduce un codigo CNAE para calcular la fragmentacion del sector.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
