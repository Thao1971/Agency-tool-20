import { useState, useEffect } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import {
  Loader2, FileText, Download, Plus, Palette, BarChart3, Building2, Zap,
  Star, Clock, Trash2
} from 'lucide-react';
import { toast } from 'sonner';
import DocumentEditor from '@/components/DocumentEditor';

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-ES', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}); } catch { return '—'; }
}

const STATUS_BADGE = {
  draft: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/20',
  generated: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  exported: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
};

function BrandSelect({ brands, value, onChange }) {
  return (
    <div className="flex-1 max-w-[200px]">
      <label className="text-[10px] text-zinc-500 block mb-1">Marca</label>
      <select value={value} onChange={e => onChange(e.target.value)}
        className="h-8 w-full rounded border border-zinc-800 bg-zinc-900 text-xs text-zinc-300 px-2">
        {brands.map(b => <option key={b.brand_id} value={b.brand_id}>{b.name}</option>)}
      </select>
    </div>
  );
}

export default function DocStudioPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('dashboard');
  const [templates, setTemplates] = useState([]);
  const [brands, setBrands] = useState([]);
  const [composing, setComposing] = useState(false);
  const [cnaeInput, setCnaeInput] = useState('62');
  const [cifInput, setCifInput] = useState('');
  const [selectedBrand, setSelectedBrand] = useState('brand_bud');
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [genericInput, setGenericInput] = useState('62');
  const [documents, setDocuments] = useState([]);
  const [selectedDoc, setSelectedDoc] = useState(null);

  useEffect(() => { loadDashboard(); }, []);

  const loadDashboard = async () => {
    setLoading(true);
    try {
      const [dashRes, tplRes, brandRes] = await Promise.all([
        api.get('/docstudio/dashboard'),
        api.get('/docstudio/templates'),
        api.get('/docstudio/brands'),
      ]);
      setData(dashRes.data);
      setTemplates(tplRes.data?.templates || []);
      if (tplRes.data?.templates?.length > 0 && !selectedTemplate) {
        setSelectedTemplate(tplRes.data.templates[0].template_id);
      }
      setBrands(brandRes.data?.brands || []);
    } catch { /* empty */ }
    setLoading(false);
  };

  const loadDocuments = async () => {
    try {
      const { data: res } = await api.get('/docstudio/documents?limit=50');
      setDocuments(res?.documents || []);
    } catch { /* */ }
  };

  const composeSectorReport = async () => {
    if (!cnaeInput) return;
    setComposing(true);
    try {
      const { data: res } = await api.post(`/docstudio/compose/sector-report?cnae_code=${cnaeInput}&brand_id=${selectedBrand}`);
      toast.success(`Informe generado: ${res.sections} secciones`);
      loadDashboard();
      loadDocuments();
    } catch (e) { toast.error('Error generando informe'); }
    setComposing(false);
  };

  const viewDocument = async (docId) => {
    try {
      const { data: res } = await api.get(`/docstudio/documents/${docId}`);
      setSelectedDoc(res.document);
    } catch { toast.error('Error cargando documento'); }
  };

  const exportPDF = async (docId) => {
    try {
      const response = await api.get(`/docstudio/export/${docId}/pdf`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `document_${docId}.pdf`;
      a.click();
      toast.success('PDF descargado');
    } catch { toast.error('Error exportando PDF'); }
  };

  const deleteDoc = async (docId) => {
    try {
      await api.delete(`/docstudio/documents/${docId}`);
      toast.success('Documento eliminado');
      loadDocuments();
      if (selectedDoc?.document_id === docId) setSelectedDoc(null);
    } catch { toast.error('Error eliminando'); }
  };

  const kpis = data?.kpis || {};

  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>;

  // Document Editor
  if (selectedDoc) {
    return (
      <DocumentEditor
        doc={selectedDoc}
        onBack={() => setSelectedDoc(null)}
        onSaved={() => loadDashboard()}
      />
    );
  }

  return (
    <div className="space-y-4" data-testid="docstudio-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Document Intelligence Studio</h1>
        <p className="text-xs text-zinc-500 mt-0.5">Motor documental corporativo — datos a documentos profesionales</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-5 gap-3">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <FileText className="w-4 h-4 text-zinc-400 mx-auto mb-1" />
            <p className="text-xl font-bold text-zinc-100 tabular-nums">{kpis.documents || 0}</p>
            <p className="text-[10px] text-zinc-500">Documentos</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <Star className="w-4 h-4 text-blue-400 mx-auto mb-1" />
            <p className="text-xl font-bold text-zinc-100 tabular-nums">{kpis.templates || 0}</p>
            <p className="text-[10px] text-zinc-500">Plantillas</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <Palette className="w-4 h-4 text-violet-400 mx-auto mb-1" />
            <p className="text-xl font-bold text-zinc-100 tabular-nums">{kpis.brands || 0}</p>
            <p className="text-[10px] text-zinc-500">Marcas</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <Download className="w-4 h-4 text-emerald-400 mx-auto mb-1" />
            <p className="text-xl font-bold text-zinc-100 tabular-nums">{kpis.exports || 0}</p>
            <p className="text-[10px] text-zinc-500">Exportaciones</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <Zap className="w-4 h-4 text-amber-400 mx-auto mb-1" />
            <p className="text-xl font-bold text-zinc-100 tabular-nums">{kpis.ai_calls || 0}</p>
            <p className="text-[10px] text-zinc-500">Llamadas IA</p>
          </CardContent>
        </Card>
      </div>

      <Tabs value={tab} onValueChange={(v) => { setTab(v); if (v === 'documents') loadDocuments(); }}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="dashboard" className="text-xs data-[state=active]:bg-zinc-800">Generar</TabsTrigger>
          <TabsTrigger value="documents" className="text-xs data-[state=active]:bg-zinc-800">Documentos ({kpis.documents || 0})</TabsTrigger>
          <TabsTrigger value="templates" className="text-xs data-[state=active]:bg-zinc-800">Plantillas</TabsTrigger>
          <TabsTrigger value="brands" className="text-xs data-[state=active]:bg-zinc-800">Marcas</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard" className="mt-3 space-y-4">
          {/* Generate Sector Report */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2"><CardTitle className="text-xs text-zinc-400 flex items-center gap-2"><BarChart3 className="w-3.5 h-3.5" /> Informe Sectorial</CardTitle></CardHeader>
            <CardContent className="flex items-end gap-3">
              <div className="flex-1 max-w-[120px]">
                <label className="text-[10px] text-zinc-500 block mb-1">CNAE</label>
                <Input value={cnaeInput} onChange={e => setCnaeInput(e.target.value)} placeholder="62" className="h-8 text-xs bg-zinc-900 border-zinc-800" />
              </div>
              <BrandSelect brands={brands} value={selectedBrand} onChange={setSelectedBrand} />
              <Button onClick={composeSectorReport} disabled={composing} className="h-8 text-xs bg-blue-600 hover:bg-blue-700">
                {composing ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <Plus className="w-3 h-3 mr-1.5" />}
                Generar informe
              </Button>
            </CardContent>
          </Card>

          {/* Generate Benchmark */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2"><CardTitle className="text-xs text-zinc-400 flex items-center gap-2"><BarChart3 className="w-3.5 h-3.5" /> Benchmark Report</CardTitle></CardHeader>
            <CardContent className="flex items-end gap-3">
              <div className="flex-1 max-w-[120px]">
                <label className="text-[10px] text-zinc-500 block mb-1">CNAE</label>
                <Input value={cnaeInput} onChange={e => setCnaeInput(e.target.value)} placeholder="62" className="h-8 text-xs bg-zinc-900 border-zinc-800" />
              </div>
              <BrandSelect brands={brands} value={selectedBrand} onChange={setSelectedBrand} />
              <Button onClick={async () => {
                setComposing(true);
                try {
                  const { data: r } = await api.post(`/docstudio/compose/benchmark?cnae_code=${cnaeInput}&brand_id=${selectedBrand}`);
                  toast.success(`Benchmark: ${r.sections} secciones`);
                  loadDashboard(); loadDocuments();
                } catch { toast.error('Error'); }
                setComposing(false);
              }} disabled={composing} className="h-8 text-xs bg-emerald-600 hover:bg-emerald-700">
                {composing ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <Plus className="w-3 h-3 mr-1.5" />}
                Benchmark
              </Button>
            </CardContent>
          </Card>

          {/* Generate Investment Memo / Teaser (need company_id) */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2"><CardTitle className="text-xs text-zinc-400 flex items-center gap-2"><Building2 className="w-3.5 h-3.5" /> Investment Memo / Teaser</CardTitle></CardHeader>
            <CardContent className="flex items-end gap-3">
              <div className="flex-1 max-w-[200px]">
                <label className="text-[10px] text-zinc-500 block mb-1">CIF empresa</label>
                <Input value={cifInput} onChange={e => setCifInput(e.target.value)} placeholder="B12345678" className="h-8 text-xs bg-zinc-900 border-zinc-800" />
              </div>
              <BrandSelect brands={brands} value={selectedBrand} onChange={setSelectedBrand} />
              <Button onClick={async () => {
                setComposing(true);
                try {
                  const { data: r } = await api.post(`/docstudio/compose/investment-memo?cif=${cifInput}&brand_id=${selectedBrand}`);
                  toast.success(`Investment Memo: ${r.sections} secciones`);
                  loadDashboard(); loadDocuments();
                } catch { toast.error('Error'); }
                setComposing(false);
              }} disabled={composing} className="h-8 text-xs bg-violet-600 hover:bg-violet-700">
                <Plus className="w-3 h-3 mr-1.5" /> Inv. Memo
              </Button>
              <Button onClick={async () => {
                setComposing(true);
                try {
                  const { data: r } = await api.post(`/docstudio/compose/teaser?cif=${cifInput}&brand_id=${selectedBrand}`);
                  toast.success(`Teaser: ${r.sections} secciones`);
                  loadDashboard(); loadDocuments();
                } catch { toast.error('Error'); }
                setComposing(false);
              }} disabled={composing} className="h-8 text-xs bg-amber-600 hover:bg-amber-700">
                <Plus className="w-3 h-3 mr-1.5" /> Teaser
              </Button>
              <Button onClick={async () => {
                setComposing(true);
                try {
                  const { data: r } = await api.post(`/docstudio/compose/information-memorandum?cif=${cifInput}&brand_id=${selectedBrand}`);
                  toast.success(`Info Memo: ${r.sections} secciones`);
                  loadDashboard(); loadDocuments();
                } catch { toast.error('Error'); }
                setComposing(false);
              }} disabled={composing} className="h-8 text-xs bg-rose-600 hover:bg-rose-700">
                <Plus className="w-3 h-3 mr-1.5" /> Info Memo
              </Button>
            </CardContent>
          </Card>

          {/* Compose from ANY template */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2"><CardTitle className="text-xs text-zinc-400 flex items-center gap-2"><Zap className="w-3.5 h-3.5" /> Generar desde plantilla</CardTitle></CardHeader>
            <CardContent className="flex items-end gap-3">
              <div className="flex-1 max-w-[200px]">
                <label className="text-[10px] text-zinc-500 block mb-1">Plantilla</label>
                <select value={selectedTemplate} onChange={e => setSelectedTemplate(e.target.value)}
                  className="h-8 w-full rounded border border-zinc-800 bg-zinc-900 text-xs text-zinc-300 px-2">
                  {templates.map(t => <option key={t.template_id} value={t.template_id}>{t.name}</option>)}
                </select>
              </div>
              <div className="flex-1 max-w-[150px]">
                <label className="text-[10px] text-zinc-500 block mb-1">CNAE o CIF</label>
                <Input value={genericInput} onChange={e => setGenericInput(e.target.value)} placeholder="62 o B12345678" className="h-8 text-xs bg-zinc-900 border-zinc-800" />
              </div>
              <BrandSelect brands={brands} value={selectedBrand} onChange={setSelectedBrand} />
              <Button onClick={async () => {
                setComposing(true);
                try {
                  const isCompany = genericInput.length > 3;
                  const params = `template_id=${selectedTemplate}&brand_id=${selectedBrand}` +
                    (isCompany ? `&cif=${genericInput}` : `&cnae_code=${genericInput}`);
                  const { data: r } = await api.post(`/docstudio/compose/from-template?${params}`);
                  toast.success(`${r.title}: ${r.sections} secciones en ${r.generation_time_ms}ms`);
                  loadDashboard(); loadDocuments();
                } catch { toast.error('Error generando'); }
                setComposing(false);
              }} disabled={composing} className="h-8 text-xs bg-cyan-600 hover:bg-cyan-700">
                {composing ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <Zap className="w-3 h-3 mr-1.5" />}
                Generar
              </Button>
            </CardContent>
          </Card>

          {/* Recent */}
          {data?.recent_documents?.length > 0 && (
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader className="pb-2"><CardTitle className="text-xs text-zinc-400">Documentos recientes</CardTitle></CardHeader>
              <Table>
                <TableBody>
                  {data.recent_documents.map(d => (
                    <TableRow key={d.document_id} className="border-zinc-800/50 cursor-pointer hover:bg-zinc-800/30" onClick={() => viewDocument(d.document_id)}>
                      <TableCell className="py-1.5 text-xs text-zinc-300">{d.title}</TableCell>
                      <TableCell className="py-1.5"><Badge variant="outline" className={`text-[9px] ${STATUS_BADGE[d.status] || ''}`}>{d.status}</Badge></TableCell>
                      <TableCell className="py-1.5 text-[10px] text-zinc-500">{fmtDate(d.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="documents" className="mt-3">
          <Card className="bg-zinc-900/50 border-zinc-800">
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800 hover:bg-transparent">
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Titulo</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Estado</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Fecha</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map(d => (
                  <TableRow key={d.document_id} className="border-zinc-800/50">
                    <TableCell className="py-1.5 text-xs text-zinc-300 cursor-pointer hover:text-zinc-100" onClick={() => viewDocument(d.document_id)}>{d.title}</TableCell>
                    <TableCell className="py-1.5"><Badge variant="outline" className={`text-[9px] ${STATUS_BADGE[d.status] || ''}`}>{d.status}</Badge></TableCell>
                    <TableCell className="py-1.5 text-[10px] text-zinc-500">{fmtDate(d.created_at)}</TableCell>
                    <TableCell className="py-1.5">
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="sm" onClick={() => exportPDF(d.document_id)} className="h-5 px-1.5 text-[10px] text-blue-400"><Download className="w-2.5 h-2.5 mr-1" />PDF</Button>
                        <Button variant="ghost" size="sm" onClick={() => deleteDoc(d.document_id)} className="h-5 px-1.5 text-[10px] text-rose-400"><Trash2 className="w-2.5 h-2.5" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {documents.length === 0 && <TableRow><TableCell colSpan={4} className="text-center text-xs text-zinc-600 py-8">Sin documentos. Genera tu primer informe.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="templates" className="mt-3">
          <div className="grid grid-cols-2 gap-3">
            {templates.map(t => (
              <Card key={t.template_id} className="bg-zinc-900/50 border-zinc-800">
                <CardContent className="p-4">
                  <h3 className="text-sm font-semibold text-zinc-200">{t.name}</h3>
                  <p className="text-xs text-zinc-500 mt-1">{t.description}</p>
                  <div className="flex items-center gap-2 mt-2">
                    <Badge variant="outline" className="text-[9px] text-zinc-400 border-zinc-600">v{t.version}</Badge>
                    <Badge variant="outline" className="text-[9px] text-blue-400 border-blue-500/20">{t.sections?.length || 0} secciones</Badge>
                    <Badge variant="outline" className="text-[9px] text-amber-400 border-amber-500/20">IA: {t.analysis_model}</Badge>
                  </div>
                  <div className="mt-2 space-y-0.5">
                    {t.sections?.map((s, i) => (
                      <div key={i} className="text-[10px] text-zinc-500">{s.order}. {s.title}</div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="brands" className="mt-3">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {brands.map(b => (
              <Card key={b.brand_id} className="bg-zinc-900/50 border-zinc-800">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-6 h-6 rounded" style={{background: b.primary_color}} />
                    <div className="w-6 h-6 rounded" style={{background: b.accent_color}} />
                    <span className="text-sm font-semibold text-zinc-200">{b.name}</span>
                  </div>
                  <div className="space-y-1 text-[10px] text-zinc-500">
                    <p>Primario: {b.primary_color}</p>
                    <p>Acento: {b.accent_color}</p>
                    <p>Fuente: {b.font_family?.split(',')[0]}</p>
                    <p>Idioma: {b.language}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
