import { useState, useEffect, useCallback } from 'react';
import { resultsAPI } from '@/lib/api';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Search, Edit2, CheckCircle, Eye, ChevronLeft, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';

export default function ReviewPage() {
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [editResult, setEditResult] = useState(null);
  const [editData, setEditData] = useState({});
  const navigate = useNavigate();
  const limit = 20;

  const fetchResults = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit, review_status: 'pending_review' };
      if (search) params.search = search;
      const res = await resultsAPI.list(params);
      setResults(res.data.results);
      setTotal(res.data.total);
      setPages(res.data.pages);
    } catch (err) {
      
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => { fetchResults(); }, [fetchResults]);

  const openEdit = (result) => {
    setEditResult(result);
    setEditData({
      company_name: result.company_name || '',
      category: result.category || '',
      subcategory: result.subcategory || '',
      description: result.description || '',
      main_contact_email: result.main_contact_email || '',
      phone: result.phone || '',
    });
  };

  const handleSave = async () => {
    if (!editResult) return;
    try {
      const updates = {};
      Object.entries(editData).forEach(([k, v]) => {
        if (v !== (editResult[k] || '')) updates[k] = v || null;
      });
      if (Object.keys(updates).length > 0) {
        await resultsAPI.update(editResult.id, updates);
        toast.success('Result updated');
      }
      setEditResult(null);
      fetchResults();
    } catch (err) {
      toast.error('Failed to update');
    }
  };

  const handleValidate = async (id) => {
    try {
      await resultsAPI.validate(id);
      toast.success('Result validated');
      fetchResults();
    } catch (err) {
      toast.error('Validation failed');
    }
  };

  return (
    <div className="space-y-6" data-testid="review-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">Manual Review</h1>
        <p className="text-sm text-zinc-400 mt-1">{total} results pending review</p>
      </div>

      {/* Search */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardContent className="p-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              placeholder="Search pending reviews..."
              data-testid="review-search-input"
              className="pl-10 bg-zinc-950 border-zinc-700 text-zinc-50 placeholder:text-zinc-600" />
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
              <TableHead className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium w-36">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.length === 0 && !loading && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-zinc-500 py-12">
                  No results pending review
                </TableCell>
              </TableRow>
            )}
            {results.map((r) => (
              <TableRow key={r.id} className="border-zinc-800 hover:bg-zinc-800/30 transition-colors"
                data-testid={`review-row-${r.id}`}>
                <TableCell>
                  <p className="text-sm text-zinc-100 font-medium truncate max-w-[200px]">
                    {r.company_name || 'Unknown'}
                  </p>
                  <p className="text-xs text-zinc-500 truncate max-w-[200px]">{r.input_url}</p>
                </TableCell>
                <TableCell>
                  {r.category ? (
                    <Badge className="bg-blue-500/10 text-blue-400 border border-blue-500/20 text-xs">{r.category}</Badge>
                  ) : <span className="text-xs text-zinc-600">—</span>}
                </TableCell>
                <TableCell>
                  <span className="text-sm font-mono font-bold text-zinc-100">{r.confidence_overall}</span>
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-zinc-400 hover:text-zinc-100"
                      onClick={() => navigate(`/results/${r.id}`)} data-testid={`review-view-${r.id}`}>
                      <Eye className="w-3.5 h-3.5" />
                    </Button>
                    <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-zinc-400 hover:text-blue-400"
                      onClick={() => openEdit(r)} data-testid={`review-edit-${r.id}`}>
                      <Edit2 className="w-3.5 h-3.5" />
                    </Button>
                    <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-zinc-400 hover:text-emerald-400"
                      onClick={() => handleValidate(r.id)} data-testid={`review-validate-${r.id}`}>
                      <CheckCircle className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-zinc-500">Page {page} of {pages}</p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(p => p + 1)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Edit Dialog */}
      <Dialog open={!!editResult} onOpenChange={(open) => { if (!open) setEditResult(null); }}>
        <DialogContent className="bg-zinc-900 border-zinc-700 max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-zinc-50 font-heading">Edit Result</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 pt-2">
            <div className="space-y-1">
              <Label className="text-zinc-400 text-xs">Company Name</Label>
              <Input value={editData.company_name || ''} onChange={(e) => setEditData(p => ({...p, company_name: e.target.value}))}
                className="bg-zinc-950 border-zinc-700 text-zinc-50" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-zinc-400 text-xs">Category</Label>
                <Input value={editData.category || ''} onChange={(e) => setEditData(p => ({...p, category: e.target.value}))}
                  className="bg-zinc-950 border-zinc-700 text-zinc-50" />
              </div>
              <div className="space-y-1">
                <Label className="text-zinc-400 text-xs">Subcategory</Label>
                <Input value={editData.subcategory || ''} onChange={(e) => setEditData(p => ({...p, subcategory: e.target.value}))}
                  className="bg-zinc-950 border-zinc-700 text-zinc-50" />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-zinc-400 text-xs">Description</Label>
              <Textarea value={editData.description || ''} onChange={(e) => setEditData(p => ({...p, description: e.target.value}))}
                className="bg-zinc-950 border-zinc-700 text-zinc-50 min-h-[80px]" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-zinc-400 text-xs">Email</Label>
                <Input value={editData.main_contact_email || ''} onChange={(e) => setEditData(p => ({...p, main_contact_email: e.target.value}))}
                  className="bg-zinc-950 border-zinc-700 text-zinc-50" />
              </div>
              <div className="space-y-1">
                <Label className="text-zinc-400 text-xs">Phone</Label>
                <Input value={editData.phone || ''} onChange={(e) => setEditData(p => ({...p, phone: e.target.value}))}
                  className="bg-zinc-950 border-zinc-700 text-zinc-50" />
              </div>
            </div>
            <Button onClick={handleSave} className="w-full bg-blue-600 hover:bg-blue-500 text-white"
              data-testid="save-review-btn">
              Save Changes
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
