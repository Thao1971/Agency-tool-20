import { useState, useEffect } from 'react';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Loader2, Search, Shuffle } from 'lucide-react';
import { toast } from 'sonner';

function CompanyPicker({ label, value, onSelect }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (query.trim().length < 2) { setResults([]); return; }
    const t = setTimeout(async () => {
      setSearching(true);
      try {
        const { data } = await api.get('/data-layer/search-companies', { params: { q: query, limit: 10 } });
        setResults(data.companies || []);
      } catch (e) { /* silent */ }
      setSearching(false);
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  return (
    <div className="space-y-1.5 flex-1">
      <p className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</p>
      {value ? (
        <div className="flex items-center justify-between bg-zinc-950 border border-zinc-700 rounded px-2 py-1.5">
          <span className="text-xs text-zinc-200">{value.legal_name}</span>
          <Button variant="ghost" size="sm" onClick={() => onSelect(null)} className="h-5 px-1.5 text-[10px] text-zinc-500">
            cambiar
          </Button>
        </div>
      ) : (
        <div className="relative">
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-zinc-500" />
            <Input value={query} onChange={e => setQuery(e.target.value)}
              placeholder="Buscar empresa..." className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs flex-1" />
            {searching && <Loader2 className="w-3.5 h-3.5 animate-spin text-zinc-500" />}
          </div>
          {results.length > 0 && (
            <div className="absolute z-10 mt-1 w-full border border-zinc-800 rounded bg-zinc-900 divide-y divide-zinc-800/70">
              {results.map(c => (
                <div key={c.master_id} className="px-2 py-1.5 hover:bg-zinc-800/30 cursor-pointer"
                  onClick={() => { onSelect(c); setQuery(''); setResults([]); }}>
                  <span className="text-xs text-zinc-200">{c.legal_name}</span>
                  <span className="text-[10px] text-zinc-600 ml-2">{c.cnae_code} · {c.provincia || '—'}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const CONTROL_LABEL = {
  full_control: 'Control total', significant_influence: 'Influencia significativa',
  minority_stake: 'Participacion minoritaria', control_edge_sin_pct_real: 'Arista real sin porcentaje',
  same_group_sin_camino_pct: 'Mismo grupo (Q2), sin cadena de % que lo explique',
  indirect_path_pct_incompleto: 'Camino indirecto real, cadena de % incompleta',
  unrelated: 'Sin relacion societaria real',
};

export default function ControlSynergyPage() {
  const [companyA, setCompanyA] = useState(null);
  const [companyB, setCompanyB] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const compare = async () => {
    if (!companyA || !companyB) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/data-layer/control-synergy/${companyA.master_id}/${companyB.master_id}`);
      setResult(data);
    } catch (e) { toast.error('Error calculando control & synergy'); setResult(null); }
    setLoading(false);
  };

  return (
    <div className="space-y-5" data-testid="control-synergy-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Control & Synergy</h1>
        <p className="text-xs text-zinc-500 mt-0.5">Control societario real (pct/cadena) y solapamiento estructural entre dos empresas</p>
      </div>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3 flex items-end gap-3">
          <CompanyPicker label="Empresa A" value={companyA} onSelect={setCompanyA} />
          <Shuffle className="w-4 h-4 text-zinc-600 mb-2" />
          <CompanyPicker label="Empresa B" value={companyB} onSelect={setCompanyB} />
          <Button size="sm" onClick={compare} disabled={!companyA || !companyB || loading} className="h-8 text-xs">
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Comparar'}
          </Button>
        </CardContent>
      </Card>

      {result && (
        <div className="grid grid-cols-2 gap-4">
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-4 space-y-2">
              <p className="text-xs font-semibold text-zinc-300">Control</p>
              <Badge variant="outline" className="text-xs border-blue-500/30 text-blue-400 bg-blue-500/5">
                {CONTROL_LABEL[result.control.control_level] || result.control.control_level}
              </Badge>
              {(result.control.pct != null || result.control.implied_effective_pct != null) && (
                <p className="text-2xl font-bold text-zinc-100 tabular-nums">
                  {(result.control.pct ?? result.control.implied_effective_pct)}%
                </p>
              )}
              {result.control.relationship_type && (
                <p className="text-[10px] text-zinc-500">Tipo: {result.control.relationship_type}</p>
              )}
              {result.control.hops && <p className="text-[10px] text-zinc-500">{result.control.hops} salto(s) de distancia</p>}
              <ul className="text-[10px] text-zinc-600 list-disc list-inside space-y-0.5 pt-1">
                {(result.control.evidence || []).map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </CardContent>
          </Card>

          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-4 space-y-2">
              <p className="text-xs font-semibold text-zinc-300">Synergy</p>
              <p className="text-2xl font-bold text-emerald-400 tabular-nums">
                {(result.synergy.synergy_score * 100).toFixed(0)}%
              </p>
              <ul className="text-[10px] text-zinc-600 list-disc list-inside space-y-0.5">
                {(result.synergy.evidence || []).map((e, i) => <li key={i}>{e}</li>)}
              </ul>
              <p className="text-[9px] text-zinc-700 pt-1 border-t border-zinc-800">{result.synergy.data_caveat}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {!result && !loading && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="py-8 text-center">
            <p className="text-xs text-zinc-600">Elige dos empresas para comparar su control y solapamiento real.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
