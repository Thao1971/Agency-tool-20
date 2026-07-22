import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Layers, Play, ChevronRight } from 'lucide-react';
import api from '@/lib/api';

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState([]);
  const [testCompanyId, setTestCompanyId] = useState('');
  const [testProfile, setTestProfile] = useState('basic');
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    api.get('/intelligence/profiles').then(r => setProfiles(r.data?.profiles || [])).catch(() => {});
  }, []);

  const runTest = async () => {
    if (!testCompanyId.trim()) return;
    setRunning(true);
    setResult(null);
    try {
      const r = await api.post('/intelligence/enrich', {
        master_company_id: testCompanyId.trim(),
        profile: testProfile,
      });
      setResult(r.data);
    } catch (e) {
      setResult({ error: e?.response?.data?.detail || e.message });
    }
    setRunning(false);
  };

  return (
    <div className="space-y-5" data-testid="engine-profiles-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Intelligence Engine — Profiles</h1>
        <p className="text-xs text-zinc-500 mt-0.5">Perfiles declarativos que cada producto consume sobre el motor</p>
      </div>

      {/* Profiles grid */}
      <div className="grid grid-cols-3 gap-3">
        {profiles.map(p => (
          <Card key={p.name} className="bg-zinc-900/50 border-zinc-800" data-testid={`profile-card-${p.name}`}>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs flex items-center gap-2">
                <Layers className="w-3.5 h-3.5 text-violet-400" />
                <span className="font-bold text-zinc-100 uppercase tracking-wider">{p.name}</span>
                <span className="text-[9px] text-zinc-500 tabular-nums ml-auto">{p.sources.length} sources</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-[11px] text-zinc-400 mb-3 leading-relaxed">{p.description}</p>
              <div className="space-y-1">
                {p.sources.map(s => (
                  <div key={s} className="flex items-center gap-1.5 text-[10px] text-zinc-500 font-mono">
                    <ChevronRight className="w-3 h-3 text-zinc-700" /> {s}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Test sandbox */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs text-zinc-400 flex items-center gap-2">
            <Play className="w-3.5 h-3.5 text-emerald-400" /> Test sandbox — ejecutar perfil sobre una compañía
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Input
              value={testCompanyId}
              onChange={e => setTestCompanyId(e.target.value)}
              placeholder="master_company_id (ej: mc_24e7589c-545)"
              className="bg-zinc-950 border-zinc-800 text-xs flex-1"
              data-testid="profile-test-mc-id"
            />
            <select
              value={testProfile}
              onChange={e => setTestProfile(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 text-xs px-3 rounded text-zinc-200"
              data-testid="profile-test-select">
              {profiles.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
            </select>
            <Button onClick={runTest} disabled={running || !testCompanyId.trim()} className="text-xs" data-testid="profile-test-run">
              {running ? 'Ejecutando…' : 'Ejecutar'}
            </Button>
          </div>

          {result && (
            <div className="bg-zinc-950/40 rounded-md p-3 border border-zinc-800/50 space-y-2" data-testid="profile-test-result">
              {result.error ? (
                <p className="text-xs text-rose-400">{result.error}</p>
              ) : (
                <>
                  <div className="flex items-center gap-4 text-[10px]">
                    <span className="text-zinc-500">profile: <strong className="text-zinc-100">{result.profile}</strong></span>
                    <span className="text-zinc-500">duration: <strong className="text-zinc-100 tabular-nums">{result.duration_ms}ms</strong></span>
                    <span className="text-zinc-500">sources with data: <strong className="text-emerald-400">{result.sources_with_data?.length || 0}</strong>/{result.sources_consulted?.length || 0}</span>
                  </div>
                  <div className="space-y-0.5">
                    {result.sources_consulted?.map(s => (
                      <div key={s.source} className="flex items-center justify-between text-[10px] py-0.5 px-2 bg-zinc-900/40 rounded">
                        <span className="flex items-center gap-1.5">
                          <span className={`w-1.5 h-1.5 rounded-full ${s.found ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
                          <span className="font-mono text-zinc-300">{s.source}</span>
                        </span>
                        <span className="text-zinc-500">
                          {s.found ? 'OK' : (s.reason || s.status || s.error || 'no data')}
                        </span>
                      </div>
                    ))}
                  </div>
                  <details className="text-[10px]">
                    <summary className="text-zinc-500 cursor-pointer hover:text-zinc-300">Ver fields ({Object.keys(result.fields || {}).length})</summary>
                    <pre className="mt-2 text-[10px] text-zinc-400 max-h-72 overflow-y-auto font-mono whitespace-pre-wrap break-all">
                      {JSON.stringify(result.fields, null, 2)}
                    </pre>
                  </details>
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
