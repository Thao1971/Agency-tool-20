import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Heart, Workflow, Layers, RefreshCw, AlertTriangle, Clock, Activity, Database, Play, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import api from '@/lib/api';

function Stat({ label, value, color = 'text-zinc-100', dot, testid }) {
  return (
    <div className="bg-zinc-950/40 rounded-md p-3 border border-zinc-800/50" data-testid={testid}>
      <div className="flex items-center gap-1.5 mb-1">
        {dot && <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />}
        <p className="text-[9px] uppercase tracking-wider text-zinc-500">{label}</p>
      </div>
      <p className={`text-xl font-bold tabular-nums ${color}`}>{value ?? '—'}</p>
    </div>
  );
}

export default function HealthPage() {
  const [valuoHealth, setValuoHealth] = useState(null);
  const [scrapeQueue, setScrapeQueue] = useState(null);
  const [profiles, setProfiles] = useState([]);
  const [sources, setSources] = useState({});
  const [ingesting, setIngesting] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [v, q, p, s] = await Promise.all([
        api.get('/valuo/health').catch(() => ({ data: null })),
        api.get('/intelligence/scrape-queue').catch(() => ({ data: null })),
        api.get('/intelligence/profiles').catch(() => ({ data: { profiles: [] } })),
        api.get('/public/intelligence/sync-status').catch(() => ({ data: { sources: {} } })),
      ]);
      setValuoHealth(v.data);
      setScrapeQueue(q.data);
      setProfiles(p.data?.profiles || []);
      setSources(s.data?.sources || {});
      setLastRefresh(new Date());
    } catch {}
    setLoading(false);
  };

  const triggerIngest = async (source) => {
    setIngesting(source);
    try {
      const r = await api.post(`/intelligence/sources/ingest/${source}`);
      const res = r.data || {};
      if (res.status === 'error') {
        toast.error(`Ingesta ${source} falló: ${res.reason || 'error desconocido'}`);
      } else {
        toast.success(`Ingesta ${source}: ${res.inserted ?? 0} insertados`);
      }
      await load();
    } catch (e) {
      toast.error(`No se pudo ejecutar la ingesta de ${source}`);
    }
    setIngesting(null);
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);

  const verdict = valuoHealth?.verdict || 'healthy';
  const verdictCfg = {
    healthy:  { dot: 'bg-emerald-500', text: 'text-emerald-400', label: 'Operativo' },
    busy:     { dot: 'bg-amber-500',   text: 'text-amber-400',   label: 'Alta carga' },
    stuck:    { dot: 'bg-rose-500',    text: 'text-rose-400',    label: 'Atascado' },
    degraded: { dot: 'bg-rose-600',    text: 'text-rose-400',    label: 'Degradado' },
  }[verdict];

  const by = valuoHealth?.by_status || {};
  const queueCounts = scrapeQueue?.counts || {};
  const timeline = valuoHealth?.timeline_last_hour || [];
  const maxBucket = Math.max(1, ...timeline.map(b => b.completed + b.failed + b.pending + b.processing));

  return (
    <div className="space-y-5" data-testid="engine-health-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-zinc-100">Intelligence Engine — Health</h1>
          <p className="text-xs text-zinc-500 mt-0.5">Observabilidad del motor: requests, sources, profiles, scrape queue</p>
        </div>
        <button onClick={load} disabled={loading}
          className="text-[10px] text-zinc-500 hover:text-zinc-300 flex items-center gap-1 transition-colors"
          data-testid="health-refresh-btn">
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> refrescar
          {lastRefresh && <span className="text-zinc-600 ml-1">{lastRefresh.toLocaleTimeString('es-ES')}</span>}
        </button>
      </div>

      {/* Verdict + Requests */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
            <Heart className={`w-3.5 h-3.5 ${verdictCfg?.text}`} />
            Requests (Valuo Enrichment Pipeline)
            <span className={`w-2 h-2 rounded-full ${verdictCfg?.dot} animate-pulse ml-1`} />
            <span className={`text-[10px] ${verdictCfg?.text} font-medium uppercase tracking-wider`}>{verdictCfg?.label}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-5 gap-2">
            <Stat label="Pending" value={by.pending ?? 0} dot="bg-zinc-500" color="text-zinc-300" testid="health-req-pending" />
            <Stat label="Processing" value={by.processing ?? 0} dot="bg-blue-500" color="text-blue-400" testid="health-req-processing" />
            <Stat label="Completed" value={by.completed ?? 0} dot="bg-emerald-500" color="text-emerald-400" testid="health-req-completed" />
            <Stat label="Failed" value={by.failed ?? 0} dot="bg-rose-500" color="text-rose-400" testid="health-req-failed" />
            <div className="bg-zinc-950/40 rounded-md p-3 border border-zinc-800/50" data-testid="health-req-duration">
              <p className="text-[9px] uppercase tracking-wider text-zinc-500">Duración p50 / p95</p>
              <p className="text-xl font-bold text-zinc-100 tabular-nums">
                {valuoHealth?.duration_ms?.p50 ?? '—'}
                <span className="text-zinc-500 mx-1">/</span>
                {valuoHealth?.duration_ms?.p95 ?? '—'}
                <span className="text-[9px] text-zinc-500 ml-1">ms</span>
              </p>
            </div>
          </div>

          {valuoHealth?.oldest_stuck && (
            <div className="bg-rose-500/10 border border-rose-500/30 rounded-md p-2 flex items-start gap-2" data-testid="health-stuck">
              <AlertTriangle className="w-3.5 h-3.5 text-rose-400 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <p className="text-xs text-rose-300 font-medium">Petición atascada &gt; 5 min</p>
                <p className="text-[10px] text-zinc-400 mt-0.5">
                  <span className="font-mono">{valuoHealth.oldest_stuck.request_id}</span>
                  {valuoHealth.oldest_stuck.created_at && <span className="ml-2 text-zinc-500">desde {new Date(valuoHealth.oldest_stuck.created_at).toLocaleTimeString('es-ES')}</span>}
                </p>
              </div>
            </div>
          )}

          {/* Timeline */}
          <div>
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Última hora (bins de 5 min)</p>
            <div className="flex items-end gap-0.5 h-14" data-testid="health-timeline">
              {timeline.map((b, i) => {
                const total = b.completed + b.failed + b.pending + b.processing;
                const h = total === 0 ? 4 : Math.max(6, Math.round((total / maxBucket) * 100));
                const showLabel = i % 3 === 0;
                return (
                  <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
                    <div className="w-full flex flex-col-reverse" style={{ height: `${h}%` }}>
                      {b.completed > 0 && <div className="bg-emerald-500/70 w-full" style={{ flex: b.completed }} />}
                      {b.processing > 0 && <div className="bg-blue-500/70 w-full" style={{ flex: b.processing }} />}
                      {b.pending > 0 && <div className="bg-zinc-500/70 w-full" style={{ flex: b.pending }} />}
                      {b.failed > 0 && <div className="bg-rose-500/70 w-full" style={{ flex: b.failed }} />}
                      {total === 0 && <div className="bg-zinc-800/40 w-full h-full" />}
                    </div>
                    <p className="text-[8px] text-zinc-600 leading-none" style={{ visibility: showLabel ? 'visible' : 'hidden' }}>{b.label}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Scrape Queue */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
            <Workflow className="w-3.5 h-3.5 text-blue-400" /> Scrape Queue (Web Source)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-4 gap-2">
            <Stat label="Pending" value={queueCounts.pending ?? 0} dot="bg-zinc-500" testid="queue-pending" />
            <Stat label="Claimed" value={queueCounts.claimed ?? 0} dot="bg-amber-500" color="text-amber-400" testid="queue-claimed" />
            <Stat label="Processing" value={queueCounts.processing ?? 0} dot="bg-blue-500" color="text-blue-400" testid="queue-processing" />
            <Stat label="Failed" value={queueCounts.failed ?? 0} dot="bg-rose-500" color="text-rose-400" testid="queue-failed" />
          </div>
          {scrapeQueue?.recent_jobs?.length > 0 && (
            <div className="border-t border-zinc-800/50 pt-2">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">Últimos jobs</p>
              <div className="space-y-1 max-h-56 overflow-y-auto" data-testid="queue-recent-jobs">
                {scrapeQueue.recent_jobs.map((j) => (
                  <div key={j.id} className="flex items-center justify-between text-[10px] py-1 px-2 bg-zinc-950/30 rounded">
                    <span className="font-mono text-zinc-500">{j.id.substring(0, 12)}</span>
                    <span className={`uppercase tracking-wider ${
                      j.status === 'pending' ? 'text-zinc-400' :
                      j.status === 'processing' ? 'text-blue-400' :
                      j.status === 'claimed' ? 'text-amber-400' : 'text-rose-400'
                    }`}>{j.status}</span>
                    <span className="text-zinc-400 truncate max-w-[280px]">{j.url}</span>
                    <span className="text-zinc-600">{j.created_at ? new Date(j.created_at).toLocaleTimeString('es-ES') : ''}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Fuentes Públicas (Intelligence Engine) — dynamic, driven by sync-status */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
            <Database className="w-3.5 h-3.5 text-emerald-400" /> Fuentes Públicas (Intelligence Engine)
            <span className="text-[9px] text-zinc-600 tabular-nums ml-1">{Object.keys(sources).length} fuentes</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3" data-testid="health-public-sources">
            {Object.entries(sources).map(([key, src]) => {
              const phaseCfg = {
                active: { dot: 'bg-emerald-500', label: 'Activo', color: 'text-emerald-400' },
                derived: { dot: 'bg-cyan-500', label: 'Derivado', color: 'text-cyan-400' },
                stub: { dot: 'bg-zinc-500', label: 'Stub (Fase 2)', color: 'text-zinc-400' },
              }[src.phase] || { dot: 'bg-zinc-500', label: src.phase, color: 'text-zinc-400' };
              const runErr = src.last_status && src.last_status !== 'ok';
              return (
                <div key={key} className="bg-zinc-950/40 rounded-md p-3 border border-zinc-800/50 flex flex-col gap-2" data-testid={`health-source-${key}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-zinc-100 truncate">{src.name}</p>
                      <span className="text-[9px] text-zinc-500 font-mono">{src.source}</span>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <span className={`w-1.5 h-1.5 rounded-full ${phaseCfg.dot}`} />
                      <span className={`text-[9px] ${phaseCfg.color}`}>{phaseCfg.label}</span>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5 text-[10px]">
                    <div><span className="text-zinc-600">Registros</span><br /><span className="text-zinc-200 tabular-nums font-medium">{(src.records ?? 0).toLocaleString('es-ES')}</span></div>
                    <div><span className="text-zinc-600">Señales</span><br /><span className="text-violet-300 tabular-nums font-medium">{(src.signals_count ?? 0).toLocaleString('es-ES')}</span></div>
                    <div><span className="text-zinc-600">Última ejecución</span><br /><span className={`tabular-nums ${runErr ? 'text-rose-400' : 'text-zinc-300'}`} title={src.last_run || ''}>{src.last_run ? new Date(src.last_run).toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}</span></div>
                    <div><span className="text-zinc-600">Duración</span><br /><span className="text-zinc-300 tabular-nums">{src.duration_ms != null ? `${src.duration_ms} ms` : '—'}</span></div>
                    <div><span className="text-zinc-600">Insertados</span><br /><span className="text-zinc-300 tabular-nums">{src.inserted_count != null ? src.inserted_count.toLocaleString('es-ES') : '—'}</span></div>
                    <div><span className="text-zinc-600">Errores</span><br /><span className={`tabular-nums ${src.error_count > 0 ? 'text-rose-400 font-medium' : 'text-zinc-300'}`}>{src.error_count != null ? src.error_count : '—'}</span></div>
                  </div>
                  <p className="text-[9px] text-zinc-600">{src.frequency}</p>
                  {src.supports_manual_ingestion && (
                    <button
                      onClick={() => triggerIngest(src.source)}
                      disabled={ingesting === src.source}
                      className="mt-1 w-full flex items-center justify-center gap-1.5 text-[10px] font-medium px-2 py-1.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 transition-colors disabled:opacity-50"
                      data-testid={`health-ingest-btn-${src.source}`}>
                      {ingesting === src.source ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                      {ingesting === src.source ? 'Ejecutando…' : 'Ejecutar ahora'}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Profiles */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
            <Layers className="w-3.5 h-3.5 text-violet-400" /> Profiles disponibles
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-3" data-testid="health-profiles">
            {profiles.map(p => (
              <div key={p.name} className="bg-zinc-950/40 rounded-md p-3 border border-zinc-800/50" data-testid={`profile-${p.name}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold text-zinc-100 uppercase tracking-wider">{p.name}</span>
                  <span className="text-[9px] text-zinc-500 tabular-nums">{p.sources.length} sources</span>
                </div>
                <p className="text-[10px] text-zinc-500 mb-2 leading-relaxed">{p.description}</p>
                <div className="flex flex-wrap gap-1">
                  {p.sources.map(s => (
                    <span key={s} className="text-[9px] px-1.5 py-0.5 bg-zinc-900 border border-zinc-800 rounded text-zinc-400 font-mono">{s}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
