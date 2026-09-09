import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { resultsAPI, getScreenshotUrl } from '@/lib/api';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import {
  ArrowLeft, ExternalLink, CheckCircle, User, Phone, Mail,
  MapPin, Award, Users, Tag, Shield, FileText, Download, Send,
  RefreshCw, Loader2, AlertTriangle
} from 'lucide-react';
import { toast } from 'sonner';

function ConfidenceBar({ value, label }) {
  const color = value > 80 ? 'bg-emerald-500' : value > 50 ? 'bg-amber-500' : 'bg-rose-500';
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-zinc-400 w-24 truncate">{label}</span>
      <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value}%` }} />
      </div>
      <span className="text-xs font-mono text-zinc-300 w-8 text-right">{value}</span>
    </div>
  );
}

export default function ResultDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [validating, setValidating] = useState(false);
  const [sending, setSending] = useState(null);
  const [sendLog, setSendLog] = useState([]);

  useEffect(() => {
    resultsAPI.get(id)
      .then(r => setResult(r.data))
      .catch(() => toast.error('Failed to load result'))
      .finally(() => setLoading(false));
    api.get(`/results/${id}/send-log`).then(r => setSendLog(r.data)).catch(() => {});
  }, [id]);

  const handleValidate = async () => {
    setValidating(true);
    try {
      await resultsAPI.validate(id);
      setResult(prev => ({ ...prev, validated: true, review_status: 'validated' }));
      toast.success('Result validated');
    } catch {
      toast.error('Validation failed');
    } finally {
      setValidating(false);
    }
  };

  const handleExportPdf = async () => {
    try {
      const res = await api.get(`/results/${id}/pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(result?.company_name || 'agency').replace(/\s+/g, '_')}_report.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('PDF downloaded');
    } catch {
      toast.error('PDF export failed');
    }
  };

  const handleSendTo = async (destination) => {
    setSending(destination);
    try {
      const res = await api.post(`/results/${id}/send`, { destination, environment: 'production' });
      if (res.data.status === 'sent') {
        toast.success(`Sent to ${destination}`);
      } else {
        toast.error(`Send to ${destination} failed: ${res.data.error || 'unknown'}`);
      }
      api.get(`/results/${id}/send-log`).then(r => setSendLog(r.data)).catch(() => {});
    } catch (err) {
      toast.error(`Send failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setSending(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48 bg-zinc-800" />
        <Skeleton className="h-64 bg-zinc-800 rounded" />
      </div>
    );
  }

  if (!result) {
    return <p className="text-zinc-400">Result not found</p>;
  }

  const screenshotUrl = result.screenshot_path ? getScreenshotUrl(result.screenshot_path) : null;

  return (
    <div className="space-y-6" data-testid="result-detail-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate('/results')}
            data-testid="back-to-results-btn"
            className="text-zinc-400 hover:text-zinc-100 h-8 w-8 p-0">
            <ArrowLeft className="w-4 h-4" />
          </Button>
          {result.logo_url && (
            <div className="w-10 h-10 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center overflow-hidden shrink-0">
              <img src={result.logo_url} alt="Logo" className="w-full h-full object-contain p-1"
                onError={(e) => { e.target.parentElement.style.display = 'none'; }} />
            </div>
          )}
          <div>
            <h1 className="text-xl font-bold tracking-tight text-zinc-50 font-heading">
              {result.company_name || 'Unknown Agency'}
            </h1>
            <a href={result.input_url} target="_blank" rel="noopener noreferrer"
              className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1">
              {result.input_url} <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* PDF Export */}
          <Button variant="outline" size="sm" onClick={handleExportPdf}
            data-testid="export-pdf-btn"
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100">
            <Download className="w-3.5 h-3.5 mr-1.5" /> PDF
          </Button>

          {/* Send to consumer */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" disabled={!!sending}
                data-testid="send-to-btn"
                className="border-zinc-700 text-zinc-300 hover:bg-blue-500/10 hover:text-blue-400 hover:border-blue-500/30">
                {sending ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Send className="w-3.5 h-3.5 mr-1.5" />}
                Send to...
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="bg-zinc-900 border-zinc-700">
              <DropdownMenuItem onClick={() => handleSendTo('cis')}
                className="text-zinc-200 focus:bg-zinc-800 focus:text-zinc-50 cursor-pointer">
                Send to CIS
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleSendTo('arroba')}
                className="text-zinc-200 focus:bg-zinc-800 focus:text-zinc-50 cursor-pointer">
                Send to Arroba
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Validate */}
          {!result.validated && (
            <Button onClick={handleValidate} disabled={validating} size="sm"
              data-testid="validate-result-btn"
              className="bg-emerald-600 hover:bg-emerald-500 text-white">
              <CheckCircle className="w-3.5 h-3.5 mr-1.5" />
              {validating ? 'Validating...' : 'Validate'}
            </Button>
          )}
          {result.validated && (
            <Badge className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <CheckCircle className="w-3 h-3 mr-1" /> Validated
            </Badge>
          )}

          <div className="text-center ml-2">
            <span className="text-3xl font-bold font-mono text-zinc-50">{result.confidence_overall}</span>
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">Score</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left */}
        <div className="lg:col-span-3 space-y-4">
          {/* Description */}
          {result.description && (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardContent className="p-5">
                <p className="text-sm text-zinc-300 leading-relaxed">{result.description}</p>
                <div className="flex flex-wrap gap-2 mt-3">
                  {result.category && (
                    <Badge className="bg-blue-500/10 text-blue-400 border border-blue-500/20">{result.category}</Badge>
                  )}
                  {result.subcategory && (
                    <Badge className="bg-zinc-700/50 text-zinc-300 border border-zinc-600/30">{result.subcategory}</Badge>
                  )}
                  <Badge className="bg-zinc-700/30 text-zinc-400 border border-zinc-600/20 text-[10px]">
                    Taxonomy {result.taxonomy_version}
                  </Badge>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Tags */}
          {result.tags?.length > 0 && (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium flex items-center gap-2">
                  <Tag className="w-3 h-3" /> Tags
                </CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4">
                <div className="flex flex-wrap gap-1.5">
                  {result.tags.map((t, i) => (
                    <Badge key={i} variant="outline" className="text-zinc-300 border-zinc-700 text-xs">{t}</Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Contact & Address */}
          <div className="grid grid-cols-2 gap-4">
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium flex items-center gap-2">
                  <User className="w-3 h-3" /> Contact
                </CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4 space-y-2">
                {result.main_contact_name && (
                  <p className="text-sm text-zinc-200 flex items-center gap-2">
                    <User className="w-3 h-3 text-zinc-500" />
                    {result.main_contact_name}
                    {result.main_contact_role && <span className="text-zinc-500">({result.main_contact_role})</span>}
                  </p>
                )}
                {result.main_contact_email && (
                  <p className="text-sm text-zinc-200 flex items-center gap-2">
                    <Mail className="w-3 h-3 text-zinc-500" /> {result.main_contact_email}
                  </p>
                )}
                {result.phone && (
                  <p className="text-sm text-zinc-200 flex items-center gap-2">
                    <Phone className="w-3 h-3 text-zinc-500" /> {result.phone}
                  </p>
                )}
                {!result.main_contact_name && !result.main_contact_email && !result.phone && (
                  <p className="text-sm text-zinc-600">No contact found</p>
                )}
              </CardContent>
            </Card>

            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium flex items-center gap-2">
                  <MapPin className="w-3 h-3" /> Address
                </CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4 space-y-1">
                {result.address_street && <p className="text-sm text-zinc-200">{result.address_street}</p>}
                {(result.address_city || result.address_province) && (
                  <p className="text-sm text-zinc-300">
                    {[result.address_city, result.address_province, result.postal_code].filter(Boolean).join(', ')}
                  </p>
                )}
                {result.country && <p className="text-sm text-zinc-400">{result.country}</p>}
                {!result.address_street && !result.address_city && (
                  <p className="text-sm text-zinc-600">No address found</p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Clients & Awards */}
          <div className="grid grid-cols-2 gap-4">
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium flex items-center gap-2">
                  <Users className="w-3 h-3" /> Clients ({result.main_clients?.length || 0})
                </CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4">
                {result.main_clients?.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {result.main_clients.map((c, i) => (
                      <Badge key={i} className="bg-zinc-800 text-zinc-200 border border-zinc-700 text-xs">{c}</Badge>
                    ))}
                  </div>
                ) : <p className="text-sm text-zinc-600">No clients detected</p>}
              </CardContent>
            </Card>

            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium flex items-center gap-2">
                  <Award className="w-3 h-3" /> Awards
                </CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4">
                {result.has_awards && result.awards_evidence?.length > 0 ? (
                  <div className="space-y-1">
                    {result.awards_evidence.map((a, i) => <p key={i} className="text-sm text-zinc-200">{a}</p>)}
                  </div>
                ) : <p className="text-sm text-zinc-600">No awards detected</p>}
              </CardContent>
            </Card>
          </div>

          {/* Confidence */}
          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2 pt-4 px-5">
              <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium flex items-center gap-2">
                <Shield className="w-3 h-3" /> Confidence Scores
              </CardTitle>
            </CardHeader>
            <CardContent className="px-5 pb-4 space-y-2">
              <ConfidenceBar value={result.confidence_overall} label="Overall" />
              <ConfidenceBar value={result.confidence_category} label="Category" />
              <ConfidenceBar value={result.confidence_description} label="Description" />
              <ConfidenceBar value={result.confidence_clients} label="Clients" />
              <ConfidenceBar value={result.confidence_contact} label="Contact" />
              <ConfidenceBar value={result.confidence_awards} label="Awards" />
              <ConfidenceBar value={result.confidence_address} label="Address" />
            </CardContent>
          </Card>

          {/* Evidence */}
          {result.evidence?.length > 0 && (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium flex items-center gap-2">
                  <FileText className="w-3 h-3" /> Evidence ({result.evidence.length})
                </CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4 space-y-2">
                {result.evidence.map((e, i) => (
                  <div key={i} className="p-2.5 rounded bg-zinc-800/50 border border-zinc-700/50">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="outline" className="text-[10px] uppercase text-zinc-400 border-zinc-600">{e.field}</Badge>
                      <Badge variant="outline" className="text-[10px] text-zinc-500 border-zinc-700">{e.evidence_type}</Badge>
                      <span className="text-[10px] text-zinc-500">by {e.detected_by}</span>
                      <span className="text-[10px] font-mono text-zinc-400 ml-auto">{e.confidence}/100</span>
                    </div>
                    <p className="text-sm text-zinc-300 break-words">{e.fragment}</p>
                    {e.source_url && <p className="text-[10px] text-zinc-600 mt-1 font-mono">{e.source_url}</p>}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Pages */}
          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2 pt-4 px-5">
              <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">
                Pages Visited ({result.visited_pages?.length || 0})
              </CardTitle>
            </CardHeader>
            <CardContent className="px-5 pb-4 space-y-1">
              {result.visited_pages?.map((p, i) => (
                <p key={i} className="text-xs text-zinc-300 font-mono truncate">{p}</p>
              ))}
              {result.failed_pages?.length > 0 && (
                <>
                  <Separator className="my-2 bg-zinc-800" />
                  <p className="text-[10px] uppercase tracking-wider text-rose-400 mb-1">Failed</p>
                  {result.failed_pages.map((p, i) => (
                    <p key={i} className="text-xs text-zinc-500 font-mono">{p.url}</p>
                  ))}
                </>
              )}
            </CardContent>
          </Card>

          {/* Send Log */}
          {sendLog.length > 0 && (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium flex items-center gap-2">
                  <Send className="w-3 h-3" /> Send History ({sendLog.length})
                </CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4 space-y-2">
                {sendLog.map((log, i) => (
                  <div key={i} className="flex items-center gap-3 p-2 rounded bg-zinc-800/50 border border-zinc-700/50">
                    {log.callback_status === 'sent'
                      ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      : <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />}
                    <Badge variant="outline" className="text-[10px] text-zinc-300 border-zinc-600">{log.destination}</Badge>
                    <span className="text-xs text-zinc-400 flex-1">{log.environment}</span>
                    <span className="text-[10px] text-zinc-500 font-mono">{log.sent_at?.substring(0, 19)}</span>
                    <span className="text-[10px] text-zinc-500">{log.sent_by}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right: Screenshot */}
        <div className="lg:col-span-2">
          <div className="sticky top-0 space-y-4">
            <Card className="bg-zinc-900 border-zinc-800 overflow-hidden">
              <div className="flex items-center gap-1.5 px-3 py-2 bg-zinc-800 border-b border-zinc-700">
                <div className="w-2.5 h-2.5 rounded-full bg-zinc-600" />
                <div className="w-2.5 h-2.5 rounded-full bg-zinc-600" />
                <div className="w-2.5 h-2.5 rounded-full bg-zinc-600" />
                <span className="text-[10px] text-zinc-500 ml-2 truncate font-mono">{result.input_url}</span>
              </div>
              {screenshotUrl ? (
                <img src={screenshotUrl} alt="Screenshot"
                  className="w-full" data-testid="detail-screenshot"
                  onError={(e) => { e.target.style.display = 'none'; }} />
              ) : (
                <div className="h-48 flex items-center justify-center text-zinc-600 text-sm">
                  No screenshot
                </div>
              )}
            </Card>

            {/* Metadata */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardContent className="p-4 space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-zinc-500">Status</span>
                  <span className="text-zinc-300">{result.status}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Review</span>
                  <span className="text-zinc-300">{result.review_status?.replace('_', ' ')}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Created</span>
                  <span className="text-zinc-300 font-mono">
                    {new Date(result.created_at).toLocaleDateString()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Job ID</span>
                  <span className="text-zinc-400 font-mono text-[10px]">{result.job_id}</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
