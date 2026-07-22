import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2, RefreshCw, ArrowLeft, MapPin, BarChart3, Layers, Building2, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { SyncBar } from '@/components/SyncBar';

const SECTION_SHORT = {
  A:'Agric.', B:'Extract.', C:'Manufact.', D:'Energia', E:'Agua', F:'Constr.',
  G:'Comercio', H:'Transp.', I:'Hostel.', J:'TIC', K:'Finanzas', L:'Inmob.',
  M:'Profes.', N:'Admin.', O:'Adm.Pub.', P:'Educ.', Q:'Sanidad', R:'Ocio',
  S:'Otros', T:'Hogares', U:'Extraterr.',
};

const CCAA_SHORT = {
  '01':'AND','02':'ARA','03':'AST','04':'BAL','05':'CAN','06':'CNT',
  '07':'CYL','08':'CLM','09':'CAT','10':'VAL','11':'EXT','12':'GAL',
  '13':'MAD','14':'MUR','15':'NAV','16':'PVA','17':'RIO','18':'CEU','19':'MEL',
};

function HeatCell({ value, max, label, onClick }) {
  const intensity = max > 0 ? Math.min(1, value / max) : 0;
  let bg;
  if (value === 0) bg = 'bg-zinc-900';
  else if (intensity < 0.15) bg = 'bg-emerald-950/40';
  else if (intensity < 0.3) bg = 'bg-emerald-900/50';
  else if (intensity < 0.5) bg = 'bg-emerald-800/60';
  else if (intensity < 0.7) bg = 'bg-emerald-700/70';
  else if (intensity < 0.85) bg = 'bg-emerald-600/80';
  else bg = 'bg-emerald-500';

  return (
    <td
      className={`${bg} border border-zinc-800/30 text-center cursor-pointer hover:ring-1 hover:ring-emerald-400/50 transition-all`}
      onClick={onClick}
      title={label}
      style={{ minWidth: 36, height: 32 }}
    >
      {value > 0 && <span className="text-[9px] text-zinc-200 tabular-nums">{value}</span>}
    </td>
  );
}

function ConcentrationBadge({ value }) {
  if (!value || value === 0) return <span className="text-xs text-zinc-600">—</span>;
  const color = value >= 3 ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
    : value >= 1.5 ? 'bg-blue-500/15 text-blue-400 border-blue-500/20'
    : value >= 0.8 ? 'bg-zinc-500/15 text-zinc-400 border-zinc-500/20'
    : 'bg-rose-500/15 text-rose-400 border-rose-500/20';
  return (
    <Badge variant="outline" className={`text-[10px] px-1.5 py-0 tabular-nums ${color}`}>
      {value.toFixed(1)}x
    </Badge>
  );
}

function DetailTable({ rows, type, onBack }) {
  const isSector = type === 'sector';
  return (
    <div className="space-y-3">
      <Button variant="ghost" size="sm" onClick={onBack} className="h-7 px-2 text-xs text-zinc-400 hover:text-zinc-200">
        <ArrowLeft className="w-3 h-3 mr-1" /> Volver al heatmap
      </Button>
      <Card className="bg-zinc-900/50 border-zinc-800">
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800 hover:bg-transparent">
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">
                {isSector ? 'Sector CNAE' : 'Territorio'}
              </TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">BORME</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Empresas est.</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Concentracion</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-zinc-500">Activity</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r, i) => (
              <TableRow key={i} className="border-zinc-800/50">
                <TableCell className="py-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-zinc-500">
                      {isSector ? r.cnae_section : r.geo_id}
                    </span>
                    <span className="text-sm text-zinc-200 truncate max-w-[250px]">
                      {isSector ? r.cnae_label : r.geo_name}
                    </span>
                  </div>
                </TableCell>
                <TableCell className="py-2">
                  <span className="text-sm font-semibold text-zinc-100 tabular-nums">
                    {(r.borme_events || 0).toLocaleString('es-ES')}
                  </span>
                </TableCell>
                <TableCell className="py-2">
                  <span className="text-xs text-zinc-400 tabular-nums">
                    {(r.estimated_companies || 0).toLocaleString('es-ES')}
                  </span>
                </TableCell>
                <TableCell className="py-2">
                  <ConcentrationBadge value={r.concentration_index} />
                </TableCell>
                <TableCell className="py-2">
                  <div className="flex items-center gap-2">
                    <div className="w-12 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${(r.activity_score||0) >= 60 ? 'bg-emerald-500' : (r.activity_score||0) >= 30 ? 'bg-blue-500' : 'bg-zinc-600'}`}
                        style={{ width: `${Math.min(100, r.activity_score || 0)}%` }} />
                    </div>
                    <span className="text-xs text-zinc-400 tabular-nums w-5">{r.activity_score || 0}</span>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

export default function CrossIntelligencePage() {
  const [heatmapData, setHeatmapData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detailView, setDetailView] = useState(null);
  const [detailRows, setDetailRows] = useState([]);
  const [detailTitle, setDetailTitle] = useState('');
  const [tab, setTab] = useState('heatmap');

  const loadHeatmap = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/public/cross-intelligence/heatmap');
      setHeatmapData(data.cells || []);
    } catch (e) { toast.error('Error cargando heatmap'); }
    setLoading(false);
  }, []);

  useEffect(() => { loadHeatmap(); }, [loadHeatmap]);

  const handleSync = async () => {
    try {
      await api.post('/public/cross-intelligence/sync');
      toast.success('Cross-Intelligence recalculado');
      loadHeatmap();
    } catch (e) { toast.error('Error sincronizando'); }
  };

  // Build heatmap matrix
  const sections = [...new Set(heatmapData.map(c => c.cnae_section))].sort();
  const ccaas = [...new Set(heatmapData.map(c => c.ccaa_code))].sort();
  const maxBorme = Math.max(1, ...heatmapData.map(c => c.borme_events));

  const getCell = (section, ccaa) => {
    return heatmapData.find(c => c.cnae_section === section && c.ccaa_code === ccaa) || { borme_events: 0 };
  };

  const handleCellClick = async (section, ccaa) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/public/cross-intelligence/sectors-in/ccaa/${ccaa}`);
      setDetailRows(data.sectors || []);
      const ccaaName = heatmapData.find(c => c.ccaa_code === ccaa)?.ccaa_name || ccaa;
      setDetailTitle(`Sectores en ${ccaaName}`);
      setDetailView({ type: 'sector', ccaa });
    } catch (e) { toast.error('Error cargando detalle'); }
    setLoading(false);
  };

  const handleSectionClick = async (section) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/public/cross-intelligence/territory-for/${section}?geo_level=ccaa`);
      setDetailRows(data.territories || []);
      setDetailTitle(`${section} — ${data.cnae_label || ''}`);
      setDetailView({ type: 'territory', section });
    } catch (e) { toast.error('Error cargando detalle'); }
    setLoading(false);
  };

  const handleCCAAClick = async (ccaa) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/public/cross-intelligence/sectors-in/ccaa/${ccaa}`);
      setDetailRows(data.sectors || []);
      const ccaaName = heatmapData.find(c => c.ccaa_code === ccaa)?.ccaa_name || ccaa;
      setDetailTitle(`Sectores en ${ccaaName}`);
      setDetailView({ type: 'sector', ccaa });
    } catch (e) { toast.error('Error cargando detalle'); }
    setLoading(false);
  };

  const goBack = () => {
    setDetailView(null);
    setDetailRows([]);
  };

  // Stats
  const totalBorme = heatmapData.reduce((s, c) => s + c.borme_events, 0);
  const totalCombos = heatmapData.filter(c => c.borme_events > 0).length;

  return (
    <div className="space-y-4" data-testid="cross-intelligence-page">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">Sector x Geo</h1>
        <p className="text-xs text-zinc-500 mt-0.5">
          Cruce sectorial-territorial — {heatmapData.length} combinaciones
        </p>
      </div>

      <SyncBar
        module="cross_intelligence"
        syncEndpoint="/public/cross-intelligence/sync"
        onSyncComplete={loadHeatmap}
      />

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <div className="flex items-center gap-2 mb-1"><Layers className="w-3.5 h-3.5 text-blue-400" /><span className="text-[10px] uppercase tracking-wider text-zinc-500">Combinaciones</span></div>
            <p className="text-xl font-bold text-zinc-100 tabular-nums" data-testid="cross-combos">{heatmapData.length}</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <div className="flex items-center gap-2 mb-1"><Zap className="w-3.5 h-3.5 text-emerald-400" /><span className="text-[10px] uppercase tracking-wider text-zinc-500">Con actividad</span></div>
            <p className="text-xl font-bold text-emerald-400 tabular-nums" data-testid="cross-active">{totalCombos}</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <div className="flex items-center gap-2 mb-1"><BarChart3 className="w-3.5 h-3.5 text-zinc-400" /><span className="text-[10px] uppercase tracking-wider text-zinc-500">Eventos BORME</span></div>
            <p className="text-xl font-bold text-zinc-100 tabular-nums">{totalBorme.toLocaleString('es-ES')}</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <div className="flex items-center gap-2 mb-1"><MapPin className="w-3.5 h-3.5 text-violet-400" /><span className="text-[10px] uppercase tracking-wider text-zinc-500">Sectores x CCAA</span></div>
            <p className="text-xl font-bold text-zinc-100 tabular-nums">{sections.length} x {ccaas.length}</p>
          </CardContent>
        </Card>
      </div>

      {detailView ? (
        <DetailTable
          rows={detailRows}
          type={detailView.type}
          onBack={goBack}
        />
      ) : loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-5 h-5 animate-spin text-zinc-500" />
        </div>
      ) : (
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="bg-zinc-900 border border-zinc-800">
            <TabsTrigger value="heatmap" className="text-xs data-[state=active]:bg-zinc-800">Heatmap</TabsTrigger>
            <TabsTrigger value="by-territory" className="text-xs data-[state=active]:bg-zinc-800">Por territorio</TabsTrigger>
            <TabsTrigger value="by-sector" className="text-xs data-[state=active]:bg-zinc-800">Por sector</TabsTrigger>
          </TabsList>

          <TabsContent value="heatmap" className="mt-3">
            <Card className="bg-zinc-900/50 border-zinc-800 overflow-x-auto">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs text-zinc-400">
                  Eventos BORME por sector (filas) y CCAA (columnas). Click en celda para detalles.
                </CardTitle>
              </CardHeader>
              <CardContent className="p-2">
                <table className="w-full border-collapse" data-testid="heatmap-table">
                  <thead>
                    <tr>
                      <th className="text-[9px] text-zinc-600 text-left px-1 py-1 w-14 sticky left-0 bg-zinc-900/95 z-10">CNAE</th>
                      {ccaas.map(c => (
                        <th key={c} className="text-[8px] text-zinc-500 text-center px-0 py-1 cursor-pointer hover:text-zinc-200"
                          onClick={() => handleCCAAClick(c)} title={heatmapData.find(h => h.ccaa_code === c)?.ccaa_name}>
                          {CCAA_SHORT[c] || c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sections.map(sec => (
                      <tr key={sec}>
                        <td className="text-[10px] font-mono text-zinc-400 px-1 py-0 sticky left-0 bg-zinc-900/95 z-10 cursor-pointer hover:text-zinc-200"
                          onClick={() => handleSectionClick(sec)}
                          title={SECTION_SHORT[sec]}>
                          {sec}
                        </td>
                        {ccaas.map(c => {
                          const cell = getCell(sec, c);
                          return (
                            <HeatCell
                              key={c}
                              value={cell.borme_events}
                              max={maxBorme}
                              label={`${SECTION_SHORT[sec] || sec} × ${CCAA_SHORT[c] || c}: ${cell.borme_events} BORME`}
                              onClick={() => handleCellClick(sec, c)}
                            />
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {/* Legend */}
                <div className="flex items-center gap-3 mt-3 px-2">
                  <span className="text-[9px] text-zinc-600">Intensidad BORME:</span>
                  <div className="flex items-center gap-0.5">
                    {['bg-zinc-900','bg-emerald-950/40','bg-emerald-900/50','bg-emerald-800/60','bg-emerald-700/70','bg-emerald-600/80','bg-emerald-500'].map((bg, i) => (
                      <div key={i} className={`w-5 h-3 ${bg} border border-zinc-800/30 rounded-sm`} />
                    ))}
                  </div>
                  <span className="text-[9px] text-zinc-600">0 → {maxBorme}</span>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="by-territory" className="mt-3">
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
              {ccaas.map(c => {
                const ccaaName = heatmapData.find(h => h.ccaa_code === c)?.ccaa_name || c;
                const ccaaCells = heatmapData.filter(h => h.ccaa_code === c && h.borme_events > 0);
                const totalB = ccaaCells.reduce((s, x) => s + x.borme_events, 0);
                const topSector = ccaaCells.sort((a, b) => b.borme_events - a.borme_events)[0];
                return (
                  <Card key={c} className="bg-zinc-900/50 border-zinc-800 cursor-pointer hover:border-zinc-700 transition-colors"
                    onClick={() => handleCCAAClick(c)} data-testid={`cross-ccaa-${c}`}>
                    <CardContent className="p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-semibold text-zinc-200">{ccaaName}</span>
                        <span className="text-xs text-zinc-500 tabular-nums">{totalB} BORME</span>
                      </div>
                      {topSector && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] text-zinc-500">Top:</span>
                          <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-emerald-400 border-emerald-500/20">
                            {topSector.cnae_section} {SECTION_SHORT[topSector.cnae_section]}
                          </Badge>
                          <span className="text-[10px] text-zinc-500">{topSector.borme_events}</span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </TabsContent>

          <TabsContent value="by-sector" className="mt-3">
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
              {sections.map(sec => {
                const secCells = heatmapData.filter(h => h.cnae_section === sec && h.borme_events > 0);
                const totalB = secCells.reduce((s, x) => s + x.borme_events, 0);
                const topCCAA = secCells.sort((a, b) => b.borme_events - a.borme_events)[0];
                return (
                  <Card key={sec} className="bg-zinc-900/50 border-zinc-800 cursor-pointer hover:border-zinc-700 transition-colors"
                    onClick={() => handleSectionClick(sec)} data-testid={`cross-section-${sec}`}>
                    <CardContent className="p-3">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-mono text-zinc-500">{sec}</span>
                          <span className="text-sm text-zinc-200">{SECTION_SHORT[sec]}</span>
                        </div>
                        <span className="text-xs text-zinc-500 tabular-nums">{totalB} BORME</span>
                      </div>
                      {topCCAA && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] text-zinc-500">Top:</span>
                          <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-violet-400 border-violet-500/20">
                            {topCCAA.ccaa_name?.substring(0, 15)}
                          </Badge>
                          <span className="text-[10px] text-zinc-500">{topCCAA.borme_events}</span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
