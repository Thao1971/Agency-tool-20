import { useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  GripVertical, Trash2, RefreshCw, Save, Download, ArrowLeft, Plus,
  Loader2, Check, Pencil, X, ChevronUp, ChevronDown, Zap
} from 'lucide-react';
import api from '@/lib/api';
import { toast } from 'sonner';

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-ES', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}); } catch { return '—'; }
}

function BlockEditor({ block, onChange, onDelete, onMoveUp, onMoveDown, isFirst, isLast }) {
  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState(null);
  const bt = block.block_type;
  const data = block.data || {};

  const startEdit = () => {
    setEditData(JSON.parse(JSON.stringify(data)));
    setEditing(true);
  };

  const saveEdit = () => {
    onChange({ ...block, data: editData, data_lineage: { ...block.data_lineage, source: 'manual_edit', date: new Date().toISOString() } });
    setEditing(false);
  };

  const cancelEdit = () => { setEditing(false); setEditData(null); };

  return (
    <div className="group relative border border-transparent hover:border-zinc-700/50 rounded-lg transition-colors" data-testid={`block-${block.block_id}`}>
      {/* Block toolbar */}
      <div className="absolute -left-10 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col gap-0.5">
        {!isFirst && <button onClick={onMoveUp} className="p-0.5 text-zinc-600 hover:text-zinc-300"><ChevronUp className="w-3 h-3" /></button>}
        {!isLast && <button onClick={onMoveDown} className="p-0.5 text-zinc-600 hover:text-zinc-300"><ChevronDown className="w-3 h-3" /></button>}
      </div>
      <div className="absolute -right-8 top-1 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col gap-0.5">
        {!editing && <button onClick={startEdit} className="p-0.5 text-zinc-600 hover:text-zinc-300"><Pencil className="w-3 h-3" /></button>}
        <button onClick={onDelete} className="p-0.5 text-zinc-600 hover:text-rose-400"><Trash2 className="w-3 h-3" /></button>
      </div>

      {/* Cover */}
      {bt === 'cover' && !editing && (
        <div className="bg-zinc-800 rounded-lg p-6 cursor-pointer" onClick={startEdit}>
          <h2 className="text-xl font-bold text-zinc-100">{data.title}</h2>
          <p className="text-sm text-zinc-400 mt-1">{data.subtitle}</p>
        </div>
      )}
      {bt === 'cover' && editing && (
        <div className="bg-zinc-800 rounded-lg p-4 space-y-2">
          <Input value={editData.title || ''} onChange={e => setEditData({...editData, title: e.target.value})}
            className="text-lg font-bold bg-zinc-900 border-zinc-700" placeholder="Titulo" />
          <Input value={editData.subtitle || ''} onChange={e => setEditData({...editData, subtitle: e.target.value})}
            className="text-sm bg-zinc-900 border-zinc-700" placeholder="Subtitulo" />
          <div className="flex gap-1"><Button size="sm" onClick={saveEdit} className="h-6 text-[10px] bg-emerald-600"><Check className="w-2.5 h-2.5 mr-1" />Guardar</Button><Button size="sm" variant="ghost" onClick={cancelEdit} className="h-6 text-[10px]"><X className="w-2.5 h-2.5" /></Button></div>
        </div>
      )}

      {/* Text */}
      {bt === 'text' && !editing && (
        <div className={`text-sm text-zinc-300 cursor-pointer rounded px-2 py-1 hover:bg-zinc-800/30 ${data.style === 'executive_summary' ? 'bg-blue-500/5 border-l-2 border-blue-500 pl-4 py-2' : data.style === 'conclusion' ? 'italic' : ''}`}
          onClick={startEdit}>
          {data.content || 'Click para editar...'}
        </div>
      )}
      {bt === 'text' && editing && (
        <div className="space-y-2 p-1">
          <Textarea value={editData.content || ''} onChange={e => setEditData({...editData, content: e.target.value})}
            className="min-h-[100px] text-sm bg-zinc-900 border-zinc-700 text-zinc-200" />
          <div className="flex gap-1"><Button size="sm" onClick={saveEdit} className="h-6 text-[10px] bg-emerald-600"><Check className="w-2.5 h-2.5 mr-1" />Guardar</Button><Button size="sm" variant="ghost" onClick={cancelEdit} className="h-6 text-[10px]"><X className="w-2.5 h-2.5" /></Button></div>
        </div>
      )}

      {/* KPI */}
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

      {/* Insight */}
      {bt === 'insight' && !editing && (
        <div className={`rounded-lg px-3 py-2 border cursor-pointer ${data.importance === 'high' ? 'bg-rose-500/5 border-rose-500/20' : 'bg-amber-500/5 border-amber-500/20'}`}
          onClick={startEdit}>
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

      {/* Table (view only for now) */}
      {bt === 'table' && (
        <div className="text-xs">
          {data.title && <p className="text-zinc-400 mb-1 font-medium">{data.title}</p>}
          <table className="w-full border-collapse">
            <thead><tr>{data.columns?.map((c,i) => <th key={i} className="text-left text-[10px] text-zinc-500 pb-1 pr-3">{c}</th>)}</tr></thead>
            <tbody>{data.rows?.map((r,ri) => <tr key={ri}>{r.map((cell,ci) => <td key={ci} className="text-zinc-300 py-0.5 pr-3">{cell}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}

      {/* Divider */}
      {bt === 'divider' && <hr className="border-zinc-800 my-2" />}

      {/* Lineage */}
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
  const [document, setDocument] = useState(JSON.parse(JSON.stringify(doc)));
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(null);
  const [dirty, setDirty] = useState(false);

  const updateBlock = (sectionIdx, blockIdx, newBlock) => {
    const updated = { ...document };
    updated.sections[sectionIdx].blocks[blockIdx] = newBlock;
    setDocument(updated);
    setDirty(true);
  };

  const deleteBlock = (sectionIdx, blockIdx) => {
    const updated = { ...document };
    updated.sections[sectionIdx].blocks.splice(blockIdx, 1);
    setDocument({ ...updated });
    setDirty(true);
  };

  const moveBlock = (sectionIdx, blockIdx, direction) => {
    const updated = { ...document };
    const blocks = updated.sections[sectionIdx].blocks;
    const newIdx = blockIdx + direction;
    if (newIdx < 0 || newIdx >= blocks.length) return;
    [blocks[blockIdx], blocks[newIdx]] = [blocks[newIdx], blocks[blockIdx]];
    setDocument({ ...updated });
    setDirty(true);
  };

  const saveDocument = async () => {
    setSaving(true);
    try {
      const sections = document.sections.map(s => ({
        section_id: s.section_id,
        title: s.title,
        blocks: s.blocks,
      }));
      await api.put(`/docstudio/documents/${document.document_id}/save`, sections);
      setDirty(false);
      toast.success(`Guardado v${document.version + 1}`);
      onSaved?.();
    } catch { toast.error('Error guardando'); }
    setSaving(false);
  };

  const regenerateSection = async (sectionIdx) => {
    const section = document.sections[sectionIdx];
    setRegenerating(section.section_id);
    try {
      const { data } = await api.post(`/docstudio/documents/${document.document_id}/section/${section.section_id}/regenerate`);
      toast.success(`Seccion regenerada: ${data.blocks} bloques`);
      // Reload the document
      const { data: fresh } = await api.get(`/docstudio/documents/${document.document_id}`);
      setDocument(fresh.document);
      setDirty(false);
    } catch { toast.error('Error regenerando'); }
    setRegenerating(null);
  };

  const exportPDF = async () => {
    try {
      if (dirty) await saveDocument();
      const response = await api.get(`/docstudio/export/${document.document_id}/pdf`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${document.title?.replace(/\s+/g, '_')?.substring(0, 40) || 'document'}.pdf`;
      a.click();
      toast.success('PDF descargado');
    } catch { toast.error('Error exportando'); }
  };

  const exportPPTX = async () => {
    try {
      if (dirty) await saveDocument();
      const response = await api.get(`/docstudio/export/${document.document_id}/pptx`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${document.title?.replace(/\s+/g, '_')?.substring(0, 40) || 'document'}.pptx`;
      a.click();
      toast.success('PowerPoint descargado');
    } catch { toast.error('Error exportando PPTX'); }
  };

  return (
    <div className="space-y-4" data-testid="document-editor">
      {/* Header */}
      <div className="flex items-center justify-between sticky top-0 z-10 bg-zinc-950 py-2 -mt-2">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack} className="text-xs text-zinc-400">
            <ArrowLeft className="w-3 h-3 mr-1" /> Volver
          </Button>
          <div>
            <h1 className="text-base font-bold text-zinc-100">{document.title}</h1>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-zinc-500">v{document.version}</span>
              {dirty && <Badge variant="outline" className="text-[9px] text-amber-400 border-amber-500/20">Sin guardar</Badge>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={saveDocument} disabled={saving || !dirty}
            className="border-zinc-700 text-zinc-300 h-7 text-xs">
            {saving ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <Save className="w-3 h-3 mr-1.5" />}
            Guardar
          </Button>
          <Button variant="outline" size="sm" onClick={exportPDF}
            className="border-zinc-700 text-zinc-300 h-7 text-xs">
            <Download className="w-3 h-3 mr-1.5" /> PDF
          </Button>
          <Button variant="outline" size="sm" onClick={exportPPTX}
            className="border-zinc-700 text-emerald-400 h-7 text-xs">
            <Download className="w-3 h-3 mr-1.5" /> PPTX
          </Button>
        </div>
      </div>

      {/* Sections */}
      {document.sections?.map((section, si) => {
        const hasAiBlocks = section.blocks?.some(b => b.data_lineage?.source === 'ai');
        return (
          <Card key={section.section_id} className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm text-zinc-300">{section.title}</CardTitle>
                {hasAiBlocks && (
                  <Button variant="ghost" size="sm" onClick={() => regenerateSection(si)}
                    disabled={regenerating === section.section_id}
                    className="h-6 px-2 text-[10px] text-violet-400 hover:text-violet-300">
                    {regenerating === section.section_id ? <Loader2 className="w-2.5 h-2.5 mr-1 animate-spin" /> : <Zap className="w-2.5 h-2.5 mr-1" />}
                    Regenerar con IA
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-2 pl-12">
              {section.blocks?.map((block, bi) => (
                <BlockEditor
                  key={block.block_id || bi}
                  block={block}
                  onChange={(newBlock) => updateBlock(si, bi, newBlock)}
                  onDelete={() => deleteBlock(si, bi)}
                  onMoveUp={() => moveBlock(si, bi, -1)}
                  onMoveDown={() => moveBlock(si, bi, 1)}
                  isFirst={bi === 0}
                  isLast={bi === section.blocks.length - 1}
                />
              ))}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
