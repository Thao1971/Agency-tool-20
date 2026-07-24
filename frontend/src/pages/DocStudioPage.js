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
  Star, Clock, Trash2, Bell, CheckCheck
} from 'lucide-react';
import { toast } from 'sonner';
import DocumentEditor from '@/components/DocumentEditor';
import TemplateBuilderPage from '@/pages/TemplateBuilderPage';

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
  const [oppSection, setOppSection] = useState('');
  const [oppProvincia, setOppProvincia] = useState('');
  const [secInput, setSecInput] = useState('C');
  const [documents, setDocuments] = useState([]);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [unread, setUnread] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);

  useEffect(() => {
    loadDashboard();
    loadNotifications();
    const t = setInterval(loadNotifications, 20000);
    return () => clearInterval(t);
  }, []);

  const loadNotifications = async () => {
    try {
      const { data } = await api.get('/docstudio/notifications?limit=20');
      setNotifications(data?.notifications || []);
      setUnread(data?.unread || 0);
    } catch { /* */ }
  };

  const composeAsync = async (docType, params, label) => {
    setComposing(true);
    try {
      const { data: r } = await api.post('/docstudio/compose-async', { doc_type: docType, params, brand_id: selectedBrand });
      const eta = r.eta_ms ? ` (~${Math.max(1, Math.round(r.eta_ms / 1000))} s)` : '';
      toast.success(`${label}: generando en segundo plano${eta}. Te avisaremos al terminar.`);
      setTimeout(loadNotifications, 4000);
      setTimeout(() => { loadNotifications(); loadDashboard(); loadDocuments(); }, 12000);
    } catch { toast.error('Error al encolar la generación'); }
    setComposing(false);
  };

  const openNotification = async (n) => {
    if (!n.read) {
      try { await api.post(`/docstudio/notifications/${n.notification_id}/read`); } catch { /* */ }
      loadNotifications();
    }
    if (n.document_id) { setNotifOpen(false); viewDocument(n.document_id); }
  };

  const markAllRead = async () => {
    try { await api.post('/docstudio/notifications/read-all'); loadNotifications(); } catch { /* */ }
  };

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

  const composeSectorReport = () => {
    if (!cnaeInput) return;
    composeAsync('sector_report', { cnae_code: cnaeInput }, 'Informe sectorial');
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
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-bold text-zinc-100">Document Intelligence Studio</h1>
          <p className="text-xs text-zinc-500 mt-0.5">Motor documental corporativo — datos a documentos profesionales</p>
        </div>
        <div className="relative">
          <Button variant="outline" size="sm" onClick={() => { setNotifOpen(o => !o); loadNotifications(); }}
            className="border-zinc-700 text-zinc-300 h-8 relative" data-testid="notif-bell">
            <Bell className="w-4 h-4" />
            {unread > 0 && <span className="absolute -top-1.5 -right-1.5 bg-rose-600 text-white text-[9px] font-bold rounded-full min-w-[16px] h-4 px-1 flex items-center justify-center">{unread}</span>}
          </Button>
          {notifOpen && (
            <div className="absolute right-0 mt-1 w-80 max-h-96 overflow-auto bg-zinc-900 border border-zinc-800 rounded-lg shadow-xl z-30" data-testid="notif-panel">
              <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800">
                <span className="text-xs font-semibold text-zinc-300">Notificaciones</span>
                {unread > 0 && <button onClick={markAllRead} className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center gap-1"><CheckCheck className="w-3 h-3" />Marcar leídas</button>}
              </div>
              {notifications.length === 0 && <p className="text-[11px] text-zinc-600 text-center py-6">Sin notificaciones</p>}
              {notifications.map(n => (
                <button key={n.notification_id} onClick={() => openNotification(n)}
                  className={`w-full text-left px-3 py-2 border-b border-zinc-800/50 hover:bg-zinc-800/40 ${n.read ? 'opacity-60' : ''}`}>
                  <div className="flex items-start gap-2">
                    <span className={`mt-1 w-1.5 h-1.5 rounded-full flex-shrink-0 ${n.level === 'error' ? 'bg-rose-500' : n.level === 'success' ? 'bg-emerald-500' : 'bg-blue-500'}`} />
                    <div className="min-w-0">
                      <p className="text-[11px] text-zinc-300 leading-snug">{n.title}</p>
                      <p className="text-[9px] text-zinc-600 mt-0.5">{fmtDate(n.created_at)}{n.document_id ? ' · abrir documento' : ''}</p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
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
          <TabsTrigger value="builder" className="text-xs data-[state=active]:bg-zinc-800">Constructor</TabsTrigger>
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
              <Button onClick={() => composeAsync('benchmark', { cnae_code: cnaeInput }, 'Benchmark')}
                disabled={composing} className="h-8 text-xs bg-emerald-600 hover:bg-emerald-700">
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
              <Button onClick={() => composeAsync('investment_memo', { cif: cifInput }, 'Investment Memo')}
                disabled={composing} className="h-8 text-xs bg-violet-600 hover:bg-violet-700">
                <Plus className="w-3 h-3 mr-1.5" /> Inv. Memo
              </Button>
              <Button onClick={() => composeAsync('teaser', { cif: cifInput }, 'Teaser')}
                disabled={composing} className="h-8 text-xs bg-amber-600 hover:bg-amber-700">
                <Plus className="w-3 h-3 mr-1.5" /> Teaser
              </Button>
              <Button onClick={() => composeAsync('information_memorandum', { cif: cifInput }, 'Information Memorandum')}
                disabled={composing} className="h-8 text-xs bg-rose-600 hover:bg-rose-700">
                <Plus className="w-3 h-3 mr-1.5" /> Info Memo
              </Button>
            </CardContent>
          </Card>

          {/* Documentos de empresa: valoración y estrategia */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2"><CardTitle className="text-xs text-zinc-400 flex items-center gap-2"><Building2 className="w-3.5 h-3.5" /> Empresa — Valoración y Estrategia</CardTitle></CardHeader>
            <CardContent className="flex items-end gap-3 flex-wrap">
              <div className="max-w-[180px]">
                <label className="text-[10px] text-zinc-500 block mb-1">CIF empresa</label>
                <Input value={cifInput} onChange={e => setCifInput(e.target.value)} placeholder="B12345678" className="h-8 text-xs bg-zinc-900 border-zinc-800" />
              </div>
              <BrandSelect brands={brands} value={selectedBrand} onChange={setSelectedBrand} />
              <Button onClick={() => composeAsync('valuation_approx', { cif: cifInput }, 'Aproximación de valor')} disabled={composing} className="h-8 text-xs bg-teal-600 hover:bg-teal-700"><Plus className="w-3 h-3 mr-1.5" />Aprox. valor</Button>
              <Button onClick={() => composeAsync('valuation_advanced', { cif: cifInput }, 'Valoración avanzada')} disabled={composing} className="h-8 text-xs bg-emerald-600 hover:bg-emerald-700"><Plus className="w-3 h-3 mr-1.5" />Valoración avanzada</Button>
              <Button onClick={() => composeAsync('strategic_analysis', { cif: cifInput }, 'Análisis estratégico')} disabled={composing} className="h-8 text-xs bg-violet-600 hover:bg-violet-700"><Plus className="w-3 h-3 mr-1.5" />Análisis estratégico</Button>
              <Button onClick={() => composeAsync('comparative', { cif: cifInput }, 'Análisis comparativo')} disabled={composing} className="h-8 text-xs bg-sky-600 hover:bg-sky-700"><Plus className="w-3 h-3 mr-1.5" />Comparativo</Button>
              <Button onClick={() => composeAsync('succession', { cif: cifInput }, 'Perfil de sucesión')} disabled={composing} className="h-8 text-xs bg-amber-600 hover:bg-amber-700"><Plus className="w-3 h-3 mr-1.5" />Perfil sucesión</Button>
            </CardContent>
          </Card>

          {/* Documentos de sector / cartera */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2"><CardTitle className="text-xs text-zinc-400 flex items-center gap-2"><BarChart3 className="w-3.5 h-3.5" /> Sector — Ranking, Fragmentación y Roll-up</CardTitle></CardHeader>
            <CardContent className="flex items-end gap-3 flex-wrap">
              <div className="max-w-[110px]">
                <label className="text-[10px] text-zinc-500 block mb-1">Sección CNAE</label>
                <Input value={secInput} onChange={e => setSecInput(e.target.value.toUpperCase())} placeholder="C" className="h-8 text-xs bg-zinc-900 border-zinc-800" />
              </div>
              <BrandSelect brands={brands} value={selectedBrand} onChange={setSelectedBrand} />
              <Button onClick={() => composeAsync('ranking', { cnae_section: secInput }, 'Ranking sectorial')} disabled={composing} className="h-8 text-xs bg-blue-600 hover:bg-blue-700"><Plus className="w-3 h-3 mr-1.5" />Ranking</Button>
              <Button onClick={() => composeAsync('fragmentation', { cnae_section: secInput }, 'Mapa de fragmentación')} disabled={composing} className="h-8 text-xs bg-cyan-600 hover:bg-cyan-700"><Plus className="w-3 h-3 mr-1.5" />Fragmentación</Button>
              <Button onClick={() => composeAsync('rollup', { cnae_section: secInput }, 'Tesis de roll-up')} disabled={composing} className="h-8 text-xs bg-rose-600 hover:bg-rose-700"><Plus className="w-3 h-3 mr-1.5" />Roll-up</Button>
            </CardContent>
          </Card>

          {/* Documento de Oportunidades (acotado) */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2"><CardTitle className="text-xs text-zinc-400 flex items-center gap-2"><Zap className="w-3.5 h-3.5" /> Documento de Oportunidades <span className="text-[10px] text-zinc-600">(siempre acotado — nunca todo el universo)</span></CardTitle></CardHeader>
            <CardContent className="flex items-end gap-3 flex-wrap">
              <div className="max-w-[110px]">
                <label className="text-[10px] text-zinc-500 block mb-1">Sección CNAE</label>
                <Input value={oppSection} onChange={e => setOppSection(e.target.value.toUpperCase())} placeholder="J" className="h-8 text-xs bg-zinc-900 border-zinc-800" />
              </div>
              <div className="max-w-[150px]">
                <label className="text-[10px] text-zinc-500 block mb-1">Provincia</label>
                <Input value={oppProvincia} onChange={e => setOppProvincia(e.target.value)} placeholder="Madrid" className="h-8 text-xs bg-zinc-900 border-zinc-800" />
              </div>
              <BrandSelect brands={brands} value={selectedBrand} onChange={setSelectedBrand} />
              <Button onClick={() => {
                const params = {};
                if (oppSection) params.cnae_section = oppSection;
                if (oppProvincia) params.provincia = oppProvincia;
                composeAsync('opportunities', params, 'Documento de Oportunidades');
              }} disabled={composing} className="h-8 text-xs bg-blue-600 hover:bg-blue-700">
                {composing ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <Zap className="w-3 h-3 mr-1.5" />}
                Generar
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
              <Button onClick={() => {
                const isCompany = genericInput.length > 3;
                const params = { template_id: selectedTemplate };
                if (isCompany) params.cif = genericInput; else params.cnae_code = genericInput;
                composeAsync('from_template', params, 'Documento');
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

        <TabsContent value="builder" className="mt-3">
          <TemplateBuilderPage />
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
