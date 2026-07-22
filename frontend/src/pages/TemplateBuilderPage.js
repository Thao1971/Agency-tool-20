import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Loader2, Plus, Copy, Save, ArrowLeft, ChevronUp, ChevronDown,
  Trash2, X, Settings2, Eye, FileText, Presentation, Database,
  Type, BarChart3, Table2, Lightbulb, Image, Minus, PanelRightOpen
} from 'lucide-react';
import { toast } from 'sonner';

const BLOCK_TYPES = [
  { id: 'cover', label: 'Portada', icon: FileText, color: 'bg-zinc-600' },
  { id: 'kpi', label: 'KPIs', icon: BarChart3, color: 'bg-blue-600' },
  { id: 'text', label: 'Texto', icon: Type, color: 'bg-emerald-600' },
  { id: 'table', label: 'Tabla', icon: Table2, color: 'bg-violet-600' },
  { id: 'insight', label: 'Insight', icon: Lightbulb, color: 'bg-amber-600' },
  { id: 'chart', label: 'Grafico', icon: BarChart3, color: 'bg-cyan-600' },
  { id: 'image', label: 'Imagen', icon: Image, color: 'bg-rose-600' },
  { id: 'divider', label: 'Separador', icon: Minus, color: 'bg-zinc-700' },
];
const CATEGORIES = ['intelligence', 'mna', 'legal', 'company', 'custom'];
const DATA_SOURCES = [
  { id: '', label: 'Automatico' },
  { id: 'financial_engine', label: 'Financial Engine' },
  { id: 'companies_master', label: 'Datos empresa' },
  { id: 'economic_intelligence', label: 'Economic Intelligence' },
  { id: 'sector_intelligence', label: 'Sector Intelligence' },
  { id: 'ai', label: 'IA (narrativa)' },
  { id: 'manual', label: 'Manual' },
];

const SAMPLE = {
  company: 'Empresa Ejemplo SL', revenue: '1.250.000', ebitda_margin: '14.2%',
  employees: '42', cagr: '+8.3%', yoy: '+5.1%', rev_per_emp: '29.762',
  sector: 'Tecnologia y Software',
};

// ══════════════════════════════════════════
// VISUAL BLOCK — Click to select, inline edit
// ══════════════════════════════════════════

function VisualBlock({ blockType, isSelected, onClick, brand }) {
  const primary = brand?.primary_color || '#1a56db';
  const accent = brand?.accent_color || '#3b82f6';
  const ring = isSelected ? 'ring-2 ring-blue-500' : 'hover:ring-1 hover:ring-zinc-500';

  if (blockType === 'cover') {
    return (
      <div className={`rounded-lg p-5 cursor-pointer transition-all ${ring}`} onClick={onClick}
        style={{ background: brand?.secondary_color || '#0e1629', minHeight: 80 }}>
        <p className="text-base font-bold text-white">{SAMPLE.company}</p>
        <p className="text-[10px] mt-1" style={{ color: accent }}>Titulo del documento</p>
        <div className="mt-3 pt-2 border-t" style={{ borderColor: accent + '40' }}>
          <p className="text-[8px] text-gray-500">{brand?.footer_text || brand?.name || 'Brand'}</p>
        </div>
      </div>
    );
  }
  if (blockType === 'kpi') {
    return (
      <div className={`grid grid-cols-3 gap-2 cursor-pointer rounded-lg p-2 transition-all ${ring}`} onClick={onClick}>
        {[{l:'Facturacion',v:SAMPLE.revenue,u:'EUR'},{l:'Margen EBITDA',v:SAMPLE.ebitda_margin},{l:'Empleados',v:SAMPLE.employees}].map((k,i) => (
          <div key={i} className="bg-gray-50 border border-gray-100 rounded p-2">
            <p className="text-[7px] uppercase text-gray-400 tracking-wider">{k.l}</p>
            <p className="text-sm font-bold" style={{ color: primary }}>{k.v}</p>
            {k.u && <p className="text-[7px] text-gray-400">{k.u}</p>}
          </div>
        ))}
      </div>
    );
  }
  if (blockType === 'text') {
    return (
      <div className={`rounded-lg cursor-pointer transition-all ${ring}`} onClick={onClick}>
        <div className="bg-blue-50 border-l-3 pl-3 py-2 rounded-r" style={{ borderLeftColor: accent, borderLeftWidth: 3 }}>
          <p className="text-[9px] text-gray-600">Narrativa profesional generada por IA basada en datos reales de la empresa y del sector (Fact-Lock activado).</p>
        </div>
      </div>
    );
  }
  if (blockType === 'table') {
    return (
      <div className={`rounded-lg cursor-pointer transition-all overflow-hidden ${ring}`} onClick={onClick}>
        <table className="w-full text-[8px] border-collapse">
          <thead><tr>{['Metrica','Q1','Mediana','Q3'].map((h,i) => <th key={i} className="text-left py-1 px-2 text-white" style={{background:primary}}>{h}</th>)}</tr></thead>
          <tbody>
            <tr className="border-b border-gray-100"><td className="py-1 px-2 text-gray-600">Revenue</td><td className="py-1 px-2">500K</td><td className="py-1 px-2 font-medium">1.2M</td><td className="py-1 px-2">2.5M</td></tr>
            <tr><td className="py-1 px-2 text-gray-600">EBITDA</td><td className="py-1 px-2">50K</td><td className="py-1 px-2 font-medium">150K</td><td className="py-1 px-2">350K</td></tr>
          </tbody>
        </table>
      </div>
    );
  }
  if (blockType === 'insight') {
    return (
      <div className={`bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 cursor-pointer transition-all ${ring}`} onClick={onClick}>
        <p className="text-[8px] font-semibold text-amber-800">Hallazgo clave</p>
        <p className="text-[8px] text-amber-700">Insight generado por IA basado en Financial Engine...</p>
      </div>
    );
  }
  if (blockType === 'chart') {
    return (
      <div className={`bg-gray-50 border border-dashed border-gray-200 rounded-lg h-20 flex items-center justify-center cursor-pointer transition-all ${ring}`} onClick={onClick}>
        <BarChart3 className="w-4 h-4 text-gray-300 mr-2" /><p className="text-[9px] text-gray-400">Grafico sectorial</p>
      </div>
    );
  }
  if (blockType === 'divider') {
    return <div className={`border-t border-gray-200 my-2 cursor-pointer ${ring}`} onClick={onClick} />;
  }
  return (
    <div className={`bg-gray-50 border border-dashed border-gray-200 rounded-lg h-10 flex items-center justify-center cursor-pointer ${ring}`} onClick={onClick}>
      <p className="text-[8px] text-gray-400">{blockType}</p>
    </div>
  );
}

// ══════════════════════════════════════════
// VISUAL SECTION — The document section on canvas
// ══════════════════════════════════════════

function VisualSection({ section, sectionIdx, selectedBlock, onSelectBlock, onAddBlock, brand }) {
  const isCover = section.block_types?.includes('cover');
  const primary = brand?.primary_color || '#1a56db';
  const accent = brand?.accent_color || '#3b82f6';

  return (
    <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
      {!isCover && (
        <div className="pb-1 mb-2 mx-4 mt-4 border-b-2" style={{ borderColor: accent }}>
          <p className="text-xs font-bold" style={{ color: primary }}>{section.title}</p>
        </div>
      )}
      <div className={`${isCover ? '' : 'px-4 pb-3'} space-y-2`}>
        {(section.block_types || []).map((bt, bi) => (
          <VisualBlock
            key={bi}
            blockType={bt}
            isSelected={selectedBlock?.sectionIdx === sectionIdx && selectedBlock?.blockIdx === bi}
            onClick={() => onSelectBlock({ sectionIdx, blockIdx: bi, blockType: bt, section })}
            brand={brand}
          />
        ))}
      </div>
      {/* Add block button between sections */}
      <div className="flex justify-center py-1.5 opacity-0 hover:opacity-100 transition-opacity">
        <div className="flex items-center gap-0.5">
          {BLOCK_TYPES.slice(0, 6).map(bt => (
            <button key={bt.id} onClick={() => onAddBlock(sectionIdx, bt.id)}
              className={`w-5 h-5 rounded ${bt.color} flex items-center justify-center hover:scale-110 transition-transform`}
              title={bt.label}>
              <bt.icon className="w-2.5 h-2.5 text-white" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// PROPERTIES PANEL (right sidebar)
// ══════════════════════════════════════════

function PropertiesPanel({ selection, section, onUpdate, onDelete, onClose }) {
  if (!selection) {
    return (
      <div className="p-3 text-center text-xs text-zinc-600">
        <PanelRightOpen className="w-5 h-5 mx-auto mb-2 text-zinc-700" />
        Selecciona un bloque del documento para ver sus propiedades
      </div>
    );
  }

  const blockType = BLOCK_TYPES.find(b => b.id === selection.blockType);

  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {blockType && <div className={`w-4 h-4 rounded ${blockType.color} flex items-center justify-center`}><blockType.icon className="w-2.5 h-2.5 text-white" /></div>}
          <span className="text-xs font-semibold text-zinc-200">{blockType?.label || selection.blockType}</span>
        </div>
        <button onClick={onClose} className="text-zinc-600 hover:text-zinc-400"><X className="w-3 h-3" /></button>
      </div>

      <div className="text-[10px] text-zinc-500">
        Seccion: <span className="text-zinc-300">{section?.title}</span>
      </div>

      {/* Data source */}
      <div>
        <label className="text-[9px] text-zinc-500 block mb-1">Fuente de datos</label>
        <select value={section?.data_source || ''} onChange={e => onUpdate('data_source', e.target.value)}
          className="w-full h-7 text-xs bg-zinc-900 border border-zinc-800 rounded text-zinc-300 px-2">
          {DATA_SOURCES.map(ds => <option key={ds.id} value={ds.id}>{ds.label}</option>)}
        </select>
      </div>

      {/* Section title */}
      <div>
        <label className="text-[9px] text-zinc-500 block mb-1">Titulo de seccion</label>
        <Input value={section?.title || ''} onChange={e => onUpdate('title', e.target.value)}
          className="h-7 text-xs bg-zinc-900 border-zinc-800" />
      </div>

      {/* Block actions */}
      <div className="pt-2 border-t border-zinc-800 space-y-1.5">
        <Button variant="outline" size="sm" onClick={() => onDelete()} className="w-full h-6 text-[10px] border-zinc-700 text-rose-400 hover:text-rose-300">
          <Trash2 className="w-2.5 h-2.5 mr-1" /> Eliminar bloque
        </Button>
      </div>

      {/* Block type info */}
      <div className="pt-2 border-t border-zinc-800">
        <p className="text-[9px] text-zinc-600 mb-1">Bloques en esta seccion:</p>
        <div className="flex flex-wrap gap-1">
          {(section?.block_types || []).map((bt, i) => {
            const info = BLOCK_TYPES.find(b => b.id === bt);
            return (
              <Badge key={i} variant="outline" className={`text-[8px] px-1 py-0 ${i === selection.blockIdx ? 'text-blue-400 border-blue-500/30' : 'text-zinc-500 border-zinc-700'}`}>
                {info?.label || bt}
              </Badge>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// MAIN PAGE
// ══════════════════════════════════════════

export default function TemplateBuilderPage() {
  const [templates, setTemplates] = useState([]);
  const [brands, setBrands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newCategory, setNewCategory] = useState('intelligence');
  const [saving, setSaving] = useState(false);
  const [previewMode, setPreviewMode] = useState('pdf');
  const [previewBrandId, setPreviewBrandId] = useState('brand_bud');
  const [selectedBlock, setSelectedBlock] = useState(null);
  const [showProps, setShowProps] = useState(true);

  useEffect(() => { loadAll(); }, []);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [tplRes, brandRes] = await Promise.all([
        api.get('/docstudio/templates'),
        api.get('/docstudio/brands'),
      ]);
      setTemplates(tplRes.data?.templates || []);
      setBrands(brandRes.data?.brands || []);
    } catch { /* */ }
    setLoading(false);
  };

  const loadTemplate = async (id) => {
    try {
      const { data } = await api.get(`/docstudio/templates/${id}`);
      setSelected(JSON.parse(JSON.stringify(data.template)));
      setSelectedBlock(null);
    } catch { toast.error('Error'); }
  };

  const createTemplate = async () => {
    if (!newName) return;
    try {
      const { data } = await api.post('/docstudio/templates', {
        name: newName, description: '', category: newCategory,
        sections: [{ title: 'Portada', order: 1, block_types: ['cover'] }],
      });
      toast.success('Plantilla creada');
      setCreating(false); setNewName('');
      loadAll();
      loadTemplate(data.template_id);
    } catch { toast.error('Error'); }
  };

  const saveTemplate = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      await api.put(`/docstudio/templates/${selected.template_id}`, {
        name: selected.name, description: selected.description, category: selected.category,
        analysis_model: selected.analysis_model, narrative_model: selected.narrative_model,
        sections: selected.sections,
      });
      toast.success(`v${selected.version + 1} guardada`);
      setSelected({ ...selected, version: selected.version + 1 });
      loadAll();
    } catch { toast.error('Error'); }
    setSaving(false);
  };

  const addSection = () => {
    const s = [...(selected.sections || [])];
    s.push({ title: 'Nueva seccion', order: s.length + 1, block_types: ['text'], data_source: null });
    setSelected({ ...selected, sections: s });
  };

  const addBlockToSection = (sectionIdx, blockType) => {
    const s = [...selected.sections];
    s[sectionIdx].block_types = [...(s[sectionIdx].block_types || []), blockType];
    setSelected({ ...selected, sections: s });
  };

  const deleteBlock = () => {
    if (!selectedBlock) return;
    const s = [...selected.sections];
    const section = s[selectedBlock.sectionIdx];
    section.block_types = section.block_types.filter((_, i) => i !== selectedBlock.blockIdx);
    if (section.block_types.length === 0) {
      s.splice(selectedBlock.sectionIdx, 1);
      s.forEach((x, i) => { x.order = i + 1; });
    }
    setSelected({ ...selected, sections: s });
    setSelectedBlock(null);
  };

  const updateSectionProp = (prop, value) => {
    if (!selectedBlock) return;
    const s = [...selected.sections];
    s[selectedBlock.sectionIdx][prop] = value;
    setSelected({ ...selected, sections: s });
  };

  const moveSection = (idx, dir) => {
    const s = [...selected.sections];
    const ni = idx + dir;
    if (ni < 0 || ni >= s.length) return;
    [s[idx], s[ni]] = [s[ni], s[idx]];
    s.forEach((x, i) => { x.order = i + 1; });
    setSelected({ ...selected, sections: s });
  };

  const deleteSection = (idx) => {
    const s = selected.sections.filter((_, i) => i !== idx);
    s.forEach((x, i) => { x.order = i + 1; });
    setSelected({ ...selected, sections: s });
    setSelectedBlock(null);
  };

  const currentBrand = brands.find(b => b.brand_id === previewBrandId) || brands[0] || {};

  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>;

  // ═══ VISUAL DOCUMENT DESIGNER ═══
  if (selected) {
    return (
      <div className="h-[calc(100vh-96px)] flex" data-testid="template-designer">
        {/* DOCUMENT CANVAS (main area) */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Toolbar */}
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-zinc-800 bg-zinc-900/50 flex-shrink-0">
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => { setSelected(null); loadAll(); }} className="h-6 px-1.5 text-zinc-500">
                <ArrowLeft className="w-3 h-3" />
              </Button>
              <Input value={selected.name} onChange={e => setSelected({ ...selected, name: e.target.value })}
                className="text-sm font-bold bg-transparent border-none p-0 h-6 text-zinc-100 focus-visible:ring-0 w-44" />
              <Badge variant="outline" className="text-[8px] text-zinc-500">{selected.category}</Badge>
              <span className="text-[9px] text-zinc-600">v{selected.version}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <select value={previewBrandId} onChange={e => setPreviewBrandId(e.target.value)}
                className="h-5 text-[8px] bg-zinc-900 border border-zinc-800 rounded text-zinc-400 px-1">
                {brands.map(b => <option key={b.brand_id} value={b.brand_id}>{b.name}</option>)}
              </select>
              <Button variant={previewMode === 'pdf' ? 'secondary' : 'ghost'} size="sm" onClick={() => setPreviewMode('pdf')} className="h-5 px-1.5 text-[9px]">
                <FileText className="w-2.5 h-2.5 mr-0.5" /> PDF
              </Button>
              <Button variant={previewMode === 'pptx' ? 'secondary' : 'ghost'} size="sm" onClick={() => setPreviewMode('pptx')} className="h-5 px-1.5 text-[9px]">
                <Presentation className="w-2.5 h-2.5 mr-0.5" /> PPTX
              </Button>
              <div className="w-px h-4 bg-zinc-800 mx-1" />
              <Button size="sm" onClick={saveTemplate} disabled={saving} className="h-6 text-[10px] bg-emerald-600 hover:bg-emerald-700 px-2.5">
                {saving ? <Loader2 className="w-2.5 h-2.5 mr-1 animate-spin" /> : <Save className="w-2.5 h-2.5 mr-1" />}
                Guardar
              </Button>
            </div>
          </div>

          {/* Canvas */}
          <div className="flex-1 overflow-y-auto bg-zinc-700/10 p-4">
            <div className={`mx-auto ${previewMode === 'pptx' ? 'max-w-3xl' : 'max-w-2xl'} space-y-3`}>
              {(selected.sections || []).map((section, si) => (
                <div key={si} className="relative group">
                  {/* Section controls (visible on hover) */}
                  <div className="absolute -left-8 top-2 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col gap-0.5 z-10">
                    {si > 0 && <button onClick={() => moveSection(si, -1)} className="p-0.5 rounded bg-zinc-800 text-zinc-500 hover:text-zinc-300"><ChevronUp className="w-3 h-3" /></button>}
                    {si < selected.sections.length - 1 && <button onClick={() => moveSection(si, 1)} className="p-0.5 rounded bg-zinc-800 text-zinc-500 hover:text-zinc-300"><ChevronDown className="w-3 h-3" /></button>}
                    <button onClick={() => deleteSection(si)} className="p-0.5 rounded bg-zinc-800 text-zinc-500 hover:text-rose-400"><Trash2 className="w-3 h-3" /></button>
                  </div>

                  {previewMode === 'pptx' ? (
                    <div className="bg-white rounded-lg shadow-sm border overflow-hidden" style={{ aspectRatio: '16/9' }}>
                      {section.block_types?.includes('cover') ? (
                        <div className="h-full flex flex-col justify-center px-8" style={{ background: currentBrand.secondary_color || '#0e1629' }}>
                          <p className="text-xl font-bold text-white">{SAMPLE.company}</p>
                          <p className="text-xs mt-1" style={{ color: currentBrand.accent_color }}>{selected.name}</p>
                          <p className="text-[8px] text-gray-500 mt-6">{currentBrand.name}</p>
                        </div>
                      ) : (
                        <div className="h-full p-4">
                          <div className="h-6 rounded-sm mb-3 flex items-center px-3" style={{ background: currentBrand.primary_color }}>
                            <span className="text-[10px] text-white font-semibold">{section.title}</span>
                          </div>
                          <div className="space-y-2">
                            {(section.block_types || []).map((bt, bi) => (
                              <VisualBlock key={bi} blockType={bt}
                                isSelected={selectedBlock?.sectionIdx === si && selectedBlock?.blockIdx === bi}
                                onClick={() => { setSelectedBlock({ sectionIdx: si, blockIdx: bi, blockType: bt, section }); setShowProps(true); }}
                                brand={currentBrand} />
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <VisualSection
                      section={section} sectionIdx={si}
                      selectedBlock={selectedBlock}
                      onSelectBlock={(sel) => { setSelectedBlock(sel); setShowProps(true); }}
                      onAddBlock={addBlockToSection}
                      brand={currentBrand}
                    />
                  )}
                </div>
              ))}

              {/* Add section */}
              <button onClick={addSection}
                className="w-full py-3 border-2 border-dashed border-zinc-700/50 rounded-lg text-zinc-600 hover:text-zinc-400 hover:border-zinc-600 transition-colors flex items-center justify-center gap-2 text-xs">
                <Plus className="w-3.5 h-3.5" /> Anadir seccion
              </button>
            </div>
          </div>
        </div>

        {/* PROPERTIES PANEL (right) */}
        {showProps && (
          <div className="w-56 border-l border-zinc-800 bg-zinc-950 flex-shrink-0 overflow-y-auto">
            <PropertiesPanel
              selection={selectedBlock}
              section={selectedBlock ? selected.sections[selectedBlock.sectionIdx] : null}
              onUpdate={updateSectionProp}
              onDelete={deleteBlock}
              onClose={() => setShowProps(false)}
            />
          </div>
        )}
      </div>
    );
  }

  // ═══ TEMPLATE LIST ═══
  return (
    <div className="space-y-4" data-testid="template-builder">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-zinc-100">Template Builder</h1>
          <p className="text-xs text-zinc-500 mt-0.5">Disena tus modelos documentales</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setCreating(true)} className="border-zinc-700 text-zinc-300 h-7 text-xs">
          <Plus className="w-3 h-3 mr-1.5" /> Nueva plantilla
        </Button>
      </div>

      {creating && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4 flex items-end gap-3">
            <div className="flex-1">
              <Input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Nombre de la plantilla" className="h-8 text-xs bg-zinc-900 border-zinc-800" />
            </div>
            <select value={newCategory} onChange={e => setNewCategory(e.target.value)}
              className="h-8 text-xs bg-zinc-900 border border-zinc-800 rounded text-zinc-300 px-2">
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <Button onClick={createTemplate} className="h-8 text-xs bg-blue-600"><Plus className="w-3 h-3 mr-1" /> Crear</Button>
            <Button variant="ghost" onClick={() => setCreating(false)} className="h-8 text-xs">Cancelar</Button>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        {templates.map(t => (
          <Card key={t.template_id} className="bg-zinc-900/50 border-zinc-800 cursor-pointer hover:border-zinc-700 transition-colors"
            onClick={() => loadTemplate(t.template_id)}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-zinc-200">{t.name}</h3>
                <Button variant="ghost" size="sm" onClick={(e) => {
                  e.stopPropagation();
                  api.post(`/docstudio/templates/${t.template_id}/duplicate?new_name=${encodeURIComponent(t.name + ' (copia)')}`).then(() => { toast.success('Duplicada'); loadAll(); });
                }} className="h-5 px-1 text-zinc-500"><Copy className="w-3 h-3" /></Button>
              </div>
              <p className="text-[10px] text-zinc-500 mb-2">{t.description?.substring(0, 60)}</p>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[9px] text-zinc-400 border-zinc-600">{t.category}</Badge>
                <Badge variant="outline" className="text-[9px] text-blue-400 border-blue-500/20">v{t.version}</Badge>
                <span className="text-[9px] text-zinc-600">{t.sections?.length || 0} secciones</span>
                {t.provider && t.provider !== 'custom' && (
                  <Badge variant="outline" className="text-[9px] text-emerald-400 border-emerald-500/20">{t.provider}</Badge>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
