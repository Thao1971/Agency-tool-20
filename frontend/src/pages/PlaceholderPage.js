import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Construction } from 'lucide-react';

export default function PlaceholderPage({ title, subtitle, hint }) {
  return (
    <div className="space-y-5" data-testid="placeholder-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">{title}</h1>
        {subtitle && <p className="text-xs text-zinc-500 mt-0.5">{subtitle}</p>}
      </div>
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-12 text-center">
          <Construction className="w-8 h-8 text-zinc-600 mx-auto mb-3" />
          <p className="text-xs text-zinc-400 mb-1">Sección en construcción</p>
          {hint && <p className="text-[10px] text-zinc-600 max-w-md mx-auto leading-relaxed">{hint}</p>}
        </CardContent>
      </Card>
    </div>
  );
}
