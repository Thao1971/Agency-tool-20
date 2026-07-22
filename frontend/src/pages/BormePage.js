import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table';
import {
  Tabs, TabsContent, TabsList, TabsTrigger
} from '@/components/ui/tabs';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Activity, Download, Search, AlertTriangle, CheckCircle,
  Loader2, ExternalLink, Play, RefreshCw, FileText, Filter
} from 'lucide-react';
import { toast } from 'sonner';

const EVENT_TYPE_COLORS = {
  governance: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  corporate: 'bg-zinc-500/10 text-zinc-300 border-zinc-500/20',
  capital: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  dissolution: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
  ma: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  correction: 'bg-zinc-500/10 text-zinc-500 border-zinc-600/20',
  other: 'bg-zinc-700/30 text-zinc-500 border-zinc-600/20',
};

export default function BormePage() {
  const [tab, setTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [events, setEvents] = useState([]);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);

  // Filters
  const [filterDate, setFilterDate] = useState('');
  const [filterName, setFilterName] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [filterProvince, setFilterProvince] = useState('');
  const [eventsOffset, setEventsOffset] = useState(0);

  // Fetch day form
  const [fetchDate, setFetchDate] = useState('');
  const [fetchFrom, setFetchFrom] = useState('');
  const [fetchTo, setFetchTo] = useState('');

  // Enrich form
  const [enrichName, setEnrichName] = useState('');
  const [enrichCif, setEnrichCif] = useState('');
  const [enrichProvince, setEnrichProvince] = useState('');
  const [enrichFrom, setEnrichFrom] = useState('');
  const [enrichTo, setEnrichTo] = useState('');
  const [enrichResults, setEnrichResults] = useState(null);

  const fetchStats = useCallback(async () => {
    try {
      const res = await api.get('/borme/stats');
      setStats(res.data);
    } catch (err) { if (process.env.NODE_ENV === 'development') console.error('BORME stats fetch error:', err); }
    finally { setLoading(false); }
  }, []);

  const fetchEvents = useCallback(async () => {
    const params = { limit: 50, offset: eventsOffset };
    if (filterDate) params.date = filterDate;
    if (filterName) params.company_name = filterName;
    if (filterType && filterType !== 'all') params.event_type = filterType;
    if (filterProvince) params.province = filterProvince;
    try {
      const res = await api.get('/borme/events', { params });
      setEvents(res.data.events || []);
      setEventsTotal(res.data.total || 0);
    } catch (err) { if (process.env.NODE_ENV === 'development') console.error('BORME events fetch error:', err); }
  }, [eventsOffset, filterDate, filterName, filterType, filterProvince]);

  useEffect(() => { fetchStats(); }, [fetchStats]);
  useEffect(() => { if (tab === 'events') fetchEvents(); }, [tab, fetchEvents]);

  const handleAction = async (action, body, label) => {
    setActionLoading(action);
    try {
      const res = await api.post(`/borme/${action}`, body);
      toast.success(`${label}: ${JSON.stringify(res.data).substring(0, 100)}`);
      fetchStats();
    } catch (err) {
      toast.error(`${label} failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleEnrich = async () => {
    if (!enrichName && !enrichCif) { toast.error('Name or CIF required'); return; }
    setActionLoading('enrich');
    try {
      const res = await api.post('/borme/enrich-company', {
        company_name: enrichName || undefined,
        cif: enrichCif || undefined,
        province: enrichProvince || undefined,
        date_from: enrichFrom || undefined,
        date_to: enrichTo || undefined,
      });
      setEnrichResults(res.data);
      toast.success(`Found ${res.data.matches?.length || 0} matches`);
    } catch (err) {
      toast.error(`Enrich failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const typeDist = stats?.event_type_distribution || {};
  const totalEvents = stats?.total_events_extracted || 0;

  return (
    <div className="space-y-6" data-testid="borme-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">BORME Operations</h1>
        <p className="text-sm text-zinc-400 mt-1">Corporate events ingestion, parsing and enrichment</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="overview" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400">
            <Activity className="w-3.5 h-3.5 mr-1.5" /> Overview
          </TabsTrigger>
          <TabsTrigger value="actions" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400">
            <Play className="w-3.5 h-3.5 mr-1.5" /> Actions
          </TabsTrigger>
          <TabsTrigger value="events" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400">
            <FileText className="w-3.5 h-3.5 mr-1.5" /> Events
          </TabsTrigger>
          <TabsTrigger value="enrich" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-50 text-zinc-400">
            <Search className="w-3.5 h-3.5 mr-1.5" /> Enrich Test
          </TabsTrigger>
        </TabsList>

        {/* OVERVIEW TAB */}
        <TabsContent value="overview">
          <div className="space-y-4">
            {/* KPI row */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
              {[
                { label: 'Days Fetched', value: stats?.total_days_fetched || 0, color: 'text-blue-400' },
                { label: 'PDFs Processed', value: stats?.total_pdfs_processed || 0, color: 'text-emerald-400' },
                { label: 'PDFs Failed', value: stats?.total_pdfs_failed || 0, color: stats?.total_pdfs_failed > 0 ? 'text-rose-400' : 'text-zinc-400' },
                { label: 'Success Rate', value: `${stats?.pdf_success_rate || 0}%`, color: 'text-emerald-400' },
                { label: 'Total Events', value: (totalEvents || 0).toLocaleString(), color: 'text-blue-400' },
              ].map(kpi => (
                <Card key={kpi.label} className="bg-zinc-900 border-zinc-800">
                  <CardContent className="p-4">
                    <p className="text-[10px] uppercase tracking-[0.1em] text-zinc-500 font-medium">{kpi.label}</p>
                    <p className={`text-2xl font-bold font-mono mt-1 ${kpi.color}`}>{kpi.value}</p>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Event type distribution */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Event Type Distribution</CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4">
                <div className="space-y-2">
                  {Object.entries(typeDist).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
                    <div key={type} className="flex items-center gap-3">
                      <Badge className={`text-xs border w-28 justify-center ${EVENT_TYPE_COLORS[type] || EVENT_TYPE_COLORS.other}`}>{type}</Badge>
                      <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                        <div className="h-full rounded-full bg-blue-500" style={{ width: `${(count / Math.max(totalEvents, 1)) * 100}%` }} />
                      </div>
                      <span className="text-xs font-mono text-zinc-300 w-16 text-right">{count.toLocaleString()}</span>
                      <span className="text-[10px] text-zinc-500 w-12 text-right">{((count / Math.max(totalEvents, 1)) * 100).toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Errors */}
            {stats?.errors_by_type && Object.keys(stats.errors_by_type).length > 0 && (
              <Card className="bg-zinc-900 border-zinc-800 border-rose-500/20">
                <CardHeader className="pb-2 pt-4 px-5">
                  <CardTitle className="text-xs uppercase tracking-[0.1em] text-rose-400 font-medium flex items-center gap-2">
                    <AlertTriangle className="w-3 h-3" /> Processing Errors
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-5 pb-4">
                  {Object.entries(stats.errors_by_type).map(([type, count]) => (
                    <div key={type} className="flex justify-between py-1">
                      <span className="text-xs text-zinc-400">{type}</span>
                      <span className="text-xs font-mono text-rose-400">{count}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* CNAE Sector Coverage */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">CNAE Sector Coverage</CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4">
                {stats?.sector_coverage ? (
                  <div className="space-y-3">
                    <div className="flex justify-between text-xs">
                      <span className="text-zinc-400">Coverage rate</span>
                      <span className="font-mono text-zinc-200 font-bold">{stats.sector_coverage.coverage_rate}%</span>
                    </div>
                    <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{
                        width: `${stats.sector_coverage.coverage_rate}%`,
                        background: `linear-gradient(90deg, #10b981 0%, #10b981 ${stats.sector_coverage.verified / Math.max(totalEvents,1) * 100}%, #f59e0b ${stats.sector_coverage.verified / Math.max(totalEvents,1) * 100}%, #f59e0b 100%)`
                      }} />
                    </div>
                    <div className="grid grid-cols-4 gap-2 text-center">
                      <div><p className="text-lg font-bold font-mono text-emerald-400">{stats.sector_coverage.verified}</p><p className="text-[9px] text-zinc-500">Verified</p></div>
                      <div><p className="text-lg font-bold font-mono text-amber-400">{stats.sector_coverage.inferred}</p><p className="text-[9px] text-zinc-500">Inferred</p></div>
                      <div><p className="text-lg font-bold font-mono text-zinc-500">{stats.sector_coverage.unavailable}</p><p className="text-[9px] text-zinc-500">Unavailable</p></div>
                      <div><p className="text-lg font-bold font-mono text-zinc-600">{stats.sector_coverage.unclassified}</p><p className="text-[9px] text-zinc-500">Pending</p></div>
                    </div>
                  </div>
                ) : <p className="text-sm text-zinc-600 text-center py-4">No sector data yet</p>}
              </CardContent>
            </Card>

            {/* Top CNAE divisions */}
            {stats?.top_cnae_divisions?.length > 0 && (
              <Card className="bg-zinc-900 border-zinc-800">
                <CardHeader className="pb-2 pt-4 px-5">
                  <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Top CNAE Divisions</CardTitle>
                </CardHeader>
                <CardContent className="px-5 pb-4 space-y-1.5">
                  {stats.top_cnae_divisions.map((d, i) => (
                    <div key={d.division || i} className="flex items-center gap-2">
                      <span className="text-xs font-mono text-zinc-400 w-8">{d.division}</span>
                      <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div className="h-full rounded-full bg-blue-500" style={{width: `${(d.count / Math.max(stats.top_cnae_divisions[0]?.count,1)) * 100}%`}} />
                      </div>
                      <span className="text-[10px] text-zinc-300 w-24 truncate text-right">{d.title}</span>
                      <span className="text-xs font-mono text-zinc-300 w-10 text-right">{d.count}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        {/* ACTIONS TAB */}
        <TabsContent value="actions">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Fetch Day */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Fetch Day</CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4 space-y-3">
                <div className="space-y-1">
                  <Label className="text-zinc-400 text-xs">Date (YYYYMMDD)</Label>
                  <Input value={fetchDate} onChange={e => setFetchDate(e.target.value)}
                    placeholder="20260414" className="bg-zinc-950 border-zinc-700 text-zinc-50 font-mono" />
                </div>
                <Button size="sm" onClick={() => handleAction('fetch-day', { date: fetchDate }, 'Fetch day')}
                  disabled={!fetchDate || actionLoading === 'fetch-day'}
                  className="bg-blue-600 hover:bg-blue-500 text-white w-full" data-testid="btn-fetch-day">
                  {actionLoading === 'fetch-day' ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Download className="w-3.5 h-3.5 mr-1.5" />}
                  Fetch Day
                </Button>
              </CardContent>
            </Card>

            {/* Fetch Range */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Fetch Range</CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4 space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <Label className="text-zinc-400 text-xs">From</Label>
                    <Input value={fetchFrom} onChange={e => setFetchFrom(e.target.value)}
                      placeholder="20260101" className="bg-zinc-950 border-zinc-700 text-zinc-50 font-mono" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-zinc-400 text-xs">To</Label>
                    <Input value={fetchTo} onChange={e => setFetchTo(e.target.value)}
                      placeholder="20260414" className="bg-zinc-950 border-zinc-700 text-zinc-50 font-mono" />
                  </div>
                </div>
                <Button size="sm" onClick={() => handleAction('fetch-range', { date_from: fetchFrom, date_to: fetchTo }, 'Fetch range')}
                  disabled={!fetchFrom || !fetchTo || actionLoading === 'fetch-range'}
                  className="bg-blue-600 hover:bg-blue-500 text-white w-full">
                  {actionLoading === 'fetch-range' ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Download className="w-3.5 h-3.5 mr-1.5" />}
                  Fetch Range
                </Button>
              </CardContent>
            </Card>

            {/* Reprocess Failures */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Reprocess Failures</CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4">
                <Button size="sm" variant="outline" onClick={() => handleAction('reprocess-failures', {}, 'Reprocess')}
                  disabled={actionLoading === 'reprocess-failures'}
                  className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 w-full">
                  {actionLoading === 'reprocess-failures' ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 mr-1.5" />}
                  Retry Failed PDFs
                </Button>
              </CardContent>
            </Card>

            {/* Classify Historical */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">CNAE Classification</CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4 space-y-2">
                <p className="text-[10px] text-zinc-500">Apply CNAE-2025 sector classification to historical events without sector data.</p>
                <Button size="sm" onClick={() => handleAction('classify-historical?limit_events=10000', {}, 'Classify historical')}
                  disabled={actionLoading === 'classify-historical?limit_events=10000'}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white w-full" data-testid="btn-classify">
                  {actionLoading === 'classify-historical?limit_events=10000' ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5 mr-1.5" />}
                  Classify All Pending Events
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* EVENTS TAB */}
        <TabsContent value="events">
          <Card className="bg-zinc-900 border-zinc-800 mb-4">
            <CardContent className="p-4">
              <div className="flex gap-2 items-end">
                <div className="space-y-1 flex-1">
                  <Label className="text-zinc-500 text-[10px]">Company</Label>
                  <Input value={filterName} onChange={e => { setFilterName(e.target.value); setEventsOffset(0); }}
                    placeholder="Company name..." className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs" />
                </div>
                <div className="space-y-1 w-28">
                  <Label className="text-zinc-500 text-[10px]">Date</Label>
                  <Input value={filterDate} onChange={e => { setFilterDate(e.target.value); setEventsOffset(0); }}
                    placeholder="YYYYMMDD" className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs font-mono" />
                </div>
                <div className="space-y-1 w-32">
                  <Label className="text-zinc-500 text-[10px]">Type</Label>
                  <Select value={filterType} onValueChange={v => { setFilterType(v); setEventsOffset(0); }}>
                    <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-700">
                      <SelectItem value="all">All types</SelectItem>
                      {['governance', 'corporate', 'capital', 'dissolution', 'ma', 'correction', 'other'].map(t =>
                        <SelectItem key={t} value={t}>{t}</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1 w-28">
                  <Label className="text-zinc-500 text-[10px]">Province</Label>
                  <Input value={filterProvince} onChange={e => { setFilterProvince(e.target.value); setEventsOffset(0); }}
                    placeholder="Madrid..." className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs" />
                </div>
                <Button size="sm" onClick={fetchEvents} className="bg-zinc-800 text-zinc-300 h-8">
                  <Filter className="w-3 h-3" />
                </Button>
              </div>
            </CardContent>
          </Card>

          <p className="text-xs text-zinc-500 mb-2">{eventsTotal.toLocaleString()} events found</p>

          <div className="rounded border border-zinc-800 overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900">
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2">Date</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2">Company</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2">Type</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2">Subtype</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2">Province</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2 w-12">PDF</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.length === 0 && (
                  <TableRow><TableCell colSpan={6} className="text-center text-zinc-500 py-8">No events found</TableCell></TableRow>
                )}
                {events.map((e, i) => (
                  <TableRow key={e.id || i} className="border-zinc-800 hover:bg-zinc-800/20">
                    <TableCell className="text-xs font-mono text-zinc-400 py-1.5">{e.publication_date}</TableCell>
                    <TableCell className="text-xs text-zinc-200 py-1.5 max-w-[200px] truncate">{e.company_name_raw}</TableCell>
                    <TableCell className="py-1.5">
                      <Badge className={`text-[9px] border ${EVENT_TYPE_COLORS[e.event_type] || EVENT_TYPE_COLORS.other}`}>{e.event_type}</Badge>
                    </TableCell>
                    <TableCell className="text-[10px] text-zinc-400 py-1.5">{e.event_subtype}</TableCell>
                    <TableCell className="text-[10px] text-zinc-400 py-1.5">{e.registry_province}</TableCell>
                    <TableCell className="py-1.5">
                      {e.pdf_url && (
                        <a href={e.pdf_url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300">
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {eventsTotal > 50 && (
            <div className="flex justify-between items-center mt-2">
              <span className="text-xs text-zinc-500">{eventsOffset + 1}-{Math.min(eventsOffset + 50, eventsTotal)} of {eventsTotal}</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={eventsOffset === 0}
                  onClick={() => setEventsOffset(o => Math.max(0, o - 50))}
                  className="border-zinc-700 text-zinc-300 h-7 text-xs">Prev</Button>
                <Button variant="outline" size="sm" disabled={eventsOffset + 50 >= eventsTotal}
                  onClick={() => setEventsOffset(o => o + 50)}
                  className="border-zinc-700 text-zinc-300 h-7 text-xs">Next</Button>
              </div>
            </div>
          )}
        </TabsContent>

        {/* ENRICH TEST TAB */}
        <TabsContent value="enrich">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Enrich Company Test</CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4 space-y-3">
                <div className="space-y-1">
                  <Label className="text-zinc-400 text-xs">Company Name</Label>
                  <Input value={enrichName} onChange={e => setEnrichName(e.target.value)}
                    placeholder="Baker Tilly SLP" className="bg-zinc-950 border-zinc-700 text-zinc-50" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <Label className="text-zinc-400 text-xs">CIF (optional)</Label>
                    <Input value={enrichCif} onChange={e => setEnrichCif(e.target.value)}
                      placeholder="B12345678" className="bg-zinc-950 border-zinc-700 text-zinc-50" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-zinc-400 text-xs">Province (optional)</Label>
                    <Input value={enrichProvince} onChange={e => setEnrichProvince(e.target.value)}
                      placeholder="Madrid" className="bg-zinc-950 border-zinc-700 text-zinc-50" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <Label className="text-zinc-400 text-xs">Date from</Label>
                    <Input value={enrichFrom} onChange={e => setEnrichFrom(e.target.value)}
                      placeholder="20260101" className="bg-zinc-950 border-zinc-700 text-zinc-50 font-mono" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-zinc-400 text-xs">Date to</Label>
                    <Input value={enrichTo} onChange={e => setEnrichTo(e.target.value)}
                      placeholder="20260414" className="bg-zinc-950 border-zinc-700 text-zinc-50 font-mono" />
                  </div>
                </div>
                <Button onClick={handleEnrich} disabled={actionLoading === 'enrich'}
                  className="bg-blue-600 hover:bg-blue-500 text-white w-full" data-testid="btn-enrich-test">
                  {actionLoading === 'enrich' ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Search className="w-3.5 h-3.5 mr-1.5" />}
                  Search BORME Events
                </Button>
              </CardContent>
            </Card>

            {/* Enrich Results */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">
                  Results {enrichResults && `(${enrichResults.matches?.length || 0} matches, ${enrichResults.unmatched_candidates?.length || 0} candidates)`}
                </CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4">
                {!enrichResults ? (
                  <p className="text-sm text-zinc-600 text-center py-8">Run a search to see results</p>
                ) : (
                  <div className="space-y-2 max-h-[400px] overflow-y-auto">
                    {enrichResults.matches?.map((m, i) => (
                      <div key={i} className="p-2.5 rounded bg-zinc-800/50 border border-zinc-700/50">
                        <div className="flex items-center gap-2 mb-1">
                          <CheckCircle className="w-3 h-3 text-emerald-400 shrink-0" />
                          <span className="text-xs text-zinc-200 font-medium truncate">{m.company_name_raw}</span>
                          <Badge className={`text-[9px] border ml-auto ${EVENT_TYPE_COLORS[m.event_type] || EVENT_TYPE_COLORS.other}`}>{m.event_subtype}</Badge>
                        </div>
                        <div className="flex gap-3 text-[10px] text-zinc-500">
                          <span className="font-mono">{m.publication_date}</span>
                          <span>{m.match_method}</span>
                          <span className="font-mono font-bold text-zinc-300">{m.confidence_match?.toFixed(2)}</span>
                          <span>{m.registry_province}</span>
                          {m.pdf_url && <a href={m.pdf_url} target="_blank" rel="noopener noreferrer" className="text-blue-400"><ExternalLink className="w-2.5 h-2.5" /></a>}
                        </div>
                        <p className="text-[10px] text-zinc-500 mt-1 line-clamp-2">{m.event_text_excerpt?.substring(0, 150)}</p>
                      </div>
                    ))}
                    {enrichResults.unmatched_candidates?.length > 0 && (
                      <>
                        <Separator className="bg-zinc-800 my-2" />
                        <p className="text-[10px] uppercase tracking-wider text-amber-400">Weak candidates</p>
                        {enrichResults.unmatched_candidates.map((c, i) => (
                          <div key={i} className="p-2 rounded bg-zinc-800/30 border border-zinc-700/30">
                            <span className="text-xs text-zinc-400">{c.company_name_raw}</span>
                            <span className="text-[10px] text-zinc-500 ml-2">{c.match_method} ({c.confidence_match?.toFixed(2)})</span>
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
