import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Trash2, Save, Download, ArrowLeft, Plus,
  Loader2, Check, Pencil, X, ChevronUp, ChevronDown, Zap, Palette,
  Maximize2, Minimize2, Eye, PencilRuler,
} from 'lucide-react';
import api from '@/lib/api';
import { toast } from 'sonner';

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-ES', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}); } catch { return '—'; }
}

const genId = () => 'b_' + Math.random().toString(36).slice(2, 14);

function defaultData(bt) {
  switch (bt) {
    case 'text': return { content: 'Nuevo texto…', style: 'body' };
    case 'kpi': return { title: 'Métrica', value: '0', unit: '' };
    case 'insight': return { title: 'Idea', summary: '', importance: 'medium' };
    case 'table': return { title: 'Tabla', columns: ['Columna 1', 'Columna 2'], rows: [['', '']] };
    default: return {};
  }
}

// Módulos que el usuario puede añadir a una sección
const ADDABLE = [
  { id: 'text', label: 'Texto' },
  { id: 'kpi', label: 'KPI' },
  { id: 'insight', label: 'Idea' },
  { id: 'table', label: 'Tabla' },
  { id: 'divider', label: 'Separador' },
  { id: 'page_break', label: 'Salto de página' },
];

function BlockEditor({ block, onChange, onDelete, onMoveUp, onMoveDown, isFirst, isLast }) {
  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState(null);
  const bt = block.block_type;
  const data = block.data || {};

  const startEdit = () => { setEditData(JSON.parse(JSON.stringify(data))); setEditing(true); };
  const saveEdit = () => {
    onChange({ ...block, data: editData, data_lineage: { ...block.data_lineage, source: 'manual_edit', date: new Date().toISOString() } });
    setEditing(false);
  };
  const cancelEdit = () => { setEditing(false); setEditData(null); };

  return (
    <div className="group relative border border-transparent hover:border-zinc-700/50 rounded-lg transition-colors" data-testid={`block-${block.block_id}`}>
      <div className="absolute -left-10 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col gap-0.5">
        {!isFirst && <button onClick={onMoveUp} className="p-0.5 text-zinc-600 hover:text-zinc-300"><ChevronUp className="w-3 h-3" /></button>}
        {!isLast && <button onClick={onMoveDown} className="p-0.5 text-zinc-600 hover:text-zinc-300"><ChevronDown className="w-3 h-3" /></button>}
      </div>
      <div className="absolute -right-8 top-1 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col gap-0.5">
        {!editing && bt !== 'page_break' && bt !== 'divider' && <button onClick={startEdit} className="p-0.5 text-zinc-600 hover:text-zinc-300"><Pencil className="w-3 h-3" /></button>}
        <button onClick={onDelete} className="p-0.5 text-zinc-600 hover:text-rose-400" data-testid={`delete-${block.block_id}`}><Trash2 className="w-3 h-3" /></button>
      </div>

      {bt === 'cover' && !editing && (
        <div className="bg-zinc-800 rounded-lg p-6 cursor-pointer" onClick={startEdit}>
          <h2 className="text-xl font-bold text-zinc-100">{data.title}</h2>
          <p className="text-sm text-zinc-400 mt-1">{data.subtitle}</p>
        </div>
      )}
      {bt === 'cover' && editing && (
        <div className="bg-zinc-800 rounded-lg p-4 space-y-2">
          <Input value={editData.title || ''} onChange={e => setEditData({...editData, title: e.target.value})} className="text-lg font-bold bg-zinc-900 border-zinc-700" placeholder="Titulo" />
          <Input value={editData.subtitle || ''} onChange={e => setEditData({...editData, subtitle: e.target.value})} className="text-sm bg-zinc-900 border-zinc-700" placeholder="Subtitulo" />
          <div className="flex gap-1"><Button size="sm" onClick={saveEdit} className="h-6 text-[10px] bg-emerald-600"><Check className="w-2.5 h-2.5 mr-1" />Guardar</Button><Button size="sm" variant="ghost" onClick={cancelEdit} className="h-6 text-[10px]"><X className="w-2.5 h-2.5" /></Button></div>
        </div>
      )}

      {bt === 'text' && !editing && (
        <div className={`text-sm text-zinc-300 cursor-pointer rounded px-2 py-1 hover:bg-zinc-800/30 ${data.style === 'executive_summary' ? 'bg-blue-500/5 border-l-2 border-blue-500 pl-4 py-2' : data.style === 'conclusion' ? 'italic' : ''}`} onClick={startEdit}>
          {data.content || 'Click para editar...'}
        </div>
      )}
      {bt === 'text' && editing && (
        <div className="space-y-2 p-1">
          <Textarea value={editData.content || ''} onChange={e => setEditData({...editData, content: e.target.value})} className="min-h-[100px] text-sm bg-zinc-900 border-zinc-700 text-zinc-200" />
          <div className="flex gap-1"><Button size="sm" onClick={saveEdit} className="h-6 text-[10px] bg-emerald-600"><Check className="w-2.5 h-2.5 mr-1" />Guardar</Button><Button size="sm" variant="ghost" onClick={cancelEdit} className="h-6 text-[10px]"><X className="w-2.5 h-2.5" /></Button></div>
        </div>
      )}

      {bt === 'kpi' && !editing && (
        <div className="inline-block bg-zinc-800/50 rounded-lg px-4 py-2 mr-2 mb-2 cursor-pointer" onClick={startEdit}>
          <p className="text-[9px] uppercase tracking-wider text-zinc-500">{data.title}</p>
          <p className="text-lg font-bold text-zinc-100">{data.value} <span className="text-xs text-zinc-500">{data.unit}</span></p>
          {data.variation && <p className="text-[10px] text-emerald-400">{data.variation}</p>}
          {data.commentary && <p className="text-[10px] text-zinc-500">{data.commentary}</p>}
        </div>
      )}
      {bt === 'kpi' && editing && (
        <div className="bg-zinc-800/50 rounded-lg p-3 space-y-1.5">
          <Input value={editData.title || ''} onChange={e => setEditData({...editData, title: e.target.value})} className="h-7 text-xs bg-zinc-900 border-zinc-700" placeholder="Titulo" />
          <div className="flex gap-2">
            <Input value={editData.value || ''} onChange={e => setEditData({...editData, value: e.target.value})} className="h-7 text-xs bg-zinc-900 border-zinc-700 flex-1" placeholder="Valor" />
            <Input value={editData.unit || ''} onChange={e => setEditData({...editData, unit: e.target.value})} className="h-7 text-xs bg-zinc-900 border-zinc-700 w-24" placeholder="Unidad" />
          </div>
          <Input value={editData.commentary || ''} onChange={e => setEditData({...editData, commentary: e.target.value})} className="h-7 text-xs bg-zinc-900 border-zinc-700" placeholder="Comentario" />
          <div className="flex gap-1"><Button size="sm" onClick={saveEdit} className="h-6 text-[10px] bg-emerald-600"><Check className="w-2.5 h-2.5 mr-1" />Guardar</Button><Button size="sm" variant="ghost" onClick={cancelEdit} className="h-6 text-[10px]"><X className="w-2.5 h-2.5" /></Button></div>
        </div>
      )}

      {bt === 'insight' && !editing && (
        <div className={`rounded-lg px-3 py-2 border cursor-pointer ${data.importance === 'high' ? 'bg-rose-500/5 border-rose-500/20' : 'bg-amber-500/5 border-amber-500/20'}`} onClick={startEdit}>
          <p className="text-xs font-semibold text-zinc-300">{data.title}</p>
          <p className="text-xs text-zinc-400">{data.summary}</p>
        </div>
      )}
      {bt === 'insight' && editing && (
        <div className="rounded-lg p-3 border border-zinc-700 space-y-1.5">
          <Input value={editData.title || ''} onChange={e => setEditData({...editData, title: e.target.value})} className="h-7 text-xs bg-zinc-900 border-zinc-700" placeholder="Titulo" />
          <Textarea value={editData.summary || ''} onChange={e => setEditData({...editData, summary: e.target.value})} className="min-h-[60px] text-xs bg-zinc-900 border-zinc-700" placeholder="Contenido" />
          <div className="flex gap-1"><Button size="sm" onClick={saveEdit} className="h-6 text-[10px] bg-emerald-600"><Check className="w-2.5 h-2.5 mr-1" />Guardar</Button><Button size="sm" variant="ghost" onClick={cancelEdit} className="h-6 text-[10px]"><X className="w-2.5 h-2.5" /></Button></div>
        </div>
      )}

      {bt === 'table' && (
        <div className="text-xs">
          {data.title && <p className="text-zinc-400 mb-1 font-medium">{data.title}</p>}
          <table className="w-full border-collapse">
            <thead><tr>{data.columns?.map((c,i) => <th key={i} className="text-left text-[10px] text-zinc-500 pb-1 pr-3">{c}</th>)}</tr></thead>
            <tbody>{data.rows?.map((r,ri) => <tr key={ri}>{r.map((cell,ci) => <td key={ci} className="text-zinc-300 py-0.5 pr-3">{cell}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}

      {bt === 'divider' && <hr className="border-zinc-800 my-2" />}

      {bt === 'page_break' && (
        <div className="my-1 flex items-center gap-2 text-blue-400/70">
          <div className="flex-1 border-t-2 border-dashed border-blue-500/40" />
          <span className="text-[9px] uppercase tracking-wider">Salto de página</span>
          <div className="flex-1 border-t-2 border-dashed border-blue-500/40" />
        </div>
      )}

      {block.data_lineage?.source === 'ai' && (
        <p className="text-[8px] text-zinc-600 mt-1 pl-1">IA: {block.data_lineage.model} — {block.data_lineage.task}</p>
      )}
      {block.data_lineage?.source === 'manual_edit' && (
        <p className="text-[8px] text-zinc-600 mt-1 pl-1">Editado manualmente — {fmtDate(block.data_lineage.date)}</p>
      )}
    </div>
  );
}

export default function DocumentEditor({ doc, onBack, onSaved }) {
  const [docState, setDocState] = useState(JSON.parse(JSON.stringify(doc)));
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [brandOpen, setBrandOpen] = useState(false);
  const [maximized, setMaximized] = useState(false);
  const [view, setView] = useState('edit'); // 'edit' | 'preview'
  const [previewHtml, setPreviewHtml] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [logoText, setLogoText] = useState(doc.brand_overlay?.logo_text || '');
  const [accent, setAccent] = useState(doc.brand_overlay?.tokens?.colors?.accent || '#2563eb');
  const [kpiColor, setKpiColor] = useState(doc.color_override?.kpi_value || '#2563eb');
  const [applyingBrand, setApplyingBrand] = useState(false);

  const docId = docState.document_id;

  const reload = async () => {
    const { data } = await api.get(`/docstudio/documents/${docId}`);
    setDocState(data.document);
    setDirty(false);
  };

  const updateBlock = (si, bi, newBlock) => {
    const u = { ...docState };
    u.sections[si].blocks[bi] = newBlock;
    setDocState(u); setDirty(true);
  };
  const deleteBlock = (si, bi) => {
    const u = { ...docState };
    u.sections[si].blocks.splice(bi, 1);
    setDocState({ ...u }); setDirty(true);
  };
  const moveBlock = (si, bi, dir) => {
    const u = { ...docState };
    const blocks = u.sections[si].blocks;
    const ni = bi + dir;
    if (ni < 0 || ni >= blocks.length) return;
    [blocks[bi], blocks[ni]] = [blocks[ni], blocks[bi]];
    setDocState({ ...u }); setDirty(true);
  };
  const addBlock = (si, blockType) => {
    const u = { ...docState };
    u.sections[si].blocks = [...(u.sections[si].blocks || []), {
      block_id: genId(), block_type: blockType, data: defaultData(blockType),
      data_lineage: { source: 'manual' },
    }];
    setDocState({ ...u }); setDirty(true);
  };
  const deleteSection = (si) => {
    const u = { ...docState };
    u.sections = u.sections.filter((_, i) => i !== si);
    setDocState({ ...u }); setDirty(true);
  };

  const addSection = async () => {
    try {
      if (dirty) await saveDocument();
      await api.post(`/docstudio/documents/${docId}/sections`, { title: 'Nueva sección' });
      await reload();
      toast.success('Sección añadida');
    } catch { toast.error('Error añadiendo sección'); }
  };

  const applyBranding = async () => {
    setApplyingBrand(true);
    try {
      if (dirty) await saveDocument();
      await api.put(`/docstudio/documents/${docId}/brand-overlay`, {
        overlay: { logo_text: logoText || null, tokens: { colors: { accent } } },
      });
      await api.put(`/docstudio/documents/${docId}/color-override`, {
        colors: { kpi_value: kpiColor, accent },
      });
      await reload();
      toast.success('Personalización de marca aplicada');
      setBrandOpen(false);
    } catch { toast.error('Error aplicando marca'); }
    setApplyingBrand(false);
  };

  const saveDocument = async () => {
    setSaving(true);
    try {
      const sections = docState.sections.map(s => ({ section_id: s.section_id, title: s.title, blocks: s.blocks }));
      await api.put(`/docstudio/documents/${docId}/save`, sections);
      setDirty(false);
      toast.success(`Guardado v${docState.version + 1}`);
      onSaved?.();
      await reload();
    } catch { toast.error('Error guardando'); }
    setSaving(false);
  };

  const regenerateSection = async (si) => {
    const section = docState.sections[si];
    setRegenerating(section.section_id);
    try {
      if (dirty) await saveDocument();
      const { data } = await api.post(`/docstudio/documents/${docId}/section/${section.section_id}/regenerate`);
      toast.success(`Sección regenerada: ${data.blocks} bloques`);
      await reload();
    } catch { toast.error('Error regenerando'); }
    setRegenerating(null);
  };

  const loadPreview = async () => {
    setPreviewLoading(true);
    try {
      if (dirty) await saveDocument();
      const res = await api.get(`/docstudio/documents/${docId}/preview`, { responseType: 'text' });
      setPreviewHtml(typeof res.data === 'string' ? res.data : '');
    } catch { toast.error('Error cargando la vista previa'); }
    setPreviewLoading(false);
  };

  const showPreview = async () => { setView('preview'); await loadPreview(); };

  const doExport = async (fmt) => {
    try {
      if (dirty) await saveDocument();
      const response = await api.get(`/docstudio/export/${docId}/${fmt}`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = window.document.createElement('a');
      a.href = url;
      a.download = `${docState.title?.replace(/\s+/g, '_')?.substring(0, 40) || 'document'}.${fmt}`;
      a.click();
      toast.success(`${fmt.toUpperCase()} descargado`);
    } catch { toast.error('Error exportando'); }
  };

  return (
    <div className={maximized
        ? "fixed inset-0 z-50 bg-zinc-950 overflow-auto p-6 space-y-4"
        : "space-y-4"} data-testid="document-editor">
      {/* Header */}
      <div className="flex items-center justify-between sticky top-0 z-10 bg-zinc-950 py-2 -mt-2">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack} className="text-xs text-zinc-400">
            <ArrowLeft className="w-3 h-3 mr-1" /> Volver
          </Button>
          <div>
            <h1 className="text-base font-bold text-zinc-100">{docState.title}</h1>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-zinc-500">v{docState.version}</span>
              {dirty && <Badge variant="outline" className="text-[9px] text-amber-400 border-amber-500/20">Sin guardar</Badge>}
              {docState.brand_overlay?.logo_text && <Badge variant="outline" className="text-[9px] text-violet-400 border-violet-500/20">Marca: {docState.brand_overlay.logo_text}</Badge>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Toggle Editar / Vista previa */}
          <div className="flex rounded-md border border-zinc-700 overflow-hidden">
            <button onClick={() => setView('edit')} data-testid="view-edit"
              className={`px-2.5 h-7 text-xs flex items-center gap-1 ${view === 'edit' ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}`}>
              <PencilRuler className="w-3 h-3" /> Editar
            </button>
            <button onClick={showPreview} data-testid="view-preview"
              className={`px-2.5 h-7 text-xs flex items-center gap-1 ${view === 'preview' ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}`}>
              <Eye className="w-3 h-3" /> Vista previa
            </button>
          </div>
          <Button variant="outline" size="sm" onClick={() => setMaximized(m => !m)} className="border-zinc-700 text-zinc-300 h-7 text-xs" data-testid="maximize-toggle" title={maximized ? 'Restaurar' : 'Maximizar visualización'}>
            {maximized ? <Minimize2 className="w-3 h-3 mr-1.5" /> : <Maximize2 className="w-3 h-3 mr-1.5" />}
            {maximized ? 'Restaurar' : 'Maximizar'}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setBrandOpen(o => !o)} className="border-zinc-700 text-violet-300 h-7 text-xs" data-testid="brand-toggle">
            <Palette className="w-3 h-3 mr-1.5" /> Personalizar
          </Button>
          <Button variant="outline" size="sm" onClick={saveDocument} disabled={saving || !dirty} className="border-zinc-700 text-zinc-300 h-7 text-xs">
            {saving ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <Save className="w-3 h-3 mr-1.5" />} Guardar
          </Button>
          <Button variant="outline" size="sm" onClick={() => doExport('pdf')} className="border-zinc-700 text-zinc-300 h-7 text-xs">
            <Download className="w-3 h-3 mr-1.5" /> PDF
          </Button>
          <Button variant="outline" size="sm" onClick={() => doExport('pptx')} className="border-zinc-700 text-emerald-400 h-7 text-xs">
            <Download className="w-3 h-3 mr-1.5" /> PPTX
          </Button>
        </div>
      </div>

      {/* Brand/color personalization panel */}
      {brandOpen && (
        <Card className="bg-zinc-900/50 border-violet-500/20" data-testid="brand-panel">
          <CardHeader className="pb-2"><CardTitle className="text-xs text-violet-300 flex items-center gap-2"><Palette className="w-3.5 h-3.5" /> Marca del cliente (logo y colores sobre la marca de plataforma)</CardTitle></CardHeader>
          <CardContent className="flex flex-wrap items-end gap-3">
            <div className="max-w-[180px]">
              <label className="text-[10px] text-zinc-500 block mb-1">Logo (texto)</label>
              <Input value={logoText} onChange={e => setLogoText(e.target.value)} placeholder="ACME" className="h-8 text-xs bg-zinc-900 border-zinc-800" />
            </div>
            <div>
              <label className="text-[10px] text-zinc-500 block mb-1">Color de acento</label>
              <input type="color" value={accent} onChange={e => setAccent(e.target.value)} className="h-8 w-14 rounded bg-zinc-900 border border-zinc-800 cursor-pointer" />
            </div>
            <div>
              <label className="text-[10px] text-zinc-500 block mb-1">Color de KPIs</label>
              <input type="color" value={kpiColor} onChange={e => setKpiColor(e.target.value)} className="h-8 w-14 rounded bg-zinc-900 border border-zinc-800 cursor-pointer" />
            </div>
            <Button onClick={applyBranding} disabled={applyingBrand} className="h-8 text-xs bg-violet-600 hover:bg-violet-700">
              {applyingBrand ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <Check className="w-3 h-3 mr-1.5" />} Aplicar
            </Button>
            <p className="text-[10px] text-zinc-600 w-full">El logo y colores del cliente se superponen a la marca de la plataforma sin alterar el resto del diseño.</p>
          </CardContent>
        </Card>
      )}

      {/* Vista previa HTML del documento maquetado */}
      {view === 'preview' && (
        <div data-testid="doc-preview">
          {previewLoading ? (
            <div className="flex items-center justify-center py-20"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>
          ) : (
            <div className="bg-white rounded-lg overflow-hidden border border-zinc-800">
              <iframe title="Vista previa del documento" srcDoc={previewHtml}
                style={{ width: '100%', height: maximized ? 'calc(100vh - 90px)' : '70vh', border: 'none' }} />
            </div>
          )}
          <p className="text-[10px] text-zinc-600 mt-2">Vista previa con la marca aplicada. Para maquetar (añadir/mover módulos, saltos de página, colores) usa el modo <b>Editar</b>; los cambios se reflejan aquí al guardar.</p>
        </div>
      )}

      {/* Sections (modo edición) */}
      {view === 'edit' && docState.sections?.map((section, si) => {
        const hasAiBlocks = section.blocks?.some(b => b.data_lineage?.source === 'ai');
        return (
          <Card key={section.section_id} className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm text-zinc-300">{section.title}</CardTitle>
                <div className="flex items-center gap-1">
                  {hasAiBlocks && (
                    <Button variant="ghost" size="sm" onClick={() => regenerateSection(si)} disabled={regenerating === section.section_id}
                      className="h-6 px-2 text-[10px] text-violet-400 hover:text-violet-300">
                      {regenerating === section.section_id ? <Loader2 className="w-2.5 h-2.5 mr-1 animate-spin" /> : <Zap className="w-2.5 h-2.5 mr-1" />} Regenerar con IA
                    </Button>
                  )}
                  <button onClick={() => deleteSection(si)} className="p-1 text-zinc-600 hover:text-rose-400" title="Eliminar sección" data-testid={`delete-section-${si}`}><Trash2 className="w-3 h-3" /></button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 pl-12">
              {section.blocks?.map((block, bi) => (
                <BlockEditor
                  key={block.block_id || bi}
                  block={block}
                  onChange={(nb) => updateBlock(si, bi, nb)}
                  onDelete={() => deleteBlock(si, bi)}
                  onMoveUp={() => moveBlock(si, bi, -1)}
                  onMoveDown={() => moveBlock(si, bi, 1)}
                  isFirst={bi === 0}
                  isLast={bi === section.blocks.length - 1}
                />
              ))}
              {/* Add-module toolbar */}
              <div className="flex flex-wrap items-center gap-1 pt-2 border-t border-zinc-800/50">
                <span className="text-[10px] text-zinc-600 mr-1">Añadir módulo:</span>
                {ADDABLE.map(a => (
                  <Button key={a.id} variant="ghost" size="sm" onClick={() => addBlock(si, a.id)}
                    className="h-6 px-2 text-[10px] text-zinc-400 hover:text-zinc-100 border border-zinc-800" data-testid={`add-${a.id}-${si}`}>
                    <Plus className="w-2.5 h-2.5 mr-1" />{a.label}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>
        );
      })}

      {/* Add section */}
      {view === 'edit' && (
        <Button variant="outline" size="sm" onClick={addSection} className="border-dashed border-zinc-700 text-zinc-400 h-8 text-xs w-full" data-testid="add-section">
          <Plus className="w-3 h-3 mr-1.5" /> Añadir sección
        </Button>
      )}
    </div>
  );
}
