import { useState, useEffect, useRef } from 'react';
import { scrapeAPI, jobsAPI, resultsAPI, getScreenshotUrl } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Search, Globe, Loader2, CheckCircle, XCircle, ExternalLink,
  User, Phone, Mail, MapPin, Award, Users, Tag
} from 'lucide-react';

const STATUS_STYLES = {
  pending: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  processing: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  completed: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  error: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
};

const PHASE_LABELS = {
  scraping: 'Scraping website...',
  storage: 'Uploading screenshot...',
  parsing: 'Extracting data...',
  llm: 'Classifying with AI...',
  validation: 'Validating output...',
  persistence: 'Saving results...',
};

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

export default function AnalysisPage() {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [job, setJob] = useState(null);
  const [result, setResult] = useState(null);
  const [screenshotUrl, setScreenshotUrl] = useState(null);
  const pollRef = useRef(null);

  // Poll for job status
  useEffect(() => {
    if (!jobId) return;

    const poll = async () => {
      try {
        const res = await jobsAPI.get(jobId);
        setJob(res.data);

        if (res.data.status === 'completed' && res.data.result_id) {
          clearInterval(pollRef.current);
          const resultRes = await resultsAPI.get(res.data.result_id);
          setResult(resultRes.data);
          if (resultRes.data.screenshot_path) {
            setScreenshotUrl(getScreenshotUrl(resultRes.data.screenshot_path));
          }
          setLoading(false);
        } else if (res.data.status === 'error') {
          clearInterval(pollRef.current);
          setLoading(false);
        }
      } catch (err) {
        
      }
    };

    poll();
    pollRef.current = setInterval(poll, 2000);
    return () => clearInterval(pollRef.current);
  }, [jobId]);

  const handleAnalyze = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setJob(null);
    setResult(null);
    setScreenshotUrl(null);
    try {
      const res = await scrapeAPI.individual(url.trim());
      setJobId(res.data.job_id);
    } catch (err) {
      setLoading(false);
      setJob({ status: 'error', error_message: err.response?.data?.detail || 'Failed to start analysis' });
    }
  };

  const progressValue = job?.phase
    ? ({ scraping: 15, storage: 30, parsing: 45, llm: 65, validation: 85, persistence: 95 }[job.phase] || 10)
    : 0;

  return (
    <div className="space-y-6" data-testid="analysis-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">Individual Analysis</h1>
        <p className="text-sm text-zinc-400 mt-1">Analyze a single agency website</p>
      </div>

      {/* URL Input */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardContent className="p-5">
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <Input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
                placeholder="https://agency-website.com"
                data-testid="analysis-url-input"
                className="pl-10 bg-zinc-950 border-zinc-700 text-zinc-50 placeholder:text-zinc-600 focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <Button
              onClick={handleAnalyze}
              disabled={loading || !url.trim()}
              data-testid="analyze-btn"
              className="bg-blue-600 hover:bg-blue-500 text-white px-6"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              <span className="ml-2">{loading ? 'Analyzing...' : 'Analyze'}</span>
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Progress */}
      {job && job.status === 'processing' && (
        <Card className="bg-zinc-900 border-zinc-800 animate-fade-up" data-testid="analysis-progress">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-blue-400 font-medium">
                {PHASE_LABELS[job.phase] || 'Processing...'}
              </span>
              <Badge className="bg-blue-500/10 text-blue-400 border border-blue-500/20">
                <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                Processing
              </Badge>
            </div>
            <Progress value={progressValue} className="h-1 bg-zinc-800" />
          </CardContent>
        </Card>
      )}

      {/* Error */}
      {job && job.status === 'error' && (
        <Card className="bg-zinc-900 border-rose-500/30 animate-fade-up" data-testid="analysis-error">
          <CardContent className="p-5">
            <div className="flex items-center gap-2 text-rose-400">
              <XCircle className="w-4 h-4" />
              <span className="text-sm font-medium">Analysis Failed</span>
            </div>
            <p className="text-sm text-zinc-400 mt-2">{job.error_message || 'Unknown error'}</p>
          </CardContent>
        </Card>
      )}

      {/* Result */}
      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 animate-fade-up" data-testid="analysis-result">
          {/* Left: Data */}
          <div className="lg:col-span-3 space-y-4">
            {/* Header */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardContent className="p-5">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-4">
                    {result.logo_url && (
                      <div className="w-14 h-14 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center overflow-hidden shrink-0">
                        <img src={result.logo_url} alt="Logo" className="w-full h-full object-contain p-1"
                          onError={(e) => { e.target.parentElement.style.display = 'none'; }} />
                      </div>
                    )}
                    <div>
                      <h2 className="text-xl font-bold text-zinc-50 font-heading">
                        {result.company_name || 'Unknown Agency'}
                      </h2>
                      <a href={result.input_url} target="_blank" rel="noopener noreferrer"
                        className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1 mt-1">
                        {result.input_url}
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-3xl font-bold font-mono text-zinc-50">{result.confidence_overall}</span>
                    <span className="text-xs text-zinc-500 uppercase tracking-wider">Score</span>
                  </div>
                </div>
                {result.description && (
                  <p className="text-sm text-zinc-300 mt-3 leading-relaxed">{result.description}</p>
                )}
                <div className="flex flex-wrap gap-2 mt-3">
                  {result.category && (
                    <Badge className="bg-blue-500/10 text-blue-400 border border-blue-500/20">{result.category}</Badge>
                  )}
                  {result.subcategory && (
                    <Badge className="bg-zinc-700/50 text-zinc-300 border border-zinc-600/30">{result.subcategory}</Badge>
                  )}
                </div>
              </CardContent>
            </Card>

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
                    {result.tags.map((tag, i) => (
                      <Badge key={i} variant="outline" className="text-zinc-300 border-zinc-700 text-xs">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Contact & Address */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card className="bg-zinc-900 border-zinc-800">
                <CardHeader className="pb-2 pt-4 px-5">
                  <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium flex items-center gap-2">
                    <User className="w-3 h-3" /> Contact
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-5 pb-4 space-y-2">
                  {result.main_contact_name && (
                    <div className="flex items-center gap-2 text-sm">
                      <User className="w-3.5 h-3.5 text-zinc-500" />
                      <span className="text-zinc-200">{result.main_contact_name}</span>
                      {result.main_contact_role && (
                        <span className="text-zinc-500">({result.main_contact_role})</span>
                      )}
                    </div>
                  )}
                  {result.main_contact_email && (
                    <div className="flex items-center gap-2 text-sm">
                      <Mail className="w-3.5 h-3.5 text-zinc-500" />
                      <span className="text-zinc-200">{result.main_contact_email}</span>
                    </div>
                  )}
                  {result.phone && (
                    <div className="flex items-center gap-2 text-sm">
                      <Phone className="w-3.5 h-3.5 text-zinc-500" />
                      <span className="text-zinc-200">{result.phone}</span>
                    </div>
                  )}
                  {!result.main_contact_name && !result.main_contact_email && !result.phone && (
                    <p className="text-sm text-zinc-600">No contact information found</p>
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
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
                  ) : (
                    <p className="text-sm text-zinc-600">No clients detected</p>
                  )}
                </CardContent>
              </Card>

              <Card className="bg-zinc-900 border-zinc-800">
                <CardHeader className="pb-2 pt-4 px-5">
                  <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium flex items-center gap-2">
                    <Award className="w-3 h-3" /> Awards
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-5 pb-4">
                  {result.has_awards ? (
                    <div className="space-y-1">
                      {result.awards_evidence?.map((a, i) => (
                        <p key={i} className="text-sm text-zinc-200">{a}</p>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-zinc-600">No awards detected</p>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Confidence Scores */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">
                  Confidence Scores
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
                  <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">
                    Evidence ({result.evidence.length})
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-5 pb-4">
                  <div className="space-y-2">
                    {result.evidence.map((e, i) => (
                      <div key={i} className="flex items-start gap-3 p-2 rounded bg-zinc-800/50 border border-zinc-700/50">
                        <Badge variant="outline" className="text-[10px] uppercase text-zinc-400 border-zinc-600 shrink-0 mt-0.5">
                          {e.field}
                        </Badge>
                        <div className="min-w-0">
                          <p className="text-sm text-zinc-200 break-words">{e.fragment}</p>
                          <div className="flex gap-3 mt-1">
                            <span className="text-[10px] text-zinc-500">{e.evidence_type}</span>
                            <span className="text-[10px] text-zinc-500">by {e.detected_by}</span>
                            <span className="text-[10px] text-zinc-500">confidence: {e.confidence}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Pages visited */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">
                  Pages Visited ({result.visited_pages?.length || 0})
                </CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4">
                <div className="space-y-1">
                  {result.visited_pages?.map((p, i) => (
                    <p key={i} className="text-xs text-zinc-300 font-mono truncate">{p}</p>
                  ))}
                </div>
                {result.failed_pages?.length > 0 && (
                  <>
                    <Separator className="my-2 bg-zinc-800" />
                    <p className="text-[10px] uppercase tracking-wider text-rose-400 mb-1">Failed Pages</p>
                    {result.failed_pages.map((p, i) => (
                      <p key={i} className="text-xs text-zinc-500 font-mono truncate">{p.url} — {p.reason}</p>
                    ))}
                  </>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Right: Screenshot */}
          <div className="lg:col-span-2">
            <div className="sticky top-0">
              <Card className="bg-zinc-900 border-zinc-800 overflow-hidden">
                {/* Browser bar */}
                <div className="flex items-center gap-1.5 px-3 py-2 bg-zinc-800 border-b border-zinc-700">
                  <div className="w-2.5 h-2.5 rounded-full bg-zinc-600" />
                  <div className="w-2.5 h-2.5 rounded-full bg-zinc-600" />
                  <div className="w-2.5 h-2.5 rounded-full bg-zinc-600" />
                  <span className="text-[10px] text-zinc-500 ml-2 truncate font-mono">{result.input_url}</span>
                </div>
                {screenshotUrl ? (
                  <img
                    src={screenshotUrl}
                    alt={`Screenshot of ${result.input_url}`}
                    className="w-full"
                    data-testid="analysis-screenshot"
                    onError={(e) => { e.target.style.display = 'none'; }}
                  />
                ) : (
                  <div className="h-48 flex items-center justify-center text-zinc-600 text-sm">
                    No screenshot available
                  </div>
                )}
              </Card>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
