import { useState } from 'react';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Loader2, Search, Building2, CheckCircle2, XCircle } from 'lucide-react';
import { toast } from 'sonner';

function fmtEUR(v) {
  if (v === null || v === undefined) return '—';
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M €`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)}k €`;
  return `${v.toLocaleString('es-ES')} €`;
}

export default function RollupThesisPage() {
  const [cnaeField, setCnaeField] = useState('cnae_code');
  const [cnaeValue, setCnaeValue] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const search = async () => {
    if (!cnaeValue.trim()) return;
    setLoading(true);
    try {
      const { data } = await api.get('/investment-intelligence/rollup-thesis/view', {
        params: { cnae_field: cnaeField, cnae_value: cnaeValue.trim(), limit_companies: 300 },
      });
      setData(data);
    } catch (e) { toast.error('Error calculando la tesis de roll-up'); setData(null); }
    setLoading(false);
  };

  return (
    <div className="space-y-5" data-testid="rollup-thesis-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Roll-up Thesis</h1>
        <p className="text-xs text-zinc-500 mt-0.5">E6 — Viabilidad de consolidacion, candidato a plataforma y ranking de targets add-on</p>
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
          {/* Viability */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center gap-2">
                {data.rollup_viable === true && <><CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span className="text-sm font-semibold text-emerald-400">Roll-up viable</span></>}
                {data.rollup_viable === false && <><XCircle className="w-4 h-4 text-rose-400" />
                  <span className="text-sm font-semibold text-rose-400">Roll-up no recomendado (sector ya consolidado)</span></>}
                {data.rollup_viable === null && <span className="text-sm font-semibold text-amber-400">Viabilidad no determinable (sin datos de facturacion)</span>}
              </div>
              <ul className="text-xs text-zinc-500 list-disc list-inside space-y-0.5">
                {(data.viability_reasons || []).map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </CardContent>
          </Card>

          {/* Platform candidate */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <Building2 className="w-3.5 h-3.5 text-blue-400" />
                <span className="text-xs font-semibold text-zinc-300">Candidato a plataforma</span>
              </div>
              {data.platform_candidate ? (
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-zinc-100">{data.platform_candidate.name || data.platform_candidate.master_id}</p>
                    <p className="text-[10px] text-zinc-500 mt-0.5">
                      Facturacion del grupo: {fmtEUR(data.platform_candidate.group_revenue)} · Cuota real: {(data.platform_candidate.market_share * 100).toFixed(1)}%
                    </p>
                  </div>
                  <Badge variant="outline" className={data.platform_candidate.platform_type === 'existing'
                    ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/5'
                    : 'text-amber-400 border-amber-500/30 bg-amber-500/5'}>
                    {data.platform_candidate.platform_type === 'existing' ? 'Plataforma existente' : 'Hace falta plataforma externa'}
                  </Badge>
                </div>
              ) : (
                <p className="text-xs text-zinc-600">Sin datos suficientes para identificar un candidato a plataforma.</p>
              )}
            </CardContent>
          </Card>

          {/* Add-on targets */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3">
              <p className="text-xs font-semibold text-zinc-300 mb-2">
                Targets add-on rankeados ({data.addon_targets_count})
              </p>
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800 hover:bg-transparent">
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Empresa</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Facturacion</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Score</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Tamano</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Sucesion</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Sinergia</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(data.addon_targets_ranked || []).map(t => (
                    <TableRow key={t.master_id} className="border-zinc-800/50">
                      <TableCell className="py-2 text-sm text-zinc-200">{t.name || t.master_id}</TableCell>
                      <TableCell className="py-2 text-xs text-zinc-300 text-right tabular-nums">{fmtEUR(t.revenue)}</TableCell>
                      <TableCell className="py-2 text-xs text-blue-400 text-right font-semibold tabular-nums">{t.addon_score}</TableCell>
                      <TableCell className="py-2 text-[10px] text-zinc-500">{t.fit_dimensions.size_fit.value}</TableCell>
                      <TableCell className="py-2 text-[10px] text-zinc-500">{t.fit_dimensions.succession_ease.value}</TableCell>
                      <TableCell className="py-2 text-[10px] text-zinc-500">{t.fit_dimensions.synergy_proximity.value}</TableCell>
                    </TableRow>
                  ))}
                  {(data.addon_targets_ranked || []).length === 0 && (
                    <TableRow><TableCell colSpan={6} className="text-center text-xs text-zinc-500 py-8">Sin targets add-on reales en este sector.</TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}

      {!data && !loading && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="py-8 text-center">
            <p className="text-xs text-zinc-600">Introduce un codigo CNAE para calcular la tesis de roll-up.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
