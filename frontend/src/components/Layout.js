import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import {
  LayoutDashboard, Search, FileStack, List, Building2,
  ClipboardCheck, Settings, LogOut, Cpu,
  FileText, Palette, Newspaper, FileDown, BookOpen, Activity, Layers,
  TrendingUp, Globe, BarChart3, Zap, ArrowRightLeft, Database,
  Landmark, Shield, Heart, Workflow, ListChecks, ScrollText,
  Users, Lock, History, Flag, Plug, Gauge, Sparkles
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import api from '@/lib/api';

const navSections = [
  {
    label: 'HOME',
    items: [
      { path: '/', label: 'Dashboard', icon: LayoutDashboard },
      { path: '/ai-chat', label: 'AI Chat', icon: Sparkles },
    ],
  },
  {
    label: 'INTELLIGENCE ENGINE',
    items: [
      { path: '/engine/profiles', label: 'Profiles', icon: Layers },
      { path: '/engine/web-source', label: 'Web Source', icon: Globe },
      { path: '/engine/scrape-queue', label: 'Scrape Queue', icon: Workflow },
      { path: '/engine/health', label: 'Health', icon: Heart },
      { path: '/macro', label: 'Macro Intel', dot: 'bg-blue-500' },
      { path: '/sector-intelligence', label: 'Sector Intel', dot: 'bg-emerald-500' },
      { path: '/economic-intelligence', label: 'Economic Intel', dot: 'bg-amber-500' },
      { path: '/geo-intelligence', label: 'Geo Intel', dot: 'bg-violet-500' },
      { path: '/cross-intelligence', label: 'Sector × Geo', dot: 'bg-cyan-500' },
    ],
  },
  {
    label: 'M&A ENGINE',
    items: [
      { path: '/transactions', label: 'Transactions', icon: ArrowRightLeft },
      { path: '/ma-radar', label: 'M&A Radar', icon: Activity },
      { path: '/valuations', label: 'Valoraciones', dot: 'bg-emerald-500' },
      { path: '/ma/buyers', label: 'Buyers', icon: Users },
      { path: '/ma/sellers', label: 'Sellers', icon: Building2 },
      { path: '/ma/matching', label: 'Matching', icon: Search },
    ],
  },
  {
    label: 'KNOWLEDGE',
    items: [
      { path: '/taxonomy-intelligence', label: 'Taxonomy Intel', icon: Layers },
      { path: '/taxonomy', label: 'Taxonomía CIS', dot: 'bg-indigo-500' },
      { path: '/editorial', label: 'Editorial', icon: Newspaper },
      { path: '/manual', label: 'Manual', icon: FileDown },
      { path: '/api-docs', label: 'API Docs', icon: BookOpen },
      { path: '/knowledge/prompts', label: 'Prompts', icon: ScrollText },
    ],
  },
  {
    label: 'PLATFORM',
    items: [
      { path: '/settings', label: 'Configuración', icon: Settings },
      { path: '/platform/integrations', label: 'Integraciones', icon: Plug },
      { path: '/platform/jobs', label: 'Jobs', icon: ListChecks },
      { path: '/platform/logs', label: 'Logs', icon: ScrollText },
      { path: '/platform/feature-flags', label: 'Feature Flags', icon: Flag },
      { path: '/data-quality', label: 'Calidad de Datos', icon: Gauge },
      { path: '/doc-studio', label: 'Document Studio', icon: FileText },
      { path: '/template-builder', label: 'Template Builder', icon: Layers },
    ],
  },
];

// ADMIN renders after the dynamic DATA section (built from the Intelligence Engine).
const adminSection = {
  label: 'ADMIN',
  items: [
    { path: '/admin/users', label: 'Usuarios', icon: Users },
    { path: '/admin/roles', label: 'Roles', icon: Shield },
    { path: '/admin/security', label: 'Seguridad', icon: Lock },
    { path: '/admin/audit', label: 'Auditoría', icon: History },
  ],
};

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [dataSources, setDataSources] = useState([]);

  useEffect(() => {
    api.get('/intelligence/sources/sidebar')
      .then(r => setDataSources(r.data?.groups?.data || []))
      .catch(() => setDataSources([]));
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  // DATA section is derived 100% from the Intelligence Engine (no static array).
  const dynamicDataSection = {
    label: 'DATA',
    items: dataSources.map(s => ({ path: s.route, label: s.label, dot: s.dot })),
  };

  const allSections = [...navSections, dynamicDataSection, adminSection];

  return (
    <div className="flex h-screen bg-zinc-950" data-testid="app-layout">
      <aside className="w-56 flex-shrink-0 border-r border-zinc-800 bg-zinc-950 flex flex-col">
        <div className="p-4 flex items-center gap-2.5">
          <div className="w-7 h-7 rounded bg-blue-600 flex items-center justify-center">
            <Cpu className="w-3.5 h-3.5 text-white" />
          </div>
          <div>
            <h1 className="font-heading text-xs font-bold tracking-tight text-zinc-50">Intelligence Engine</h1>
            <p className="text-[8px] uppercase tracking-[0.15em] text-zinc-500 font-medium">Platform Console</p>
          </div>
        </div>

        <Separator className="bg-zinc-800" />

        <ScrollArea className="flex-1 px-2 py-2">
          <nav>
            {allSections.map((section, sIdx) => (
              <div key={sIdx}>
                {section.label && (
                  <p className="px-3 pt-3 pb-1 text-[7px] font-semibold uppercase tracking-[0.2em] text-zinc-600">
                    {section.label}
                  </p>
                )}
                {section.items.map((item) => (
                  <NavLink
                    key={item.path + item.label}
                    to={item.path}
                    end={item.path === '/'}
                    data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, '-').replace(/[×&]/g, '')}`}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 px-3 py-1 rounded text-[12px] font-medium transition-colors ${
                        isActive
                          ? 'bg-zinc-800 text-zinc-50'
                          : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
                      }`
                    }
                  >
                    {item.dot ? (
                      <span className={`w-2 h-2 rounded-full ${item.dot} flex-shrink-0`} />
                    ) : (
                      <item.icon className="w-3.5 h-3.5 flex-shrink-0" />
                    )}
                    {item.label}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>
        </ScrollArea>

        <div className="p-3 border-t border-zinc-800">
          <div className="flex items-center justify-between">
            <p className="text-[10px] text-zinc-500 truncate">{user?.email}</p>
            <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn"
              className="text-zinc-500 hover:text-zinc-200 h-7 w-7 p-0">
              <LogOut className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="p-6">
            <Outlet />
          </div>
        </ScrollArea>
      </main>
    </div>
  );
}
