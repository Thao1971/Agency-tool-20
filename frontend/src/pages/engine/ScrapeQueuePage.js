import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Workflow, RefreshCw } from 'lucide-react';
import api from '@/lib/api';

export default function ScrapeQueuePage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get('/intelligence/scrape-queue');
      setData(r.data);
    } catch {}
    setLoading(false);
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  const counts = data?.counts || {};
  const jobs = data?.recent_jobs || [];

  return (
    <div className="space-y-5" data-testid="engine-scrape-queue-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-zinc-100">Intelligence Engine — Scrape Queue</h1>
          <p className="text-xs text-zinc-500 mt-0.5">Cola de scrapes encolados por el web source · auto-refresh 10s</p>
        </div>
        <Button onClick={load} disabled={loading} variant="outline" size="sm" className="text-xs" data-testid="queue-refresh-btn">
          <RefreshCw className={`w-3 h-3 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Refrescar
        </Button>
      </div>

      <div className="grid grid-cols-4 gap-3">
        {['pending', 'claimed', 'processing', 'failed'].map((s) => {
          const colors = {
            pending: 'text-zinc-300 bg-zinc-500/10 border-zinc-700',
            claimed: 'text-amber-400 bg-amber-500/10 border-amber-700/50',
            processing: 'text-blue-400 bg-blue-500/10 border-blue-700/50',
            failed: 'text-rose-400 bg-rose-500/10 border-rose-700/50',
          };
          return (
            <Card key={s} className={`border ${colors[s]}`} data-testid={`queue-stat-${s}`}>
              <CardContent className="p-4">
                <p className="text-[10px] uppercase tracking-wider opacity-80 mb-1">{s}</p>
                <p className={`text-2xl font-bold tabular-nums ${colors[s].split(' ')[0]}`}>{counts[s] ?? 0}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
            <Workflow className="w-3.5 h-3.5 text-blue-400" /> Últimos jobs ({jobs.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {jobs.length === 0 ? (
            <p className="text-xs text-zinc-600 py-8 text-center">Sin jobs recientes</p>
          ) : (
            <div className="space-y-1" data-testid="queue-jobs-list">
              {jobs.map(j => (
                <div key={j.id} className="grid grid-cols-12 gap-2 items-center text-[11px] py-1.5 px-2 bg-zinc-950/30 rounded hover:bg-zinc-900/40">
                  <span className="col-span-2 font-mono text-zinc-500">{j.id.substring(0, 16)}</span>
                  <span className={`col-span-1 text-[10px] uppercase tracking-wider ${
                    j.status === 'pending' ? 'text-zinc-400' :
                    j.status === 'processing' ? 'text-blue-400' :
                    j.status === 'claimed' ? 'text-amber-400' :
                    j.status === 'failed' ? 'text-rose-400' : 'text-emerald-400'
                  }`}>{j.status}</span>
                  <span className="col-span-2 font-mono text-zinc-500 text-[10px]">{(j.entity_id || '').substring(0, 16)}</span>
                  <span className="col-span-5 text-zinc-300 truncate">{j.url}</span>
                  <span className="col-span-2 text-[10px] text-zinc-600 text-right">{j.created_at ? new Date(j.created_at).toLocaleString('es-ES') : ''}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
