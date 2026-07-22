import { useState, useEffect } from 'react';
import { docsAPI } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';

const METHOD_COLORS = {
  GET: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  POST: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  PUT: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  DELETE: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
};

export default function ApiDocsPage() {
  const [docs, setDocs] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    docsAPI.get()
      .then(r => setDocs(r.data))
      .catch(() => {});
  }, []);

  if (!docs) return <div className="text-zinc-500">Loading API docs...</div>;

  const endpoints = docs.endpoints || [];

  return (
    <div className="space-y-6" data-testid="api-docs-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">API Documentation</h1>
        <p className="text-sm text-zinc-400 mt-1">
          {docs.service} v{docs.version} — Base URL: <code className="text-blue-400 font-mono text-xs">{docs.base_url}</code>
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Endpoint list */}
        <div className="lg:col-span-2">
          <ScrollArea className="h-[calc(100vh-200px)]">
            <div className="space-y-1 pr-4">
              {endpoints.map((ep, i) => (
                <div
                  key={i}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded cursor-pointer transition-colors ${
                    selected === i ? 'bg-zinc-800' : 'hover:bg-zinc-800/50'
                  }`}
                  onClick={() => setSelected(i)}
                  data-testid={`api-endpoint-${i}`}
                >
                  <Badge className={`text-[10px] font-mono w-14 justify-center border ${METHOD_COLORS[ep.method]}`}>
                    {ep.method}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-mono text-zinc-300 truncate">{ep.path}</p>
                    <p className="text-[10px] text-zinc-500 truncate">{ep.description}</p>
                  </div>
                  {ep.auth && (
                    <Badge variant="outline" className="text-[10px] text-zinc-500 border-zinc-700 shrink-0">
                      Auth
                    </Badge>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>
        </div>

        {/* Detail */}
        <div className="lg:col-span-3">
          {selected !== null && endpoints[selected] ? (
            <Card className="bg-zinc-900 border-zinc-800 sticky top-0">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-3">
                  <Badge className={`text-xs font-mono border ${METHOD_COLORS[endpoints[selected].method]}`}>
                    {endpoints[selected].method}
                  </Badge>
                  <code className="text-sm font-mono text-zinc-100">{endpoints[selected].path}</code>
                </div>
                <p className="text-sm text-zinc-400 mt-2">{endpoints[selected].description}</p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-2">
                  <Badge variant="outline" className={`text-xs ${endpoints[selected].auth ? 'text-amber-400 border-amber-500/30' : 'text-emerald-400 border-emerald-500/30'}`}>
                    {endpoints[selected].auth ? 'Requires Authentication' : 'Public'}
                  </Badge>
                </div>

                {endpoints[selected].body && (
                  <>
                    <Separator className="bg-zinc-800" />
                    <div>
                      <p className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium mb-2">Request Body</p>
                      <pre className="bg-zinc-950 border border-zinc-800 rounded p-3 text-xs font-mono text-zinc-300 overflow-x-auto">
                        {JSON.stringify(endpoints[selected].body, null, 2)}
                      </pre>
                    </div>
                  </>
                )}

                {endpoints[selected].params && (
                  <>
                    <Separator className="bg-zinc-800" />
                    <div>
                      <p className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium mb-2">Query Parameters</p>
                      <pre className="bg-zinc-950 border border-zinc-800 rounded p-3 text-xs font-mono text-zinc-300 overflow-x-auto">
                        {JSON.stringify(endpoints[selected].params, null, 2)}
                      </pre>
                    </div>
                  </>
                )}

                {endpoints[selected].response && (
                  <>
                    <Separator className="bg-zinc-800" />
                    <div>
                      <p className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium mb-2">Response</p>
                      <pre className="bg-zinc-950 border border-zinc-800 rounded p-3 text-xs font-mono text-zinc-300 overflow-x-auto">
                        {JSON.stringify(endpoints[selected].response, null, 2)}
                      </pre>
                    </div>
                  </>
                )}

                <Separator className="bg-zinc-800" />
                <div>
                  <p className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium mb-2">cURL Example</p>
                  <pre className="bg-zinc-950 border border-zinc-800 rounded p-3 text-xs font-mono text-zinc-300 overflow-x-auto whitespace-pre-wrap">
{`curl -X ${endpoints[selected].method} \\
  "${window.location.origin}${endpoints[selected].path}" \\${endpoints[selected].auth ? `
  -H "Authorization: Bearer <token>" \\` : ''}${endpoints[selected].body ? `
  -H "Content-Type: application/json" \\
  -d '${JSON.stringify(endpoints[selected].body)}'` : ''}`}
                  </pre>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardContent className="p-12 text-center text-zinc-500">
                Select an endpoint to view details
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
