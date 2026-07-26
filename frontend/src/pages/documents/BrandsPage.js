import { useState, useEffect, useRef, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Palette, Save, Loader2, Type } from 'lucide-react';
import { toast } from 'sonner';

// Grupos de tokens de color (todos los que usa el renderizador de slides).
const COLOR_GROUPS = [
  { title: 'Base', keys: [
    ['bg_primary', 'Fondo'], ['bg_surface', 'Superficie'], ['text_primary', 'Texto'],
    ['text_secondary', 'Texto 2º'], ['text_muted', 'Texto tenue'], ['border', 'Borde'] ] },
  { title: 'Acento y KPIs', keys: [
    ['accent', 'Acento'], ['accent_text', 'Texto sobre acento'], ['kpi_value', 'Valor KPI'],
    ['kpi_label', 'Etiqueta KPI'], ['tag_bg', 'Etiqueta fondo'], ['tag_text', 'Etiqueta texto'] ] },
  { title: 'Tablas', keys: [
    ['table_header_bg', 'Cabecera tabla'], ['table_header_text', 'Texto cabecera'],
    ['table_row_alt', 'Fila alterna'] ] },
];
const COVER_TOKENS = [
  ['bg', 'Fondo portada'], ['text', 'Texto portada'], ['brand_text', 'Acento portada'],
  ['subtitle_text', 'Subtítulo'],
];
const FONT_OPTIONS = [
  { label: 'Montserrat', value: "'Montserrat', sans-serif" },
  { label: 'Inter', value: "'Inter', sans-serif" },
  { label: 'Playfair Display', value: "'Playfair Display', serif" },
  { label: 'Georgia (serif)', value: 'Georgia, serif' },
  { label: 'Helvetica / Arial', value: "'Helvetica Neue', Arial, sans-serif" },
];

export default function BrandsPage() {
  const [brands, setBrands] = useState([]);
  const [editing, setEditing] = useState(null);
  const [editData, setEditData] = useState(null);
  const [saving, setSaving] = useState(false);
  const [previewHtml, setPreviewHtml] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const debounceRef = useRef(null);

  const fetchBrands = async () => {
    try { const res = await api.get('/documents/brands'); setBrands(res.data.brands || []); } catch {}
  };
  useEffect(() => { fetchBrands(); }, []);

  const openEdit = async (brandId) => {
    try {
      const res = await api.get(`/documents/brands/${brandId}`);
      setEditData(res.data); setEditing(brandId);
    } catch { toast.error('No se pudo cargar la marca'); }
  };

  const setField = (key, value) => setEditData(p => ({ ...p, [key]: value }));
  const updateToken = (section, key, value) => setEditData(prev => ({
    ...prev,
    tokens: { ...prev.tokens, [section]: { ...(prev.tokens?.[section] || {}), [key]: value } },
  }));

  // Vista previa en TIEMPO REAL: cada cambio en editData re-renderiza (debounce 350ms).
  const renderPreview = useCallback(async (data) => {
    if (!data) return;
    setPreviewLoading(true);
    try {
      const res = await api.post('/docstudio/brands/preview-live', { brand: data }, { responseType: 'text' });
      setPreviewHtml(res.data);
    } catch { /* silencioso: no romper la edición */ }
    finally { setPreviewLoading(false); }
  }, []);

  useEffect(() => {
    if (!editData) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => renderPreview(editData), 350);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
  }, [editData, renderPreview]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put(`/documents/brands/${editing}`, editData);
      toast.success('Marca guardada'); fetchBrands();
    } catch { toast.error('No se pudo guardar'); }
    finally { setSaving(false); }
  };

  const Swatch = ({ section, k, label }) => (
    <div className="flex items-center gap-2">
      <input type="color" value={editData?.tokens?.[section]?.[k] || '#000000'}
        onChange={e => updateToken(section, k, e.target.value)}
        className="w-8 h-8 rounded border border-zinc-700 bg-transparent cursor-pointer shrink-0" />
      <div className="min-w-0">
        <p className="text-[11px] text-zinc-300 truncate">{label}</p>
        <p className="text-[9px] font-mono text-zinc-500">{editData?.tokens?.[section]?.[k]}</p>
      </div>
    </div>
  );

  if (!editing) {
    return (
      <div className="space-y-6" data-testid="brands-page">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">Marcas</h1>
          <p className="text-sm text-zinc-400 mt-1">Personaliza logo, colores y tipografía. Vista previa en tiempo real.</p>
        </div>
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
                  {b.is_default && <Badge className="ml-auto bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px]">Default</Badge>}
                </div>
                <div className="flex gap-1">
                  {['bg_primary', 'accent', 'text_primary', 'table_header_bg'].map(tok => (
                    <div key={tok} className="w-6 h-6 rounded border border-zinc-700"
                      style={{ background: b.tokens?.colors?.[tok] || '#333' }} title={tok} />
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="brand-editor">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => { setEditing(null); setEditData(null); setPreviewHtml(''); }}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">← Marcas</Button>
          <h2 className="text-lg font-bold text-zinc-100 font-heading">{editData?.name}</h2>
          <Badge variant="outline" className="text-[10px] text-zinc-400 border-zinc-600">{editing}</Badge>
          {previewLoading && <Loader2 className="w-3.5 h-3.5 animate-spin text-zinc-500" />}
        </div>
        <Button size="sm" onClick={handleSave} disabled={saving} className="bg-blue-600 hover:bg-blue-500 text-white" data-testid="brand-save-btn">
          {saving ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Save className="w-3.5 h-3.5 mr-1.5" />} Guardar
        </Button>
      </div>

      {/* Dos paneles: controles (izq) + vista previa en vivo (dcha) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* CONTROLES */}
        <div className="space-y-4 max-h-[calc(100vh-160px)] overflow-y-auto pr-1">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2 pt-4 px-5"><CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500">Identidad y logo</CardTitle></CardHeader>
            <CardContent className="px-5 pb-4 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1"><Label className="text-zinc-400 text-xs">Nombre</Label>
                  <Input value={editData?.name || ''} onChange={e => setField('name', e.target.value)} className="bg-zinc-950 border-zinc-700 text-zinc-50" /></div>
                <div className="space-y-1"><Label className="text-zinc-400 text-xs">Logo (texto)</Label>
                  <Input value={editData?.logo_text || ''} onChange={e => setField('logo_text', e.target.value)} className="bg-zinc-950 border-zinc-700 text-zinc-50" /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1"><Label className="text-zinc-400 text-xs">Logo claro (URL, fondos oscuros)</Label>
                  <Input value={editData?.logo_light || ''} onChange={e => setField('logo_light', e.target.value)} placeholder="https://…" className="bg-zinc-950 border-zinc-700 text-zinc-50" /></div>
                <div className="space-y-1"><Label className="text-zinc-400 text-xs">Logo oscuro (URL, fondos claros)</Label>
                  <Input value={editData?.logo_dark || ''} onChange={e => setField('logo_dark', e.target.value)} placeholder="https://…" className="bg-zinc-950 border-zinc-700 text-zinc-50" /></div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2 pt-4 px-5"><CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 flex items-center gap-2"><Type className="w-3 h-3" /> Tipografía</CardTitle></CardHeader>
            <CardContent className="px-5 pb-4 grid grid-cols-2 gap-3">
              {[['heading', 'Títulos'], ['body', 'Cuerpo']].map(([k, label]) => (
                <div key={k} className="space-y-1">
                  <Label className="text-zinc-400 text-xs">{label}</Label>
                  <select value={editData?.tokens?.fonts?.[k] || ''} onChange={e => updateToken('fonts', k, e.target.value)}
                    className="w-full h-9 rounded-md bg-zinc-950 border border-zinc-700 text-zinc-50 text-sm px-2">
                    {FONT_OPTIONS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
                    {editData?.tokens?.fonts?.[k] && !FONT_OPTIONS.some(f => f.value === editData.tokens.fonts[k]) &&
                      <option value={editData.tokens.fonts[k]}>Actual</option>}
                  </select>
                </div>
              ))}
            </CardContent>
          </Card>

          {COLOR_GROUPS.map(group => (
            <Card key={group.title} className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5"><CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 flex items-center gap-2"><Palette className="w-3 h-3" /> {group.title}</CardTitle></CardHeader>
              <CardContent className="px-5 pb-4 grid grid-cols-2 gap-3">
                {group.keys.map(([k, label]) => <Swatch key={k} section="colors" k={k} label={label} />)}
              </CardContent>
            </Card>
          ))}

          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2 pt-4 px-5"><CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500">Portada y separadores</CardTitle></CardHeader>
            <CardContent className="px-5 pb-4 grid grid-cols-2 gap-3">
              {COVER_TOKENS.map(([k, label]) => <Swatch key={k} section="cover" k={k} label={label} />)}
            </CardContent>
          </Card>
        </div>

        {/* VISTA PREVIA EN VIVO */}
        <div className="lg:sticky lg:top-4 self-start">
          <div className="rounded-lg border border-zinc-700 bg-zinc-950 overflow-hidden" style={{ height: 'calc(100vh - 160px)' }}>
            {previewHtml
              ? <iframe srcDoc={previewHtml} title="Vista previa de marca" className="w-full h-full" style={{ border: 'none', background: '#fff' }} />
              : <div className="flex items-center justify-center h-full text-zinc-600 text-sm"><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Generando vista previa…</div>}
          </div>
          <p className="text-[11px] text-zinc-500 mt-2">Vista previa en tiempo real. Los cambios se reflejan al instante; pulsa <b>Guardar</b> para aplicarlos a los documentos.</p>
        </div>
      </div>
    </div>
  );
}
