import { useState, useRef } from 'react';
import { scrapeAPI, jobsAPI } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table';
import { Upload, FileSpreadsheet, Loader2, CheckCircle, XCircle, Clock } from 'lucide-react';
import { toast } from 'sonner';

const STATUS_ICON = {
  pending: <Clock className="w-3.5 h-3.5 text-zinc-400" />,
  processing: <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />,
  completed: <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />,
  error: <XCircle className="w-3.5 h-3.5 text-rose-400" />,
};

const STATUS_STYLES = {
  pending: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  processing: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  completed: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  error: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
};

export default function BulkAnalysisPage() {
  const [items, setItems] = useState([]);
  const [bulkJobId, setBulkJobId] = useState(null);
  const [bulkStatus, setBulkStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const fileRef = useRef(null);
  const pollRef = useRef(null);

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    try {
      const res = await scrapeAPI.bulkUpload(file);
      setBulkJobId(res.data.bulk_job_id);
      setItems(res.data.items || []);
      setBulkStatus('processing');
      startPolling(res.data.bulk_job_id);
      toast.success(`Started processing ${res.data.total_urls} URLs`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setLoading(false);
    }
  };

  const startPolling = (bjId) => {
    setPolling(true);
    pollRef.current = setInterval(async () => {
      try {
        const [bulkRes, itemsRes] = await Promise.all([
          jobsAPI.getBulk(bjId),
          jobsAPI.getBulkItems(bjId)
        ]);
        setBulkStatus(bulkRes.data.status);
        setItems(itemsRes.data?.items || itemsRes.data || []);
        if (['completed', 'partial', 'error'].includes(bulkRes.data.status)) {
          clearInterval(pollRef.current);
          setPolling(false);
        }
      } catch (err) {
        
      }
    }, 3000);
  };

  const completedCount = items.filter(i => i.status === 'completed').length;
  const progress = items.length > 0 ? (completedCount / items.length) * 100 : 0;

  return (
    <div className="space-y-6" data-testid="bulk-analysis-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-50 font-heading">Bulk Analysis</h1>
        <p className="text-sm text-zinc-400 mt-1">Upload CSV or Excel with agency URLs</p>
      </div>

      {/* Upload zone */}
      {!bulkJobId && (
        <Card className="bg-zinc-900 border-zinc-800 border-dashed">
          <CardContent className="p-8 flex flex-col items-center justify-center gap-4">
            <div className="w-14 h-14 rounded-lg bg-zinc-800 flex items-center justify-center">
              <FileSpreadsheet className="w-6 h-6 text-zinc-400" />
            </div>
            <div className="text-center">
              <p className="text-sm text-zinc-300 font-medium">Drop a CSV or Excel file here</p>
              <p className="text-xs text-zinc-500 mt-1">File must contain a column named "url"</p>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={handleFileUpload}
              className="hidden"
              data-testid="bulk-file-input"
            />
            <Button onClick={() => fileRef.current?.click()} disabled={loading}
              data-testid="bulk-upload-btn"
              className="bg-blue-600 hover:bg-blue-500 text-white">
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Upload className="w-4 h-4 mr-2" />}
              {loading ? 'Uploading...' : 'Select File'}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Progress */}
      {bulkJobId && (
        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-zinc-300 font-medium">
                {completedCount} / {items.length} URLs processed
              </span>
              <Badge className={`border ${STATUS_STYLES[bulkStatus] || STATUS_STYLES.processing}`}>
                {bulkStatus || 'processing'}
              </Badge>
            </div>
            <Progress value={progress} className="h-1.5 bg-zinc-800" />
          </CardContent>
        </Card>
      )}

      {/* Items table */}
      {items.length > 0 && (
        <div className="rounded border border-zinc-800 overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="bg-zinc-900 border-zinc-800 hover:bg-zinc-900">
                <TableHead className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium w-12">#</TableHead>
                <TableHead className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium">URL</TableHead>
                <TableHead className="text-xs uppercase tracking-[0.1em] text-zinc-500 font-medium w-32">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item, idx) => (
                <TableRow key={item.id} className="border-zinc-800 hover:bg-zinc-800/30 transition-colors"
                  data-testid={`bulk-item-${item.id}`}>
                  <TableCell className="text-xs text-zinc-500 font-mono">{idx + 1}</TableCell>
                  <TableCell className="text-sm text-zinc-200 font-mono truncate max-w-[400px]">{item.url}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {STATUS_ICON[item.status] || STATUS_ICON.pending}
                      <Badge className={`text-xs border ${STATUS_STYLES[item.status] || STATUS_STYLES.pending}`}>
                        {item.status}
                      </Badge>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
