import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle
} from '@/components/ui/dialog';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from 'recharts';
import {
  GitMerge, Scissors, ExternalLink, Filter, ArrowRight,
  Building, MapPin, Calendar, FileText, ChevronLeft, ChevronRight
} from 'lucide-react';
import { toast } from 'sonner';

const SUBTYPE_META = {
  merger: { label: 'Merger', icon: GitMerge, color: 'bg-blue-500/10 text-blue-400 border-blue-500/20', chartColor: '#3b82f6' },
  absorption: { label: 'Absorption', icon: GitMerge, color: 'bg-blue-500/10 text-blue-400 border-blue-500/20', chartColor: '#6366f1' },
  spin_off: { label: 'Spin-off', icon: Scissors, color: 'bg-amber-500/10 text-amber-400 border-amber-500/20', chartColor: '#f59e0b' },
};

export default function MAPage() {
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [analytics, setAnalytics] = useState(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState(null);

  // Filters
  const [filterSubtype, setFilterSubtype] = useState('all');
  const [filterProvince, setFilterProvince] = useState('');
  const [filterCompany, setFilterCompany] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');
  const limit = 50;

  const fetchMA = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit, offset };
      if (filterSubtype !== 'all') params.subtype = filterSubtype;
      if (filterProvince) params.province = filterProvince;
      if (filterCompany) params.company_name = filterCompany;
      if (filterDateFrom) params.date_from = filterDateFrom;
      if (filterDateTo) params.date_to = filterDateTo;

      const res = await api.get('/borme/ma', { params });
      setEvents(res.data.events || []);
      setTotal(res.data.total || 0);
      setAnalytics(res.data.analytics || null);
    } catch (_) {
      toast.error('Failed to load M&A data');
    } finally {
      setLoading(false);
    }
  }, [offset, filterSubtype, filterProvince, filterCompany, filterDateFrom, filterDateTo]);

  useEffect(() => { fetchMA(); }, [fetchMA]);

  const subtypeDist = analytics?.by_subtype || {};
  const provinceDist = analytics?.by_province || {};
  const dateDist = analytics?.by_date || [];
  const totalMergers = subtypeDist.merger || 0;
  const totalSpinoffs = subtypeDist.spin_off || 0;

  const provinceChartData = Object.entries(provinceDist)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([name, count]) => ({ name: name.length > 12 ? name.substring(0, 12) + '..' : name, count }));

  const dateChartData = [...dateDist].reverse().slice(-15);

  const pages = Math.ceil(total / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <div className="space-y-5" data-testid="ma-page">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">BORME Monitor</h1>
        <p className="text-sm text-zinc-400 mt-0.5">Mergers, spin-offs and corporate restructuring from BORME</p>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-md bg-blue-600/15 flex items-center justify-center">
              <GitMerge className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p className="text-2xl font-bold font-mono text-zinc-50">{total}</p>
              <p className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">Total M&A Events</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-md bg-blue-500/10 flex items-center justify-center">
              <GitMerge className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p className="text-2xl font-bold font-mono text-blue-400">{totalMergers}</p>
              <p className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">Mergers</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-md bg-amber-500/10 flex items-center justify-center">
              <Scissors className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <p className="text-2xl font-bold font-mono text-amber-400">{totalSpinoffs}</p>
              <p className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">Spin-offs</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-md bg-emerald-500/10 flex items-center justify-center">
              <MapPin className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <p className="text-2xl font-bold font-mono text-emerald-400">{Object.keys(provinceDist).length}</p>
              <p className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">Provinces</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* By province */}
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">By Province</CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-4">
            {provinceChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={provinceChartData} layout="vertical" margin={{ left: 4, right: 16 }}>
                  <XAxis type="number" tick={{ fill: '#71717a', fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" width={90} tick={{ fill: '#a1a1aa', fontSize: 10 }} />
                  <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 6, color: '#fafafa', fontSize: 12 }} />
                  <Bar dataKey="count" radius={[0, 3, 3, 0]}>
                    {provinceChartData.map((_, i) => <Cell key={i} fill={i === 0 ? '#3b82f6' : i === 1 ? '#6366f1' : '#71717a'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <p className="text-sm text-zinc-600 text-center py-8">No data</p>}
          </CardContent>
        </Card>

        {/* Timeline */}
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Daily Activity</CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-4">
            {dateChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={dateChartData} margin={{ left: 0, right: 0 }}>
                  <XAxis dataKey="date" tick={{ fill: '#71717a', fontSize: 9 }} tickFormatter={d => d.substring(6)} />
                  <YAxis tick={{ fill: '#71717a', fontSize: 10 }} width={30} />
                  <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 6, color: '#fafafa', fontSize: 12 }}
                    labelFormatter={l => `Date: ${l}`} />
                  <Bar dataKey="count" fill="#3b82f6" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <p className="text-sm text-zinc-600 text-center py-8">No data</p>}
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardContent className="p-4">
          <div className="flex gap-2 items-end flex-wrap">
            <div className="space-y-1 flex-1 min-w-[150px]">
              <Label className="text-zinc-500 text-[10px]">Company</Label>
              <Input value={filterCompany} onChange={e => { setFilterCompany(e.target.value); setOffset(0); }}
                placeholder="Search company..." className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs" />
            </div>
            <div className="space-y-1 w-32">
              <Label className="text-zinc-500 text-[10px]">Type</Label>
              <Select value={filterSubtype} onValueChange={v => { setFilterSubtype(v); setOffset(0); }}>
                <SelectTrigger className="bg-zinc-950 border-zinc-700 text-zinc-200 h-8 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-700">
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="merger">Mergers</SelectItem>
                  <SelectItem value="spin_off">Spin-offs</SelectItem>
                  <SelectItem value="absorption">Absorptions</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 w-28">
              <Label className="text-zinc-500 text-[10px]">Province</Label>
              <Input value={filterProvince} onChange={e => { setFilterProvince(e.target.value); setOffset(0); }}
                placeholder="Madrid" className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs" />
            </div>
            <div className="space-y-1 w-28">
              <Label className="text-zinc-500 text-[10px]">From</Label>
              <Input value={filterDateFrom} onChange={e => { setFilterDateFrom(e.target.value); setOffset(0); }}
                placeholder="YYYYMMDD" className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs font-mono" />
            </div>
            <div className="space-y-1 w-28">
              <Label className="text-zinc-500 text-[10px]">To</Label>
              <Input value={filterDateTo} onChange={e => { setFilterDateTo(e.target.value); setOffset(0); }}
                placeholder="YYYYMMDD" className="bg-zinc-950 border-zinc-700 text-zinc-50 h-8 text-xs font-mono" />
            </div>
            <Button size="sm" onClick={() => { setOffset(0); fetchMA(); }} className="bg-zinc-800 text-zinc-300 h-8">
              <Filter className="w-3 h-3" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Events table */}
      <div className="rounded border border-zinc-800 overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900">
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2 w-24">Date</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2 w-24">Type</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2">Company</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2 w-40">Sector CNAE</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2 w-28">Province</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2 w-16">PDF</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500 py-2 w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {events.length === 0 && !loading && (
              <TableRow><TableCell colSpan={7} className="text-center text-zinc-500 py-12">No M&A events found</TableCell></TableRow>
            )}
            {events.map((e, i) => {
              const meta = SUBTYPE_META[e.event_subtype] || SUBTYPE_META.merger;
              const Icon = meta.icon;
              const sectorBadge = e.sector_status === 'verified'
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                : e.sector_status === 'inferred'
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                : 'bg-zinc-700/30 text-zinc-500 border-zinc-600/20';
              return (
                <TableRow key={e.idempotency_key || `ma-${i}`} className="border-zinc-800 hover:bg-zinc-800/20 transition-colors">
                  <TableCell className="py-2">
                    <span className="text-xs font-mono text-zinc-300">{e.publication_date}</span>
                  </TableCell>
                  <TableCell className="py-2">
                    <Badge className={`text-[9px] border ${meta.color}`}>
                      <Icon className="w-2.5 h-2.5 mr-1" />{meta.label}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-2">
                    <p className="text-xs text-zinc-100 font-medium truncate max-w-[250px]">{e.company_name_raw}</p>
                  </TableCell>
                  <TableCell className="py-2">
                    {e.cnae_code ? (
                      <div title={`Source: ${e.sector_source || '?'}\nConfidence: ${e.sector_confidence ? (e.sector_confidence * 100).toFixed(0) + '%' : '?'}\nEvidence: ${(e.sector_evidence_text || '').substring(0, 100)}`}>
                        <span className="text-[10px] text-zinc-200">{e.cnae_title?.substring(0, 25) || e.cnae_code}</span>
                        <div className="flex items-center gap-1 mt-0.5">
                          <span className="text-[9px] font-mono text-zinc-500">{e.cnae_code}</span>
                          <Badge className={`text-[8px] border px-1 py-0 ${sectorBadge}`}>
                            {e.sector_status === 'verified' ? 'V' : e.sector_status === 'inferred' ? 'I' : '?'}
                          </Badge>
                        </div>
                      </div>
                    ) : (
                      <span className="text-[10px] text-zinc-600">—</span>
                    )}
                  </TableCell>
                  <TableCell className="py-2">
                    <span className="text-[11px] text-zinc-400">{e.registry_province}</span>
                  </TableCell>
                  <TableCell className="py-2">
                    {e.pdf_url ? (
                      <a href={e.pdf_url} target="_blank" rel="noopener noreferrer"
                        className="text-blue-400 hover:text-blue-300 text-[10px] flex items-center gap-1">
                        <FileText className="w-3 h-3" /> PDF
                      </a>
                    ) : <span className="text-zinc-600 text-[10px]">—</span>}
                  </TableCell>
                  <TableCell className="py-2">
                    <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-zinc-500 hover:text-zinc-200"
                      onClick={() => setSelectedEvent(e)}>
                      <ArrowRight className="w-3 h-3" />
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-zinc-500">Page {currentPage} of {pages} ({total} events)</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={offset === 0}
              onClick={() => setOffset(o => Math.max(0, o - limit))}
              className="border-zinc-700 text-zinc-300 h-7 text-xs">
              <ChevronLeft className="w-3.5 h-3.5" />
            </Button>
            <Button variant="outline" size="sm" disabled={offset + limit >= total}
              onClick={() => setOffset(o => o + limit)}
              className="border-zinc-700 text-zinc-300 h-7 text-xs">
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* Event detail dialog */}
      <Dialog open={!!selectedEvent} onOpenChange={(o) => { if (!o) setSelectedEvent(null); }}>
        <DialogContent className="bg-zinc-900 border-zinc-700 max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-zinc-50 font-heading text-lg">{selectedEvent?.company_name_raw}</DialogTitle>
          </DialogHeader>
          {selectedEvent && (
            <div className="space-y-4 pt-2">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500">Event Type</p>
                  <Badge className={`${SUBTYPE_META[selectedEvent.event_subtype]?.color || 'bg-zinc-700 text-zinc-300'}`}>
                    {selectedEvent.event_subtype}
                  </Badge>
                </div>
                <div className="space-y-1">
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500">Publication Date</p>
                  <p className="text-sm text-zinc-200 font-mono">{selectedEvent.publication_date}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500">Province</p>
                  <p className="text-sm text-zinc-200">{selectedEvent.registry_province}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500">BORME Reference</p>
                  <p className="text-sm text-zinc-200 font-mono">{selectedEvent.official_identifier}</p>
                </div>
              </div>

              {/* Sector CNAE */}
              {selectedEvent.cnae_code && (
                <>
                  <Separator className="bg-zinc-800" />
                  <div className="grid grid-cols-3 gap-3">
                    <div className="space-y-1">
                      <p className="text-[10px] uppercase tracking-wider text-zinc-500">Sector CNAE</p>
                      <p className="text-sm text-zinc-200">{selectedEvent.cnae_title}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-[10px] uppercase tracking-wider text-zinc-500">Code</p>
                      <p className="text-sm text-zinc-200 font-mono">{selectedEvent.cnae_code}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-[10px] uppercase tracking-wider text-zinc-500">Status</p>
                      <Badge className={selectedEvent.sector_status === 'verified' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'}>
                        {selectedEvent.sector_status === 'verified' ? 'Verified' : 'Inferred'}
                        {selectedEvent.sector_confidence && ` (${(selectedEvent.sector_confidence * 100).toFixed(0)}%)`}
                      </Badge>
                    </div>
                  </div>
                  {selectedEvent.sector_evidence_text && (
                    <div className="space-y-1">
                      <p className="text-[10px] uppercase tracking-wider text-zinc-500">Evidence</p>
                      <p className="text-[10px] text-zinc-400 bg-zinc-800/30 p-2 rounded">{selectedEvent.sector_evidence_text.substring(0, 200)}</p>
                    </div>
                  )}
                </>
              )}
              <Separator className="bg-zinc-800" />
              <div className="space-y-1">
                <p className="text-[10px] uppercase tracking-wider text-zinc-500">Event Excerpt</p>
                <p className="text-xs text-zinc-300 leading-relaxed bg-zinc-800/50 p-3 rounded border border-zinc-700/50 max-h-[200px] overflow-y-auto">
                  {selectedEvent.event_text_excerpt || selectedEvent.event_text_raw?.substring(0, 500) || 'No text available'}
                </p>
              </div>
              {selectedEvent.pdf_url && (
                <a href={selectedEvent.pdf_url} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 text-sm text-blue-400 hover:text-blue-300">
                  <ExternalLink className="w-3.5 h-3.5" /> View official BORME PDF
                </a>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
