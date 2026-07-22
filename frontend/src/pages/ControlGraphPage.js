import { useState, useEffect } from 'react';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Loader2, Search, Network, ArrowRight } from 'lucide-react';
import { toast } from 'sonner';

function fmtEUR(v) {
  if (v === null || v === undefined) return '—';
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M €`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)}k €`;
  return `${v.toLocaleString('es-ES')} €`;
}

export default function ControlGraphPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [root, setRoot] = useState(null);
  const [graph, setGraph] = useState(null);
  const [loading, setLoading] = useState(false);

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

  const loadGraph = async (company) => {
    setLoading(true);
    setRoot(company);
    setQuery(''); setResults([]);
    try {
      const { data } = await api.get(`/data-layer/graph/${company.master_id}/traverse`, {
        params: { max_hops: 2, max_nodes: 150 },
      });
      setGraph(data);
    } catch (e) { toast.error('Error cargando el grafo de control'); setGraph(null); }
    setLoading(false);
  };

  const nodesById = Object.fromEntries((graph?.nodes || []).map(n => [n.master_id, n]));

  return (
    <div className="space-y-5" data-testid="control-graph-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Grafo de control</h1>
        <p className="text-xs text-zinc-500 mt-0.5">T3 — Navegacion multi-salto sobre propiedad real (Q2) + competidores</p>
      </div>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3 space-y-2">
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-zinc-500" />
            <Input value={query} onChange={e => setQuery(e.target.value)}
              placeholder="Buscar empresa para empezar la navegacion..."
              className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs flex-1" />
            {searching && <Loader2 className="w-3.5 h-3.5 animate-spin text-zinc-500" />}
          </div>
          {results.length > 0 && (
            <div className="border border-zinc-800 rounded divide-y divide-zinc-800/70">
              {results.map(c => (
                <div key={c.master_id} className="flex items-center justify-between px-2 py-1.5 hover:bg-zinc-800/30 cursor-pointer"
                  onClick={() => loadGraph(c)}>
                  <span className="text-xs text-zinc-200">{c.legal_name}</span>
                  <span className="text-[10px] text-zinc-600">{c.cnae_code} · {c.provincia || '—'}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {loading && <div className="flex items-center justify-center py-12"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>}

      {graph && !loading && (
        <>
          <div className="flex items-center gap-2">
            <Network className="w-4 h-4 text-blue-400" />
            <span className="text-sm text-zinc-200">Centrado en <strong>{root?.legal_name}</strong></span>
            <Badge variant="outline" className="text-[10px] border-zinc-700 text-zinc-400">
              {graph.node_count} nodos · {graph.edge_count} aristas
            </Badge>
            {graph.truncated && <Badge variant="outline" className="text-[10px] border-amber-500/30 text-amber-400">truncado</Badge>}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-3">
                <p className="text-xs font-semibold text-zinc-300 mb-2">Empresas en el grafo</p>
                <Table>
                  <TableHeader>
                    <TableRow className="border-zinc-800 hover:bg-transparent">
                      <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Empresa</TableHead>
                      <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">Facturacion</TableHead>
                      <TableHead className="w-8" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(graph.nodes || []).map(n => (
                      <TableRow key={n.master_id} className={`border-zinc-800/50 ${n.master_id !== root?.master_id ? 'cursor-pointer hover:bg-zinc-800/30' : ''}`}
                        onClick={() => n.master_id !== root?.master_id && loadGraph({ master_id: n.master_id, legal_name: n.name })}>
                        <TableCell className="py-1.5 text-xs text-zinc-200">
                          {n.name || n.master_id} {n.master_id === root?.master_id && <Badge variant="outline" className="ml-1 text-[9px] border-blue-500/30 text-blue-400">raiz</Badge>}
                        </TableCell>
                        <TableCell className="py-1.5 text-xs text-zinc-400 text-right tabular-nums">{fmtEUR(n.revenue)}</TableCell>
                        <TableCell className="py-1.5">{n.master_id !== root?.master_id && <ArrowRight className="w-3 h-3 text-zinc-600" />}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-3">
                <p className="text-xs font-semibold text-zinc-300 mb-2">Relaciones reales</p>
                <Table>
                  <TableHeader>
                    <TableRow className="border-zinc-800 hover:bg-transparent">
                      <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Origen</TableHead>
                      <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Tipo</TableHead>
                      <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Destino</TableHead>
                      <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 text-right">%</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(graph.edges || []).map((e, i) => (
                      <TableRow key={i} className="border-zinc-800/50">
                        <TableCell className="py-1.5 text-xs text-zinc-300">{nodesById[e.src_master_id]?.name || e.src_master_id || 'externo'}</TableCell>
                        <TableCell className="py-1.5">
                          <Badge variant="outline" className={`text-[9px] ${e.relationship_type === 'competitor_of'
                            ? 'border-rose-500/30 text-rose-400 bg-rose-500/5' : 'border-emerald-500/30 text-emerald-400 bg-emerald-500/5'}`}>
                            {e.relationship_type}
                          </Badge>
                        </TableCell>
                        <TableCell className="py-1.5 text-xs text-zinc-300">{nodesById[e.dst_master_id]?.name || e.dst_master_id || 'externo'}</TableCell>
                        <TableCell className="py-1.5 text-xs text-zinc-400 text-right tabular-nums">{e.pct != null ? `${e.pct}%` : '—'}</TableCell>
                      </TableRow>
                    ))}
                    {(graph.edges || []).length === 0 && (
                      <TableRow><TableCell colSpan={4} className="text-center text-xs text-zinc-500 py-8">Sin relaciones reales detectadas.</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {!graph && !loading && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="py-8 text-center">
            <p className="text-xs text-zinc-600">Busca una empresa para navegar su grafo de control real.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
