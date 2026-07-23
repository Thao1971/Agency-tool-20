import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '@/lib/api';
import { signalLink } from '@/pages/SignalsPage';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Loader2, Eye, Bell, Trash2, Search, CheckCheck } from 'lucide-react';
import { toast } from 'sonner';

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' }); }
  catch { return '—'; }
}

export default function WatchlistPage() {
  const navigate = useNavigate();
  const [watches, setWatches] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [unreadOnly, setUnreadOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);

  const loadAll = useCallback(async (uOnly = unreadOnly) => {
    setLoading(true);
    try {
      const [w, a] = await Promise.all([
        api.get('/watchlist'),
        api.get('/watchlist/alerts', { params: { unread_only: uOnly, limit: 50 } }),
      ]);
      setWatches(w.data.watches || []);
      setAlerts(a.data.alerts || []);
    } catch (e) { toast.error('Error cargando watchlist'); }
    setLoading(false);
  }, [unreadOnly]);

  useEffect(() => { loadAll(); }, [loadAll]);

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

  const addWatch = async (company) => {
    try {
      await api.post('/watchlist', { master_id: company.master_id });
      toast.success(`${company.legal_name} añadida a la watchlist`);
      setQuery(''); setResults([]);
      loadAll();
    } catch (e) { toast.error('Error añadiendo a la watchlist'); }
  };

  const removeWatch = async (masterId) => {
    try {
      await api.delete(`/watchlist/${masterId}`);
      setWatches(prev => prev.filter(w => w.master_id !== masterId));
    } catch (e) { toast.error('Error eliminando'); }
  };

  const markRead = async (alertId) => {
    try {
      await api.post(`/watchlist/alerts/${alertId}/mark-read`);
      setAlerts(prev => prev.filter(a => a.alert_id !== alertId));
    } catch (e) { /* */ }
  };

  const isWatching = (masterId) => watches.some(w => w.master_id === masterId);

  return (
    <div className="space-y-5" data-testid="watchlist-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Watchlist</h1>
        <p className="text-xs text-zinc-500 mt-0.5">Empresas seguidas y alertas in-app (Q7) — sin canal de email/push hoy</p>
      </div>

      {/* Add company */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3 space-y-2">
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-zinc-500" />
            <Input value={query} onChange={e => setQuery(e.target.value)}
              placeholder="Buscar empresa por nombre para seguir..."
              className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs flex-1" />
            {searching && <Loader2 className="w-3.5 h-3.5 animate-spin text-zinc-500" />}
          </div>
          {results.length > 0 && (
            <div className="border border-zinc-800 rounded divide-y divide-zinc-800/70">
              {results.map(c => (
                <div key={c.master_id} className="flex items-center justify-between px-2 py-1.5">
                  <div>
                    <span className="text-xs text-zinc-200">{c.legal_name}</span>
                    <span className="text-[10px] text-zinc-600 ml-2">{c.cnae_code} · {c.provincia || '—'}</span>
                  </div>
                  <Button size="sm" variant="outline" disabled={isWatching(c.master_id)}
                    onClick={() => addWatch(c)} className="h-6 px-2 text-[10px] border-zinc-700">
                    {isWatching(c.master_id) ? 'Ya seguida' : 'Seguir'}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {/* Watched companies */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3">
              <div className="flex items-center gap-2 mb-2">
                <Eye className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-xs font-semibold text-zinc-300">Empresas seguidas ({watches.length})</span>
              </div>
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800 hover:bg-transparent">
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Empresa</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Desde</TableHead>
                    <TableHead className="w-8" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {watches.map(w => (
                    <TableRow key={w.watch_id} className="border-zinc-800/50">
                      <TableCell className="py-2 text-sm text-zinc-200">{w.company_name || w.master_id}</TableCell>
                      <TableCell className="py-2 text-xs text-zinc-500">{fmtDate(w.created_at)}</TableCell>
                      <TableCell className="py-2">
                        <Button variant="ghost" size="sm" onClick={() => removeWatch(w.master_id)}
                          className="h-6 w-6 p-0 text-zinc-500 hover:text-rose-400">
                          <Trash2 className="w-3 h-3" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {watches.length === 0 && (
                    <TableRow><TableCell colSpan={3} className="text-center text-xs text-zinc-500 py-8">
                      Aún no sigues ninguna empresa.
                    </TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Alerts */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Bell className="w-3.5 h-3.5 text-amber-400" />
                  <span className="text-xs font-semibold text-zinc-300">Alertas ({alerts.length})</span>
                </div>
                <Button variant="ghost" size="sm"
                  onClick={() => { setUnreadOnly(!unreadOnly); loadAll(!unreadOnly); }}
                  className="h-6 px-2 text-[10px] text-zinc-400">
                  {unreadOnly ? 'Ver todas' : 'Solo no leídas'}
                </Button>
              </div>
              <div className="space-y-1.5 max-h-[420px] overflow-auto">
                {alerts.map(a => (
                  <div key={a.alert_id} className="flex items-start justify-between gap-2 border border-zinc-800/70 rounded px-2 py-1.5">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs text-zinc-200 truncate">{a.company_name || a.master_id}</span>
                        <Badge
                          variant="outline"
                          className={`text-[9px] border-blue-500/30 text-blue-400 bg-blue-500/5 shrink-0 ${a.signal_id ? 'cursor-pointer hover:bg-blue-500/15' : ''}`}
                          onClick={() => a.signal_id && navigate(signalLink(a.signal_id, a.master_id))}
                        >
                          {a.signal_type}
                        </Badge>
                      </div>
                      <p className="text-[10px] text-zinc-500 mt-0.5 line-clamp-2">{a.explanation}</p>
                      <p className="text-[9px] text-zinc-700 mt-0.5">{fmtDate(a.signal_detected_at)}</p>
                    </div>
                    {!a.read && (
                      <Button variant="ghost" size="sm" onClick={() => markRead(a.alert_id)}
                        className="h-6 w-6 p-0 text-zinc-500 hover:text-emerald-400 shrink-0">
                        <CheckCheck className="w-3.5 h-3.5" />
                      </Button>
                    )}
                  </div>
                ))}
                {alerts.length === 0 && (
                  <p className="text-center text-xs text-zinc-500 py-8">
                    {unreadOnly ? 'Sin alertas pendientes.' : 'Sin alertas.'}
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
