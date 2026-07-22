import { useState, useEffect, useCallback } from 'react';
import { resultsAPI } from '@/lib/api';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table';
import { Search, Download, ChevronLeft, ChevronRight, ExternalLink, Eye } from 'lucide-react';

const STATUS_STYLES = {
  completed: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  error: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
  pending_review: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  reviewed: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  validated: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
};

export default function ResultsPage() {
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [reviewFilter, setReviewFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const limit = 20;

  const fetchResults = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit };
      if (search) params.search = search;
      if (statusFilter !== 'all') params.status = statusFilter;
      if (reviewFilter !== 'all') params.review_status = reviewFilter;
      const res = await resultsAPI.list(params);
      setResults(res.data.results);
      setTotal(res.data.total);
      setPages(res.data.pages);
    } catch (err) {
      
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter, reviewFilter]);

  useEffect(() => { fetchResults(); }, [fetchResults]);

  const handleExport = async (format) => {
    try {
      const res = await resultsAPI.exportData(format, {
        status: statusFilter !== 'all' ? statusFilter : undefined,
        review_status: reviewFilter !== 'all' ? reviewFilter : undefined,
      });
      if (format === 'json') {
        const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
        downloadBlob(blob, 'agency_results.json');
      } else {
        downloadBlob(res.data, `agency_results.${format === 'excel' ? 'xlsx' : 'csv'}`);
      }
    } catch (err) {
      
    }
  };

  const downloadBlob = (blob, filename) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6" data-testid="results-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">Results</h1>
          <p className="text-sm text-zinc-400 mt-1">{total} total results</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => handleExport('csv')}
            data-testid="export-csv-btn"
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100">
            <Download className="w-3.5 h-3.5 mr-1.5" /> CSV
          </Button>
          <Button variant="outline" size="sm" onClick={() => handleExport('excel')}
            data-testid="export-excel-btn"
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100">
            <Download className="w-3.5 h-3.5 mr-1.5" /> Excel
          </Button>
          <Button variant="outline" size="sm" onClick={() => handleExport('json')}
            data-testid="export-json-btn"
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100">
            <Download className="w-3.5 h-3.5 mr-1.5" /> JSON
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardContent className="p-4">
          <div className="flex gap-3 items-center">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <Input
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                placeholder="Search by name, URL or description..."
                data-testid="results-search-input"
                className="pl-10 bg-zinc-950 border-zinc-700 text-zinc-50 placeholder:text-zinc-600"
              />
            </div>
            <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1); }}>
              <SelectTrigger className="w-40 bg-zinc-950 border-zinc-700 text-zinc-300" data-testid="results-status-filter">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent className="bg-zinc-900 border-zinc-700">
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
                <SelectItem value="error">Error</SelectItem>
              </SelectContent>
            </Select>
            <Select value={reviewFilter} onValueChange={(v) => { setReviewFilter(v); setPage(1); }}>
              <SelectTrigger className="w-44 bg-zinc-950 border-zinc-700 text-zinc-300" data-testid="results-review-filter">
                <SelectValue placeholder="Review" />
              </SelectTrigger>
              <SelectContent className="bg-zinc-900 border-zinc-700">
                <SelectItem value="all">All Reviews</SelectItem>
                <SelectItem value="pending_review">Pending Review</SelectItem>
                <SelectItem value="reviewed">Reviewed</SelectItem>
                <SelectItem value="validated">Validated</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <div className="rounded border border-zinc-800 overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900">
              <TableHead className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Agency</TableHead>
              <TableHead className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Category</TableHead>
              <TableHead className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Score</TableHead>
              <TableHead className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">Review</TableHead>
              <TableHead className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium w-16">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.length === 0 && !loading && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-zinc-500 py-12">
                  No results found. Start by analyzing an agency.
                </TableCell>
              </TableRow>
            )}
            {results.map((r) => (
              <TableRow key={r.id} className="border-zinc-800 hover:bg-zinc-800/30 transition-colors cursor-pointer"
                onClick={() => navigate(`/results/${r.id}`)}
                data-testid={`result-row-${r.id}`}
              >
                <TableCell>
                  <div className="flex items-center gap-3">
                    {r.logo_url && (
                      <div className="w-8 h-8 rounded bg-zinc-800 border border-zinc-700 flex items-center justify-center overflow-hidden shrink-0">
                        <img src={r.logo_url} alt="" className="w-full h-full object-contain p-0.5"
                          onError={(e) => { e.target.parentElement.style.display = 'none'; }} />
                      </div>
                    )}
                    <div>
                      <p className="text-sm text-zinc-100 font-medium truncate max-w-[220px]">
                        {r.company_name || 'Unknown'}
                      </p>
                      <p className="text-xs text-zinc-500 truncate max-w-[220px]">{r.input_url}</p>
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  {r.category ? (
                    <Badge className="bg-blue-500/10 text-blue-400 border border-blue-500/20 text-xs truncate max-w-[180px]">
                      {r.category}
                    </Badge>
                  ) : (
                    <span className="text-xs text-zinc-600">—</span>
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-mono font-bold text-zinc-100">{r.confidence_overall}</span>
                    <div className="w-8 h-1 bg-zinc-800 rounded-full overflow-hidden">
                      <div className="h-full rounded-full"
                        style={{
                          width: `${r.confidence_overall}%`,
                          backgroundColor: r.confidence_overall > 80 ? '#10b981' : r.confidence_overall > 50 ? '#f59e0b' : '#ef4444'
                        }}
                      />
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge className={`text-xs border ${STATUS_STYLES[r.review_status] || STATUS_STYLES.pending_review}`}>
                    {r.review_status?.replace('_', ' ')}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="sm"
                    className="h-7 w-7 p-0 text-zinc-400 hover:text-zinc-100"
                    onClick={(e) => { e.stopPropagation(); navigate(`/results/${r.id}`); }}>
                    <Eye className="w-3.5 h-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-zinc-500">
            Page {page} of {pages} ({total} results)
          </p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" disabled={page >= pages}
              onClick={() => setPage(p => p + 1)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
