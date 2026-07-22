import { useState, useEffect } from 'react';
import { configAPI } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Save, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

export default function SettingsPage() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    configAPI.get()
      .then(r => setConfig(r.data))
      .catch(() => toast.error('Failed to load config'))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updates = {
        max_depth: config.max_depth,
        max_pages: config.max_pages,
        capture_internal_pages: config.capture_internal_pages,
        timeout_seconds: config.timeout_seconds,
        concurrency_limit: config.concurrency_limit,
        export_format: config.export_format,
        callback_url: config.callback_url || null,
        priority_patterns: config.priority_patterns,
      };
      const res = await configAPI.update(updates);
      setConfig(res.data);
      toast.success('Configuration saved');
    } catch (err) {
      toast.error('Failed to save config');
    } finally {
      setSaving(false);
    }
  };

  if (loading || !config) {
    return <div className="text-zinc-500">Loading configuration...</div>;
  }

  return (
    <div className="space-y-6" data-testid="settings-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">Settings</h1>
          <p className="text-sm text-zinc-400 mt-1">Configure scraping engine and integrations</p>
        </div>
        <Button onClick={handleSave} disabled={saving}
          data-testid="save-settings-btn"
          className="bg-blue-600 hover:bg-blue-500 text-white">
          {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
          Save Settings
        </Button>
      </div>

      <Tabs defaultValue="scraping" className="space-y-4">
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="scraping" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400"
            data-testid="tab-scraping">Scraping Engine</TabsTrigger>
          <TabsTrigger value="export" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400"
            data-testid="tab-export">Export</TabsTrigger>
          <TabsTrigger value="webhooks" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400"
            data-testid="tab-webhooks">Webhooks</TabsTrigger>
        </TabsList>

        <TabsContent value="scraping">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardContent className="p-6 space-y-6">
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label className="text-zinc-300 text-xs uppercase tracking-wider">Max Pages per Analysis</Label>
                  <Input type="number" value={config.max_pages}
                    onChange={(e) => setConfig(p => ({...p, max_pages: parseInt(e.target.value) || 10}))}
                    data-testid="config-max-pages"
                    className="bg-zinc-950 border-zinc-700 text-zinc-50 w-32" />
                  <p className="text-xs text-zinc-500">Maximum internal pages to visit</p>
                </div>
                <div className="space-y-2">
                  <Label className="text-zinc-300 text-xs uppercase tracking-wider">Max Depth</Label>
                  <Input type="number" value={config.max_depth}
                    onChange={(e) => setConfig(p => ({...p, max_depth: parseInt(e.target.value) || 2}))}
                    data-testid="config-max-depth"
                    className="bg-zinc-950 border-zinc-700 text-zinc-50 w-32" />
                </div>
                <div className="space-y-2">
                  <Label className="text-zinc-300 text-xs uppercase tracking-wider">Timeout (seconds)</Label>
                  <Input type="number" value={config.timeout_seconds}
                    onChange={(e) => setConfig(p => ({...p, timeout_seconds: parseInt(e.target.value) || 30}))}
                    data-testid="config-timeout"
                    className="bg-zinc-950 border-zinc-700 text-zinc-50 w-32" />
                </div>
                <div className="space-y-2">
                  <Label className="text-zinc-300 text-xs uppercase tracking-wider">Concurrency Limit</Label>
                  <Input type="number" value={config.concurrency_limit}
                    onChange={(e) => setConfig(p => ({...p, concurrency_limit: parseInt(e.target.value) || 3}))}
                    data-testid="config-concurrency"
                    className="bg-zinc-950 border-zinc-700 text-zinc-50 w-32" />
                </div>
              </div>

              <Separator className="bg-zinc-800" />

              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-zinc-300 text-sm">Capture Internal Pages</Label>
                  <p className="text-xs text-zinc-500">Navigate to about, services, contact pages</p>
                </div>
                <Switch
                  checked={config.capture_internal_pages}
                  onCheckedChange={(v) => setConfig(p => ({...p, capture_internal_pages: v}))}
                  className="data-[state=checked]:bg-blue-600"
                  data-testid="config-capture-internal"
                />
              </div>

              <Separator className="bg-zinc-800" />

              <div className="space-y-2">
                <Label className="text-zinc-300 text-xs uppercase tracking-wider">Priority URL Patterns</Label>
                <p className="text-xs text-zinc-500 mb-2">One pattern per line. Pages matching these patterns will be visited first.</p>
                <textarea
                  value={(config.priority_patterns || []).join('\n')}
                  onChange={(e) => setConfig(p => ({...p, priority_patterns: e.target.value.split('\n').filter(Boolean)}))}
                  rows={8}
                  data-testid="config-patterns"
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200 font-mono focus:ring-1 focus:ring-blue-500 focus:border-blue-500 resize-none"
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="export">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardContent className="p-6">
              <div className="space-y-2">
                <Label className="text-zinc-300 text-xs uppercase tracking-wider">Default Export Format</Label>
                <div className="flex gap-3">
                  {['json', 'csv', 'excel'].map(fmt => (
                    <Button key={fmt}
                      variant={config.export_format === fmt ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setConfig(p => ({...p, export_format: fmt}))}
                      className={config.export_format === fmt
                        ? 'bg-blue-600 text-white'
                        : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'}
                    >
                      {fmt.toUpperCase()}
                    </Button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="webhooks">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardContent className="p-6 space-y-4">
              <div className="space-y-2">
                <Label className="text-zinc-300 text-xs uppercase tracking-wider">Default Callback URL</Label>
                <Input value={config.callback_url || ''}
                  onChange={(e) => setConfig(p => ({...p, callback_url: e.target.value}))}
                  placeholder="https://your-system.com/webhook"
                  data-testid="config-callback-url"
                  className="bg-zinc-950 border-zinc-700 text-zinc-50 placeholder:text-zinc-600" />
                <p className="text-xs text-zinc-500">Will be called when a job or bulk job completes</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
