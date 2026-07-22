import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle
} from '@/components/ui/dialog';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table';
import {
  Tabs, TabsContent, TabsList, TabsTrigger
} from '@/components/ui/tabs';
import {
  FileText, Plus, Play, Download, Eye, Loader2, CheckCircle,
  Edit2, Sparkles, ArrowLeft, ArrowRight, X
} from 'lucide-react';
import { toast } from 'sonner';

const STATUS_STYLES = {
  queued: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  processing: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  completed: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  failed: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
  draft: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  published: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
};

const EDITABLE_BLOCKS = [
  { key: 'executive_summary', label: 'Executive Summary', type: 'textarea' },
  { key: 'company_overview', label: 'Company Overview', type: 'textarea' },
  { key: 'top_strengths', label: 'Key Strengths', type: 'list' },
  { key: 'top_risks', label: 'Key Risks', type: 'list' },
  { key: 'financial_highlights', label: 'Financial Highlights', type: 'textarea' },
  { key: 'market_position', label: 'Market Position', type: 'textarea' },
  { key: 'next_steps', label: 'Next Steps', type: 'list' },
];

export default function DocumentsPage() {
  const [tab, setTab] = useState('create');
  const [templates, setTemplates] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [outputs, setOutputs] = useState([]);

  // Wizard state
  const [step, setStep] = useState(1); // 1=setup, 2=edit blocks, 3=preview, 4=generate
  const [selTemplate, setSelTemplate] = useState('');
  const [selFormat, setSelFormat] = useState('pdf');
  const [selBrand, setSelBrand] = useState('brand_bud');
  const [brands, setBrands] = useState([]);
  const [docTitle, setDocTitle] = useState('');
  const [docSubtitle, setDocSubtitle] = useState('');
  const [blocks, setBlocks] = useState({});
  const [previewHtml, setPreviewHtml] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generatedJobId, setGeneratedJobId] = useState(null);
  const [generatedOutput, setGeneratedOutput] = useState(null);

  // Source data from scraper
  const [scraperSearch, setScraperSearch] = useState('');
  const [scraperResult, setScraperResult] = useState(null);

  const fetchAll = useCallback(async () => {
    try {
      const [tpl, jbs, outs, brd] = await Promise.all([
        api.get('/documents/templates'),
        api.get('/documents/jobs?limit=20'),
        api.get('/documents/outputs?limit=20'),
        api.get('/documents/brands').catch(() => ({ data: { brands: [] } }))
      ]);
      setTemplates(tpl.data.templates || []);
      setJobs(jbs.data.jobs || []);
      setOutputs(outs.data.outputs || []);
      setBrands(brd.data.brands || []);
    } catch (err) {  }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Load scraper result
  const loadFromScraper = async () => {
    if (!scraperSearch.trim()) return;
    try {
      const res = await api.get(`/results?search=${encodeURIComponent(scraperSearch)}&limit=1`);
      const r = res.data.results?.[0];
      if (!r) { toast.error('No agency found'); return; }
      setScraperResult(r);
      setDocTitle(r.company_name || '');
      setDocSubtitle('Agency Profile Report');
      // Pre-fill blocks from scraper data
      setBlocks({
        company_name: r.company_name || '',
        subtitle: 'Agency Profile Report',
        category: r.category || '',
        subcategory: r.subcategory || '',
        website: r.input_url || '',
        city: r.address_city || '',
        country: r.country || 'Spain',
        main_contact_email: r.main_contact_email || '',
        phone: r.phone || '',
        confidence_overall: String(r.confidence_overall || 0),
        confidence_category: String(r.confidence_category || 0),
        num_clients: String((r.main_clients || []).length),
        num_pages_visited: String((r.visited_pages || []).length),
        has_awards_text: r.has_awards ? 'Yes' : 'No',
        num_tags: String((r.tags || []).length),
        executive_summary: r.description || '',
        company_overview: r.description || '',
        top_strengths: [],
        top_risks: [],
        clients_list: r.main_clients || [],
        tags_list: r.tags || [],
        market_position: '',
        financial_highlights: '',
        next_steps: [],
      });
      toast.success(`Loaded: ${r.company_name}`);
    } catch { toast.error('Search failed'); }
  };

  const updateBlock = (key, value) => {
    setBlocks(prev => ({ ...prev, [key]: value }));
  };

  const updateListItem = (key, idx, value) => {
    setBlocks(prev => {
      const list = [...(prev[key] || [])];
      list[idx] = value;
      return { ...prev, [key]: list };
    });
  };

  const addListItem = (key) => {
    setBlocks(prev => ({ ...prev, [key]: [...(prev[key] || []), ''] }));
  };

  const removeListItem = (key, idx) => {
    setBlocks(prev => {
      const list = [...(prev[key] || [])];
      list.splice(idx, 1);
      return { ...prev, [key]: list };
    });
  };

  // AI generate block
  const aiGenerateBlock = async (blockKey) => {
    try {
      const res = await api.post('/documents/ai/generate-blocks', {
        block_type: blockKey,
        context: { ...blocks, company_name: docTitle },
        locale: 'es',
        model: blockKey.includes('strengths') || blockKey.includes('risks') || blockKey === 'executive_summary' ? 'primary' : 'secondary'
      });
      if (res.data.block?.content) {
        const content = res.data.block.content;
        updateBlock(blockKey, content);
        toast.success(`AI generated: ${blockKey}`);
      }
    } catch { toast.error('AI generation failed'); }
  };

  // Preview
  const loadPreview = async () => {
    setPreviewLoading(true);
    try {
      const res = await api.post('/documents/preview', {
        template_id: selTemplate,
        brand_id: selBrand,
        output_format: selFormat,
        data_payload: { ...blocks, company_name: docTitle, subtitle: docSubtitle }
      }, { responseType: 'text' });
      setPreviewHtml(res.data);
      setStep(3);
    } catch (err) {
      toast.error('Preview failed');
    } finally {
      setPreviewLoading(false);
    }
  };

  // Generate final
  const generateFinal = async () => {
    setGenerating(true);
    try {
      const res = await api.post('/documents/generate', {
        template_id: selTemplate,
        brand_id: selBrand,
        output_format: selFormat,
        source_app: scraperResult ? 'scraper' : 'manual',
        source_entity_id: scraperResult?.id,
        data_payload: { ...blocks, company_name: docTitle, subtitle: docSubtitle }
      });
      const jobId = res.data.job_id;
      setGeneratedJobId(jobId);
      setStep(4);

      // Poll
      const poll = setInterval(async () => {
        const jr = await api.get(`/documents/jobs/${jobId}`);
        if (jr.data.status === 'completed') {
          clearInterval(poll);
          const out = await api.get(`/documents/outputs/${jr.data.output_id}`);
          setGeneratedOutput(out.data);
          fetchAll();
          toast.success('Document generated');
        } else if (jr.data.status === 'failed') {
          clearInterval(poll);
          toast.error(`Failed: ${jr.data.error_message || 'unknown'}`);
        }
      }, 2000);
    } catch (err) {
      toast.error('Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async (output) => {
    try {
      const res = await api.get(`/screenshots/${output.storage_path}`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${output.output_id}.${output.output_format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error('Download failed'); }
  };

  const resetWizard = () => {
    setStep(1); setBlocks({}); setDocTitle(''); setDocSubtitle('');
    setScraperResult(null); setPreviewHtml(''); setGeneratedJobId(null);
    setGeneratedOutput(null); setScraperSearch('');
  };

  return (
    <div className="space-y-6" data-testid="documents-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">Document Generator</h1>
          <p className="text-sm text-zinc-400 mt-1">Generate PDF reports with AI content and corporate branding</p>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="create" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400">
            <Plus className="w-3.5 h-3.5 mr-1.5" /> Create
          </TabsTrigger>
          <TabsTrigger value="outputs" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400">
            Outputs ({outputs.length})
          </TabsTrigger>
          <TabsTrigger value="jobs" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400">
            Jobs ({jobs.length})
          </TabsTrigger>
        </TabsList>

        {/* CREATE TAB — Wizard flow */}
        <TabsContent value="create">
          {/* Step indicators */}
          <div className="flex items-center gap-2 mb-6">
            {['Setup', 'Edit Blocks', 'Preview', 'Generate'].map((label, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                  step > i + 1 ? 'bg-emerald-600 text-white' :
                  step === i + 1 ? 'bg-blue-600 text-white' :
                  'bg-zinc-800 text-zinc-500'
                }`}>{i + 1}</div>
                <span className={`text-xs ${step === i + 1 ? 'text-zinc-200' : 'text-zinc-500'}`}>{label}</span>
                {i < 3 && <div className="w-8 h-px bg-zinc-700" />}
              </div>
            ))}
          </div>

          {/* STEP 1: Setup */}
          {step === 1 && (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardContent className="p-6 space-y-5">
                <div className="space-y-2">
                  <Label className="text-zinc-300 text-xs uppercase tracking-wider">Load from Scraper</Label>
                  <div className="flex gap-2">
                    <Input value={scraperSearch} onChange={e => setScraperSearch(e.target.value)}
                      placeholder="Search agency name..." onKeyDown={e => e.key === 'Enter' && loadFromScraper()}
                      className="bg-zinc-950 border-zinc-700 text-zinc-50" data-testid="scraper-search" />
                    <Button variant="outline" onClick={loadFromScraper}
                      className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 shrink-0">Load</Button>
                  </div>
                  {scraperResult && (
                    <Badge className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      <CheckCircle className="w-3 h-3 mr-1" /> {scraperResult.company_name} loaded
                    </Badge>
                  )}
                </div>
                <Separator className="bg-zinc-800" />
                <div className="grid grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label className="text-zinc-300 text-xs">Template</Label>
                    <Select value={selTemplate} onValueChange={setSelTemplate}>
                      <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200" data-testid="select-template">
                        <SelectValue placeholder="Select template" />
                      </SelectTrigger>
                      <SelectContent className="bg-zinc-900 border-zinc-700">
                        {templates.map(t => (
                          <SelectItem key={t.template_id} value={t.template_id}>{t.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-zinc-300 text-xs">Brand / Theme</Label>
                    <Select value={selBrand} onValueChange={setSelBrand}>
                      <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200" data-testid="select-brand">
                        <SelectValue placeholder="Select brand" />
                      </SelectTrigger>
                      <SelectContent className="bg-zinc-900 border-zinc-700">
                        {brands.map(b => (
                          <SelectItem key={b.brand_id} value={b.brand_id}>
                            {b.name} {b.is_default ? '(default)' : ''}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-zinc-300 text-xs">Format</Label>
                    <Select value={selFormat} onValueChange={setSelFormat}>
                      <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-zinc-900 border-zinc-700">
                        <SelectItem value="pdf">PDF</SelectItem>
                        <SelectItem value="pptx">PowerPoint</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label className="text-zinc-300 text-xs">Title</Label>
                    <Input value={docTitle} onChange={e => setDocTitle(e.target.value)}
                      placeholder="Company name" className="bg-zinc-950 border-zinc-700 text-zinc-50" />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-zinc-300 text-xs">Subtitle</Label>
                    <Input value={docSubtitle} onChange={e => setDocSubtitle(e.target.value)}
                      placeholder="Report type" className="bg-zinc-950 border-zinc-700 text-zinc-50" />
                  </div>
                </div>
                <div className="flex justify-end">
                  <Button onClick={() => { if (!selTemplate) { toast.error('Select a template'); return; } setStep(2); }}
                    className="bg-blue-600 hover:bg-blue-500 text-white" data-testid="step1-next">
                    Next: Edit Blocks <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* STEP 2: Edit Blocks */}
          {step === 2 && (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-heading text-zinc-300 flex items-center gap-2">
                  <Edit2 className="w-4 h-4" /> Edit Content Blocks
                </CardTitle>
              </CardHeader>
              <CardContent className="p-6 space-y-4">
                {EDITABLE_BLOCKS.map(block => (
                  <div key={block.key} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-zinc-300 text-xs uppercase tracking-wider">{block.label}</Label>
                      <Button variant="ghost" size="sm" onClick={() => aiGenerateBlock(block.key)}
                        className="text-xs text-blue-400 hover:text-blue-300 h-6 px-2"
                        data-testid={`ai-gen-${block.key}`}>
                        <Sparkles className="w-3 h-3 mr-1" /> AI Generate
                      </Button>
                    </div>
                    {block.type === 'textarea' ? (
                      <Textarea value={blocks[block.key] || ''} onChange={e => updateBlock(block.key, e.target.value)}
                        rows={3} className="bg-zinc-950 border-zinc-700 text-zinc-50 text-sm" />
                    ) : (
                      <div className="space-y-1">
                        {(blocks[block.key] || []).map((item, idx) => (
                          <div key={idx} className="flex gap-2">
                            <Input value={item} onChange={e => updateListItem(block.key, idx, e.target.value)}
                              className="bg-zinc-950 border-zinc-700 text-zinc-50 text-sm flex-1" />
                            <Button variant="ghost" size="sm" onClick={() => removeListItem(block.key, idx)}
                              className="h-9 w-9 p-0 text-zinc-500 hover:text-rose-400">
                              <X className="w-3.5 h-3.5" />
                            </Button>
                          </div>
                        ))}
                        <Button variant="ghost" size="sm" onClick={() => addListItem(block.key)}
                          className="text-xs text-blue-400 hover:text-blue-300 h-7 px-2">
                          <Plus className="w-3 h-3 mr-1" /> Add item
                        </Button>
                      </div>
                    )}
                  </div>
                ))}
                <Separator className="bg-zinc-800" />
                <div className="flex justify-between">
                  <Button variant="outline" onClick={() => setStep(1)}
                    className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
                    <ArrowLeft className="w-4 h-4 mr-2" /> Back
                  </Button>
                  <Button onClick={loadPreview} disabled={previewLoading}
                    className="bg-blue-600 hover:bg-blue-500 text-white" data-testid="step2-preview">
                    {previewLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Eye className="w-4 h-4 mr-2" />}
                    Preview
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* STEP 3: Preview */}
          {step === 3 && (
            <div className="space-y-4">
              <Card className="bg-zinc-900 border-zinc-800">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Eye className="w-4 h-4 text-blue-400" />
                      <span className="text-sm font-medium text-zinc-200">Document Preview</span>
                      <Badge className="bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[10px]">
                        Review before generating
                      </Badge>
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => setStep(2)}
                        className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
                        <ArrowLeft className="w-3.5 h-3.5 mr-1.5" /> Edit
                      </Button>
                      <Button size="sm" onClick={generateFinal} disabled={generating}
                        className="bg-emerald-600 hover:bg-emerald-500 text-white" data-testid="step3-generate">
                        {generating ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Play className="w-3.5 h-3.5 mr-1.5" />}
                        Generate Final PDF
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <div className="rounded-lg border border-zinc-700 overflow-hidden bg-zinc-950" style={{ height: '70vh' }}>
                <iframe srcDoc={previewHtml} title="Document Preview"
                  className="w-full h-full" style={{ border: 'none' }}
                  data-testid="preview-iframe" />
              </div>
            </div>
          )}

          {/* STEP 4: Generated */}
          {step === 4 && (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardContent className="p-8 text-center space-y-4">
                {generatedOutput ? (
                  <>
                    <CheckCircle className="w-12 h-12 text-emerald-400 mx-auto" />
                    <h3 className="text-lg font-bold text-zinc-50 font-heading">Document Generated</h3>
                    <p className="text-sm text-zinc-400">
                      {generatedOutput.output_format?.toUpperCase()} — {((generatedOutput.size_bytes || 0) / 1024).toFixed(0)} KB
                    </p>
                    <div className="flex gap-3 justify-center">
                      <Button onClick={() => handleDownload(generatedOutput)}
                        className="bg-blue-600 hover:bg-blue-500 text-white" data-testid="download-final">
                        <Download className="w-4 h-4 mr-2" /> Download
                      </Button>
                      <Button variant="outline" onClick={resetWizard}
                        className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
                        <Plus className="w-4 h-4 mr-2" /> New Document
                      </Button>
                    </div>
                  </>
                ) : (
                  <>
                    <Loader2 className="w-10 h-10 text-blue-400 mx-auto animate-spin" />
                    <h3 className="text-lg font-bold text-zinc-50 font-heading">Generating...</h3>
                    <p className="text-sm text-zinc-400">This usually takes 2-5 seconds</p>
                  </>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* OUTPUTS TAB */}
        <TabsContent value="outputs">
          <div className="rounded border border-zinc-800 overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900">
                  <TableHead className="text-xs uppercase tracking-wider text-zinc-500">Output</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-zinc-500">Format</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-zinc-500">Size</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-zinc-500">Source</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-zinc-500">Date</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-zinc-500 w-20">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {outputs.length === 0 && (
                  <TableRow><TableCell colSpan={6} className="text-center text-zinc-500 py-8">No outputs yet</TableCell></TableRow>
                )}
                {outputs.map(o => (
                  <TableRow key={o.output_id} className="border-zinc-800 hover:bg-zinc-800/30">
                    <TableCell className="text-xs font-mono text-zinc-300">{o.output_id}</TableCell>
                    <TableCell><Badge variant="outline" className="text-[10px] text-zinc-300 border-zinc-600">{o.output_format}</Badge></TableCell>
                    <TableCell className="text-xs text-zinc-400">{o.size_bytes ? `${(o.size_bytes/1024).toFixed(0)} KB` : '-'}</TableCell>
                    <TableCell className="text-xs text-zinc-400">{o.source_app || 'manual'}</TableCell>
                    <TableCell className="text-xs text-zinc-500 font-mono">{o.created_at?.substring(0, 19)}</TableCell>
                    <TableCell>
                      <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-zinc-400 hover:text-blue-400"
                        onClick={() => handleDownload(o)}><Download className="w-3.5 h-3.5" /></Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        {/* JOBS TAB */}
        <TabsContent value="jobs">
          <div className="rounded border border-zinc-800 overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900">
                  <TableHead className="text-xs uppercase tracking-wider text-zinc-500">Job</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-zinc-500">Format</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-zinc-500">Source</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-zinc-500">Status</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-zinc-500">Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.length === 0 && (
                  <TableRow><TableCell colSpan={5} className="text-center text-zinc-500 py-8">No jobs yet</TableCell></TableRow>
                )}
                {jobs.map(j => (
                  <TableRow key={j.job_id} className="border-zinc-800 hover:bg-zinc-800/30">
                    <TableCell className="text-xs font-mono text-zinc-300">{j.job_id?.substring(0, 16)}</TableCell>
                    <TableCell><Badge variant="outline" className="text-[10px] text-zinc-300 border-zinc-600">{j.output_format}</Badge></TableCell>
                    <TableCell className="text-xs text-zinc-400">{j.source_app || 'manual'}</TableCell>
                    <TableCell>
                      <Badge className={`text-xs border ${STATUS_STYLES[j.status]}`}>
                        {j.status === 'processing' && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
                        {j.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-zinc-500 font-mono">{j.created_at?.substring(0, 19)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
