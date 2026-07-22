import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Search, FileText, Image, ListChecks, Settings, Radar, Palette, Landmark } from 'lucide-react';

const TOOL_ICONS = {
  scraper: Radar,
  documents: FileText,
  assets: Palette,
  borme: Landmark,
};

const TOOL_COLORS = {
  scraper: 'bg-blue-600/15 text-blue-400 group-hover:bg-blue-600/25',
  documents: 'bg-amber-600/15 text-amber-400 group-hover:bg-amber-600/25',
  assets: 'bg-violet-600/15 text-violet-400 group-hover:bg-violet-600/25',
  borme: 'bg-rose-600/15 text-rose-400 group-hover:bg-rose-600/25',
};

export default function HubPage() {
  const [tools, setTools] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    api.get('/hub/tools').then(r => setTools(r.data.tools)).catch((e) => {  });
  }, []);

  return (
    <div className="space-y-8" data-testid="hub-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">Agency Tools Hub</h1>
        <p className="text-sm text-zinc-400 mt-1">Transversal tools for CIS, Arroba and future platforms</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {tools.map(tool => {
          const Icon = TOOL_ICONS[tool.id] || ListChecks;
          return (
            <Card key={tool.id}
              className="bg-zinc-900 border-zinc-800 hover:border-zinc-600 transition-colors cursor-pointer group"
              onClick={() => navigate(tool.path)}
              data-testid={`tool-${tool.id}`}
            >
              <CardContent className="p-6">
                <div className="flex items-start gap-4">
                  <div className={`w-11 h-11 rounded-lg flex items-center justify-center border border-transparent transition-colors ${TOOL_COLORS[tool.id] || 'bg-zinc-700/30 text-zinc-400'}`}>
                    <Icon className="w-5 h-5" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-bold text-zinc-100 font-heading">{tool.name}</h3>
                      <Badge className="text-[9px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        {tool.status}
                      </Badge>
                    </div>
                    <p className="text-xs text-zinc-400 mt-1">{tool.description}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
