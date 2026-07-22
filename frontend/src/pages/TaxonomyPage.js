import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle
} from '@/components/ui/dialog';
import {
  Plus, ChevronDown, ChevronRight, Edit2, Layers, Trash2,
  RotateCcw, Tag, Shield, AlertTriangle
} from 'lucide-react';
import { toast } from 'sonner';

const taxonomyAPI = { get: () => api.get('/taxonomy?include_inactive=true') };

export default function TaxonomyPage() {
  const [taxonomy, setTaxonomy] = useState([]);
  const [status, setStatus] = useState(null);
  const [aliases, setAliases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedCats, setExpandedCats] = useState({});
  const [showAddCat, setShowAddCat] = useState(false);
  const [showAddSub, setShowAddSub] = useState(false);
  const [showAddAlias, setShowAddAlias] = useState(false);
  const [editingCat, setEditingCat] = useState(null);
  const [editingSub, setEditingSub] = useState(null);
  const [selectedCatId, setSelectedCatId] = useState(null);
  const [form, setForm] = useState({ name: '', description: '', definition: '', order: 0 });
  const [aliasForm, setAliasForm] = useState({ alias: '', target_type: 'category', target_id: '' });

  const fetchAll = useCallback(async () => {
    try {
      const [taxRes, statusRes, aliasRes] = await Promise.all([
        taxonomyAPI.get(),
        api.get('/taxonomy/status'),
        api.get('/taxonomy/aliases?include_inactive=true'),
      ]);
      setTaxonomy(taxRes.data.categories || []);
      setStatus(statusRes.data);
      setAliases(aliasRes.data.aliases || []);
    } catch (_) { toast.error('Error cargando taxonomia'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const toggleExpand = (id) => setExpandedCats(p => ({ ...p, [id]: !p[id] }));

  // ── Category actions ──
  const handleCreateCat = async () => {
    if (!form.name.trim()) { toast.error('Nombre obligatorio'); return; }
    try {
      await api.post('/taxonomy/categories', { name: form.name, description: form.description || null, order: taxonomy.length + 1 });
      toast.success('Categoria creada');
      setShowAddCat(false); setForm({ name: '', description: '', definition: '', order: 0 });
      fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || 'Error'); }
  };

  const handleUpdateCat = async () => {
    if (!editingCat) return;
    try {
      const update = {};
      if (form.name && form.name !== editingCat.name) update.name = form.name;
      if (form.description !== undefined) update.description = form.description;
      if (Object.keys(update).length === 0) { setEditingCat(null); return; }
      await api.put(`/taxonomy/categories/${editingCat.id}`, update);
      toast.success('Categoria actualizada');
      setEditingCat(null); fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || 'Error'); }
  };

  const handleDeactivateCat = async (catId) => {
    try {
      await api.delete(`/taxonomy/categories/${catId}`);
      toast.success('Categoria desactivada');
      fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || 'Error'); }
  };

  const handleReactivateCat = async (catId) => {
    try {
      await api.put(`/taxonomy/categories/${catId}`, { active: true });
      toast.success('Categoria reactivada');
      fetchAll();
    } catch (err) { toast.error('Error'); }
  };

  // ── Subcategory actions ──
  const handleCreateSub = async () => {
    if (!form.name.trim() || !selectedCatId) { toast.error('Nombre y categoria obligatorios'); return; }
    try {
      const subs = taxonomy.find(c => c.id === selectedCatId)?.subcategories || [];
      await api.post('/taxonomy/subcategories', { category_id: selectedCatId, name: form.name, definition: form.definition || null, order: subs.length + 1 });
      toast.success('Subcategoria creada');
      setShowAddSub(false); setForm({ name: '', description: '', definition: '', order: 0 });
      fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || 'Error'); }
  };

  const handleUpdateSub = async () => {
    if (!editingSub) return;
    try {
      const update = {};
      if (form.name && form.name !== editingSub.name) update.name = form.name;
      if (form.definition !== undefined) update.definition = form.definition;
      if (Object.keys(update).length === 0) { setEditingSub(null); return; }
      await api.put(`/taxonomy/subcategories/${editingSub.id}`, update);
      toast.success('Subcategoria actualizada');
      setEditingSub(null); fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || 'Error'); }
  };

  const handleDeactivateSub = async (subId) => {
    try {
      const r = await api.delete(`/taxonomy/subcategories/${subId}`);
      const msg = r.data.in_use_by_companies || r.data.in_use_by_transactions
        ? `Desactivada (en uso por ${r.data.in_use_by_companies} empresas, ${r.data.in_use_by_transactions} transacciones)`
        : 'Subcategoria desactivada';
      toast.success(msg);
      fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || 'Error'); }
  };

  const handleReactivateSub = async (subId) => {
    try {
      await api.put(`/taxonomy/subcategories/${subId}`, { active: true });
      toast.success('Subcategoria reactivada');
      fetchAll();
    } catch (err) { toast.error('Error'); }
  };

  // ── Alias actions ──
  const handleCreateAlias = async () => {
    if (!aliasForm.alias.trim() || !aliasForm.target_id) { toast.error('Alias y target obligatorios'); return; }
    try {
      await api.post('/taxonomy/aliases', aliasForm);
      toast.success('Alias creado');
      setShowAddAlias(false); setAliasForm({ alias: '', target_type: 'category', target_id: '' });
      fetchAll();
    } catch (err) { toast.error(err.response?.data?.detail || 'Error'); }
  };

  const handleDeactivateAlias = async (aliasId) => {
    try {
      await api.delete(`/taxonomy/aliases/${aliasId}`);
      toast.success('Alias desactivado');
      fetchAll();
    } catch (err) { toast.error('Error'); }
  };

  if (loading) return <div className="flex justify-center py-12"><div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="space-y-4" data-testid="taxonomy-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-zinc-50 font-heading">Taxonomia CIS</h1>
          <p className="text-xs text-zinc-400">Master taxonomico — fuente de verdad para categorias y subcategorias</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => { setShowAddCat(true); setForm({ name: '', description: '', definition: '', order: 0 }); }} className="bg-blue-600 hover:bg-blue-500 text-white" data-testid="add-cat-btn">
            <Plus className="w-3 h-3 mr-1" />Categoria
          </Button>
          <Button size="sm" variant="outline" onClick={() => setShowAddAlias(true)} className="border-zinc-700 text-zinc-300" data-testid="add-alias-btn">
            <Tag className="w-3 h-3 mr-1" />Alias
          </Button>
        </div>
      </div>

      {/* Status bar */}
      {status && (
        <div className="flex items-center gap-4 text-[10px] text-zinc-400 px-3 py-2 rounded bg-zinc-900 border border-zinc-800">
          <span className="text-zinc-300 font-medium"><Shield className="w-3 h-3 inline mr-1" />{status.version}</span>
          <span>{status.categories_active} categorias</span>
          <span>{status.subcategories_active} subcategorias</span>
          <span>{status.aliases_active} aliases</span>
          {status.categories_inactive > 0 && <span className="text-amber-400">{status.categories_inactive} cats inactivas</span>}
          {status.inconsistencies?.length > 0 && <span className="text-rose-400"><AlertTriangle className="w-3 h-3 inline mr-1" />{status.inconsistencies.length} inconsistencias</span>}
        </div>
      )}

      {/* Categories list */}
      <div className="space-y-1">
        {taxonomy.map(cat => {
          const expanded = expandedCats[cat.id];
          const activeSubs = (cat.subcategories || []).filter(s => s.active);
          const inactiveSubs = (cat.subcategories || []).filter(s => !s.active);
          return (
            <Card key={cat.id} className={`border-zinc-800 ${cat.active ? 'bg-zinc-900' : 'bg-zinc-900/50 opacity-70'}`} data-testid={`cat-${cat.id}`}>
              <CardContent className="p-0">
                <div className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-zinc-800/30" onClick={() => toggleExpand(cat.id)}>
                  {expanded ? <ChevronDown className="w-3.5 h-3.5 text-zinc-500" /> : <ChevronRight className="w-3.5 h-3.5 text-zinc-500" />}
                  <span className="text-[10px] text-zinc-500 font-mono w-5">{cat.order}</span>
                  <span className="text-sm text-zinc-100 font-medium flex-1">{cat.name}</span>
                  {cat.description && <span className="text-[9px] text-zinc-500 truncate max-w-[200px]">{cat.description}</span>}
                  <Badge variant="outline" className="text-[8px] text-zinc-500 border-zinc-700">{activeSubs.length} sub{activeSubs.length !== 1 ? 's' : ''}</Badge>
                  {!cat.active && <Badge className="text-[7px] bg-rose-500/10 text-rose-400 border border-rose-500/20">Inactiva</Badge>}
                  <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                    <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-zinc-500 hover:text-zinc-200"
                      onClick={() => { setEditingCat(cat); setForm({ name: cat.name, description: cat.description || '', definition: '', order: cat.order }); }} data-testid={`edit-cat-${cat.id}`}>
                      <Edit2 className="w-3 h-3" />
                    </Button>
                    <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-zinc-500 hover:text-blue-400"
                      onClick={() => { setSelectedCatId(cat.id); setShowAddSub(true); setForm({ name: '', description: '', definition: '', order: 0 }); }}>
                      <Plus className="w-3 h-3" />
                    </Button>
                    {cat.active ? (
                      <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-zinc-500 hover:text-rose-400" onClick={() => handleDeactivateCat(cat.id)}>
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    ) : (
                      <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-zinc-500 hover:text-emerald-400" onClick={() => handleReactivateCat(cat.id)}>
                        <RotateCcw className="w-3 h-3" />
                      </Button>
                    )}
                  </div>
                </div>
                {expanded && (
                  <div className="px-6 pb-2 space-y-0.5">
                    {activeSubs.map(sub => (
                      <div key={sub.id} className="flex items-center gap-2 py-1 px-2 rounded hover:bg-zinc-800/30" data-testid={`sub-${sub.id}`}>
                        <span className="text-[9px] text-zinc-600 font-mono w-4">{sub.order}</span>
                        <span className="text-xs text-zinc-300 flex-1">{sub.name}</span>
                        {sub.definition && <span className="text-[8px] text-zinc-600 truncate max-w-[150px]">{sub.definition}</span>}
                        <Button size="sm" variant="ghost" className="h-5 w-5 p-0 text-zinc-600 hover:text-zinc-300"
                          onClick={() => { setEditingSub(sub); setForm({ name: sub.name, description: '', definition: sub.definition || '', order: sub.order }); }}>
                          <Edit2 className="w-2.5 h-2.5" />
                        </Button>
                        <Button size="sm" variant="ghost" className="h-5 w-5 p-0 text-zinc-600 hover:text-rose-400" onClick={() => handleDeactivateSub(sub.id)}>
                          <Trash2 className="w-2.5 h-2.5" />
                        </Button>
                      </div>
                    ))}
                    {inactiveSubs.length > 0 && (
                      <div className="pt-1 border-t border-zinc-800/50">
                        <p className="text-[8px] text-zinc-600 mb-0.5">Inactivas:</p>
                        {inactiveSubs.map(sub => (
                          <div key={sub.id} className="flex items-center gap-2 py-0.5 px-2 opacity-50">
                            <span className="text-xs text-zinc-500 flex-1 line-through">{sub.name}</span>
                            <Button size="sm" variant="ghost" className="h-5 w-5 p-0 text-zinc-600 hover:text-emerald-400" onClick={() => handleReactivateSub(sub.id)}>
                              <RotateCcw className="w-2.5 h-2.5" />
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Aliases section */}
      {aliases.length > 0 && (
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-1 pt-3 px-4"><CardTitle className="text-[10px] uppercase tracking-wider text-zinc-500"><Tag className="w-3 h-3 inline mr-1" />Aliases ({aliases.length})</CardTitle></CardHeader>
          <CardContent className="px-4 pb-3">
            <div className="space-y-0.5">
              {aliases.filter(a => a.active).map(a => (
                <div key={a.alias_id} className="flex items-center gap-2 text-[10px] py-0.5">
                  <span className="text-zinc-200 font-medium">{a.alias}</span>
                  <span className="text-zinc-600">→</span>
                  <span className="text-zinc-400">{a.target_type}:{a.target_id.substring(0, 8)}</span>
                  <Button size="sm" variant="ghost" className="h-4 w-4 p-0 text-zinc-600 hover:text-rose-400 ml-auto" onClick={() => handleDeactivateAlias(a.alias_id)}>
                    <Trash2 className="w-2.5 h-2.5" />
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Add Category Dialog */}
      <Dialog open={showAddCat} onOpenChange={setShowAddCat}>
        <DialogContent className="bg-zinc-900 border-zinc-700 max-w-sm">
          <DialogHeader><DialogTitle className="text-zinc-50 font-heading text-sm">Nueva categoria</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label className="text-zinc-400 text-[11px]">Nombre *</Label><Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs" data-testid="cat-name-input" /></div>
            <div><Label className="text-zinc-400 text-[11px]">Descripcion</Label><Textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} rows={2} className="bg-zinc-950 border-zinc-700 text-zinc-50 text-xs" /></div>
            <Button onClick={handleCreateCat} className="w-full bg-blue-600 text-white text-xs">Crear categoria</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Subcategory Dialog */}
      <Dialog open={showAddSub} onOpenChange={setShowAddSub}>
        <DialogContent className="bg-zinc-900 border-zinc-700 max-w-sm">
          <DialogHeader><DialogTitle className="text-zinc-50 font-heading text-sm">Nueva subcategoria</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label className="text-zinc-400 text-[11px]">Nombre *</Label><Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs" data-testid="sub-name-input" /></div>
            <div><Label className="text-zinc-400 text-[11px]">Definicion</Label><Textarea value={form.definition} onChange={e => setForm(f => ({ ...f, definition: e.target.value }))} rows={2} className="bg-zinc-950 border-zinc-700 text-zinc-50 text-xs" /></div>
            <Button onClick={handleCreateSub} className="w-full bg-blue-600 text-white text-xs">Crear subcategoria</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Category Dialog */}
      <Dialog open={!!editingCat} onOpenChange={() => setEditingCat(null)}>
        <DialogContent className="bg-zinc-900 border-zinc-700 max-w-sm">
          <DialogHeader><DialogTitle className="text-zinc-50 font-heading text-sm">Editar categoria</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-[9px] text-zinc-500 font-mono">ID: {editingCat?.id}</p>
            <div><Label className="text-zinc-400 text-[11px]">Nombre</Label><Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs" /></div>
            <div><Label className="text-zinc-400 text-[11px]">Descripcion</Label><Textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} rows={2} className="bg-zinc-950 border-zinc-700 text-zinc-50 text-xs" /></div>
            <Button onClick={handleUpdateCat} className="w-full bg-blue-600 text-white text-xs">Guardar</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Subcategory Dialog */}
      <Dialog open={!!editingSub} onOpenChange={() => setEditingSub(null)}>
        <DialogContent className="bg-zinc-900 border-zinc-700 max-w-sm">
          <DialogHeader><DialogTitle className="text-zinc-50 font-heading text-sm">Editar subcategoria</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-[9px] text-zinc-500 font-mono">ID: {editingSub?.id}</p>
            <div><Label className="text-zinc-400 text-[11px]">Nombre</Label><Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs" /></div>
            <div><Label className="text-zinc-400 text-[11px]">Definicion</Label><Textarea value={form.definition} onChange={e => setForm(f => ({ ...f, definition: e.target.value }))} rows={2} className="bg-zinc-950 border-zinc-700 text-zinc-50 text-xs" /></div>
            <Button onClick={handleUpdateSub} className="w-full bg-blue-600 text-white text-xs">Guardar</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Alias Dialog */}
      <Dialog open={showAddAlias} onOpenChange={setShowAddAlias}>
        <DialogContent className="bg-zinc-900 border-zinc-700 max-w-sm">
          <DialogHeader><DialogTitle className="text-zinc-50 font-heading text-sm">Nuevo alias</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label className="text-zinc-400 text-[11px]">Alias *</Label><Input value={aliasForm.alias} onChange={e => setAliasForm(f => ({ ...f, alias: e.target.value }))} placeholder="ej: PR, Relaciones publicas..." className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs" /></div>
            <div><Label className="text-zinc-400 text-[11px]">Categoria destino *</Label>
              <select value={aliasForm.target_id} onChange={e => setAliasForm(f => ({ ...f, target_id: e.target.value, target_type: 'category' }))}
                className="w-full bg-zinc-950 border border-zinc-700 text-zinc-200 h-8 text-xs rounded px-2">
                <option value="">Seleccionar...</option>
                {taxonomy.filter(c => c.active).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <Button onClick={handleCreateAlias} className="w-full bg-blue-600 text-white text-xs">Crear alias</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
