import { useState, useEffect } from 'react';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Download, FileText, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';

export default function ManualPage() {
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/manual', { responseType: 'text' })
      .then(r => setContent(r.data))
      .catch(() => setContent('Manual not available.'))
      .finally(() => setLoading(false));
  }, []);

  const handleDownload = () => {
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'MANUAL_DE_APLICACION_AGENCIAS.md';
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Manual downloaded');
  };

  // Simple markdown renderer
  const renderMarkdown = (md) => {
    if (!md) return null;
    return md.split('\n').map((line, i) => {
      if (line.startsWith('# ')) return <h1 key={i} className="text-2xl font-bold text-zinc-50 font-heading mt-8 mb-3">{line.slice(2)}</h1>;
      if (line.startsWith('## ')) return <h2 key={i} className="text-xl font-bold text-zinc-100 font-heading mt-6 mb-2 pb-1 border-b border-zinc-800">{line.slice(3)}</h2>;
      if (line.startsWith('### ')) return <h3 key={i} className="text-lg font-semibold text-zinc-200 mt-5 mb-2">{line.slice(4)}</h3>;
      if (line.startsWith('| ')) {
        const cells = line.split('|').filter(c => c.trim()).map(c => c.trim());
        const isHeader = i > 0 && md.split('\n')[i + 1]?.startsWith('|--');
        const isSeparator = line.includes('---');
        if (isSeparator) return null;
        return (
          <div key={i} className={`grid gap-2 px-2 py-1.5 text-xs font-mono ${isHeader ? 'bg-zinc-800 text-zinc-300 font-semibold' : 'text-zinc-400 border-b border-zinc-800/50'}`}
            style={{ gridTemplateColumns: `repeat(${cells.length}, 1fr)` }}>
            {cells.map((c, j) => <span key={j} className="truncate">{c}</span>)}
          </div>
        );
      }
      if (line.startsWith('```')) return <div key={i} className="my-1" />;
      if (line.startsWith('- ')) return <li key={i} className="text-sm text-zinc-300 ml-4 mb-1 list-disc">{line.slice(2)}</li>;
      if (line.startsWith('**') && line.endsWith('**')) return <p key={i} className="text-sm font-bold text-zinc-200 mt-2">{line.replace(/\*\*/g, '')}</p>;
      if (line.startsWith('---')) return <hr key={i} className="border-zinc-800 my-4" />;
      if (line.trim() === '') return <div key={i} className="h-2" />;
      // Code block content
      if (content.split('\n').slice(0, i).reverse().find(l => l.startsWith('```'))?.startsWith('```') &&
          !content.split('\n').slice(0, i).reverse().find((l, idx) => idx > 0 && l.startsWith('```'))) {
        return <pre key={i} className="text-xs font-mono text-zinc-400 bg-zinc-900 px-3">{line}</pre>;
      }
      return <p key={i} className="text-sm text-zinc-300 leading-relaxed">{line}</p>;
    });
  };

  return (
    <div className="space-y-4" data-testid="manual-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">Application Manual</h1>
          <p className="text-sm text-zinc-400 mt-1">Complete technical and functional documentation</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={handleDownload} disabled={loading}
            className="bg-blue-600 hover:bg-blue-500 text-white" data-testid="download-manual-btn">
            <Download className="w-4 h-4 mr-2" /> Download .md
          </Button>
        </div>
      </div>

      <Card className="bg-zinc-900 border-zinc-800">
        <CardContent className="p-0">
          <ScrollArea className="h-[calc(100vh-200px)]">
            <div className="p-6 max-w-4xl">
              {loading ? (
                <p className="text-zinc-500">Loading manual...</p>
              ) : (
                renderMarkdown(content)
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
