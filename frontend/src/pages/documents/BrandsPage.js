import { useState, useEffect } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Palette, Save, Eye, Loader2, Check } from 'lucide-react';
import { toast } from 'sonner';

const COLOR_TOKENS = [
  { key: 'bg_primary', label: 'Background' },
  { key: 'bg_surface', label: 'Surface' },
  { key: 'text_primary', label: 'Text Primary' },
  { key: 'text_secondary', label: 'Text Secondary' },
  { key: 'accent', label: 'Accent' },
  { key: 'accent_text', label: 'Accent Text' },
  { key: 'border', label: 'Border' },
  { key: 'tag_bg', label: 'Tag Background' },
  { key: 'kpi_value', label: 'KPI Value' },
  { key: 'strengths_bg', label: 'Strengths Background' },
  { key: 'table_header_bg', label: 'Table Header' },
  { key: 'disclaimer_border', label: 'Disclaimer Border' },
];

const COVER_TOKENS = [
  { key: 'bg', label: 'Cover Background' },
  { key: 'text', label: 'Cover Text' },
  { key: 'brand_text', label: 'Cover Brand' },
  { key: 'badge_text', label: 'Badge Text' },
  { key: 'badge_border', label: 'Badge Border' },
];

export default function BrandsPage() {
  const [brands, setBrands] = useState([]);
  const [editing, setEditing] = useState(null);
  const [editData, setEditData] = useState(null);
  const [saving, setSaving] = useState(false);
  const [previewHtml, setPreviewHtml] = useState('');
  const [showPreview, setShowPreview] = useState(false);

  const fetchBrands = async () => {
    try {
      const res = await api.get('/documents/brands');
      setBrands(res.data.brands || []);
    } catch (e) {  }
  };

  useEffect(() => { fetchBrands(); }, []);

  const openEdit = async (brandId) => {
    try {
      const res = await api.get(`/documents/brands/${brandId}`);
      setEditData(res.data);
      setEditing(brandId);
    } catch { toast.error('Failed to load brand'); }
  };

  const updateToken = (section, key, value) => {
    setEditData(prev => ({
      ...prev,
      tokens: {
        ...prev.tokens,
        [section]: { ...(prev.tokens?.[section] || {}), [key]: value }
      }
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put(`/documents/brands/${editing}`, editData);
      toast.success('Brand saved');
      fetchBrands();
    } catch { toast.error('Save failed'); }
    finally { setSaving(false); }
  };

  const handlePreview = async () => {
    try {
      // Save first, then preview
      await api.put(`/documents/brands/${editing}`, editData);
      const res = await api.post('/documents/preview', {
        template_id: 'tpl_agency_report',
        brand_id: editing,
        data_payload: {
          company_name: 'Preview Agency',
          subtitle: 'Brand Preview',
          category: 'Creatividad y Produccion',
          subcategory: 'Agencia creativa',
          executive_summary: 'This is a preview of the brand styling applied to the Agency Report template.',
          confidence_overall: '85', confidence_category: '80',
          num_clients: '5', num_pages_visited: '8',
          has_awards_text: 'Yes', num_tags: '4',
          top_strengths: ['Strong brand identity', 'Clear visual hierarchy', 'Professional styling'],
          top_risks: ['Limited to current tokens', 'No custom fonts yet'],
          clients_list: ['Client A', 'Client B', 'Client C'],
          tags_list: ['branding', 'design system', 'tokens'],
          market_position: 'Preview of how this brand looks in a real document.',
          financial_highlights: 'Financial data would appear here.',
          next_steps: ['Review styling', 'Adjust tokens if needed', 'Generate final document'],
          website: 'https://preview.example.com',
          city: 'Madrid', country: 'Spain',
        }
      }, { responseType: 'text' });
      setPreviewHtml(res.data);
      setShowPreview(true);
    } catch { toast.error('Preview failed'); }
  };

  return (
    <div className="space-y-6" data-testid="brands-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">Brand Profiles</h1>
        <p className="text-sm text-zinc-400 mt-1">Manage visual themes for document generation</p>
      </div>

      {!editing ? (
        /* Brand list */
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {brands.map(b => (
            <Card key={b.brand_id} className="bg-zinc-900 border-zinc-800 hover:border-zinc-600 transition-colors cursor-pointer"
              onClick={() => openEdit(b.brand_id)} data-testid={`brand-card-${b.brand_id}`}>
              <CardContent className="p-5">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center font-bold text-lg"
                    style={{ background: b.tokens?.colors?.accent || b.tokens?.cover?.bg || '#333', color: b.tokens?.colors?.accent_text || '#fff' }}>
                    {b.logo_text || '?'}
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-zinc-100">{b.name}</h3>
                    <p className="text-xs text-zinc-500">{b.brand_id}</p>
                  </div>
                  {b.is_default && (
                    <Badge className="ml-auto bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px]">Default</Badge>
                  )}
                </div>
                <div className="flex gap-1">
                  {['bg_primary', 'accent', 'text_primary', 'border'].map(tok => (
                    <div key={tok} className="w-6 h-6 rounded border border-zinc-700"
                      style={{ background: b.tokens?.colors?.[tok] || '#333' }}
                      title={tok} />
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        /* Brand editor */
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button variant="outline" size="sm" onClick={() => { setEditing(null); setEditData(null); }}
                className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">Back</Button>
              <h2 className="text-lg font-bold text-zinc-100 font-heading">{editData?.name}</h2>
              <Badge variant="outline" className="text-[10px] text-zinc-400 border-zinc-600">{editing}</Badge>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={handlePreview}
                className="border-zinc-700 text-zinc-300 hover:bg-zinc-800" data-testid="brand-preview-btn">
                <Eye className="w-3.5 h-3.5 mr-1.5" /> Preview
              </Button>
              <Button size="sm" onClick={handleSave} disabled={saving}
                className="bg-blue-600 hover:bg-blue-500 text-white" data-testid="brand-save-btn">
                {saving ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Save className="w-3.5 h-3.5 mr-1.5" />}
                Save
              </Button>
            </div>
          </div>

          {/* Identity */}
          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2 pt-4 px-5">
              <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Identity</CardTitle>
            </CardHeader>
            <CardContent className="px-5 pb-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1">
                  <Label className="text-zinc-400 text-xs">Name</Label>
                  <Input value={editData?.name || ''} onChange={e => setEditData(p => ({...p, name: e.target.value}))}
                    className="bg-zinc-950 border-zinc-700 text-zinc-50" />
                </div>
                <div className="space-y-1">
                  <Label className="text-zinc-400 text-xs">Logo Text (fallback)</Label>
                  <Input value={editData?.logo_text || ''} onChange={e => setEditData(p => ({...p, logo_text: e.target.value}))}
                    className="bg-zinc-950 border-zinc-700 text-zinc-50" />
                </div>
                <div className="space-y-1">
                  <Label className="text-zinc-400 text-xs">Default</Label>
                  <p className="text-sm text-zinc-300 pt-1">{editData?.is_default ? 'Yes' : 'No'}</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 mt-3">
                <div className="space-y-1">
                  <Label className="text-zinc-400 text-xs">Logo Light (URL for dark backgrounds)</Label>
                  <Input value={editData?.logo_light || ''} onChange={e => setEditData(p => ({...p, logo_light: e.target.value}))}
                    placeholder="https://..." className="bg-zinc-950 border-zinc-700 text-zinc-50" />
                </div>
                <div className="space-y-1">
                  <Label className="text-zinc-400 text-xs">Logo Dark (URL for light backgrounds)</Label>
                  <Input value={editData?.logo_dark || ''} onChange={e => setEditData(p => ({...p, logo_dark: e.target.value}))}
                    placeholder="https://..." className="bg-zinc-950 border-zinc-700 text-zinc-50" />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Color tokens */}
          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2 pt-4 px-5">
              <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium flex items-center gap-2">
                <Palette className="w-3 h-3" /> Color Tokens
              </CardTitle>
            </CardHeader>
            <CardContent className="px-5 pb-4">
              <div className="grid grid-cols-3 gap-3">
                {COLOR_TOKENS.map(t => (
                  <div key={t.key} className="flex items-center gap-2">
                    <input type="color" value={editData?.tokens?.colors?.[t.key] || '#000000'}
                      onChange={e => updateToken('colors', t.key, e.target.value)}
                      className="w-8 h-8 rounded border border-zinc-700 bg-transparent cursor-pointer" />
                    <div>
                      <p className="text-xs text-zinc-300">{t.label}</p>
                      <p className="text-[10px] font-mono text-zinc-500">{editData?.tokens?.colors?.[t.key]}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Cover tokens */}
          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2 pt-4 px-5">
              <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Cover Styling</CardTitle>
            </CardHeader>
            <CardContent className="px-5 pb-4">
              <div className="grid grid-cols-3 gap-3">
                {COVER_TOKENS.map(t => (
                  <div key={t.key} className="flex items-center gap-2">
                    <input type="color" value={editData?.tokens?.cover?.[t.key] || '#000000'}
                      onChange={e => updateToken('cover', t.key, e.target.value)}
                      className="w-8 h-8 rounded border border-zinc-700 bg-transparent cursor-pointer" />
                    <div>
                      <p className="text-xs text-zinc-300">{t.label}</p>
                      <p className="text-[10px] font-mono text-zinc-500">{editData?.tokens?.cover?.[t.key]}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Preview dialog */}
      <Dialog open={showPreview} onOpenChange={setShowPreview}>
        <DialogContent className="bg-zinc-900 border-zinc-700 max-w-5xl h-[80vh]">
          <DialogHeader>
            <DialogTitle className="text-zinc-50 font-heading">Brand Preview — {editData?.name}</DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-hidden rounded border border-zinc-700" style={{ height: 'calc(80vh - 80px)' }}>
            <iframe srcDoc={previewHtml} title="Brand Preview" className="w-full h-full" style={{ border: 'none' }} />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
