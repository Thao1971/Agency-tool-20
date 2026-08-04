import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Send, Bot, User, Loader2, Trash2, Brain, ChevronDown, ChevronRight,
         ArrowRight, FileText, Eye, Star, Search, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import api from '@/lib/api';

// Icono por tipo de acción del contrato del Copilot
const ACTION_ICON = {
  navigate: ArrowRight, analyze: Brain, open_deliberation: Eye,
  generate_document: FileText, add_to_watchlist: Star, search: Search, explain_order: Info,
  select_entity: ArrowRight,
};

function EntityCard({ card }) {
  if (!card) return null;
  return (
    <div className="mt-2 rounded-lg border border-neutral-200 bg-white p-3">
      <div className="flex items-center justify-between">
        <div className="font-semibold text-neutral-900">{card.name}</div>
        {card.conviction && (
          <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
            {card.conviction}
          </span>
        )}
      </div>
      {Array.isArray(card.kpis) && card.kpis.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-neutral-600">
          {card.kpis.map((k, i) => (
            <span key={i}><span className="text-neutral-400">{k.label}:</span> {k.value}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function Disclosure({ disclosure }) {
  const [open, setOpen] = useState(false);
  if (!disclosure) return null;
  return (
    <div className="mt-2">
      <button onClick={() => setOpen(!open)}
              className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-800">
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Ver deliberación
      </button>
      {open && (
        <div className="mt-1 rounded-md bg-neutral-50 p-2 text-xs text-neutral-600">
          Convicción: <b>{disclosure.conviction}</b> · banda {disclosure.band} ·
          score {disclosure.score}/100 · confianza {disclosure.confidence}%
        </div>
      )}
    </div>
  );
}

export default function CopilotPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [sectors, setSectors] = useState([]);
  const scrollRef = useRef(null);
  const lastQuestionRef = useRef('');
  const navigate = useNavigate();

  useEffect(() => {
    api.get('/copilot-ui/sectors')
      .then(({ data }) => setSectors((data.sectors || []).slice(0, 8)))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, busy]);

  const runAction = (a, msg) => {
    switch (a.kind) {
      case 'select_entity':
        runAsk(lastQuestionRef.current || `Analiza ${a.params?.name}`,
               { company_id: a.params?.company_id },
               `Me refiero a ${a.params?.name}`);
        break;
      case 'navigate':
        if (a.target && a.target.startsWith('/')) navigate(a.target);
        else toast.info(`Ir a: ${a.label}`);
        break;
      case 'generate_document':
        navigate('/doc-studio');
        break;
      case 'open_deliberation':
        toast.info(msg?.disclosure
          ? `${msg.disclosure.conviction} · banda ${msg.disclosure.band} · ${msg.disclosure.score}/100`
          : 'Sin deliberación disponible');
        break;
      case 'explain_order': {
        const rb = (msg?.personalization_applied?.ranking_bias) || [];
        toast.info(rb.length ? rb.join(' · ') : 'Sin sesgo aplicado');
        break;
      }
      case 'add_to_watchlist':
        toast.success('Añadido a seguimiento (demo)');
        break;
      case 'search':
        toast.info(`Buscar: ${a.params?.query || ''}`);
        break;
      default:
        toast.info(a.label);
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    lastQuestionRef.current = text;
    runAsk(text);
  };

  const runAsk = async (question, extra = {}, displayText = null) => {
    if (busy) return;
    setMessages((m) => [...m, { role: 'user', content: displayText || question }]);
    setBusy(true);
    try {
      const { data } = await api.post('/copilot-ui/ask', { question, session_id: sessionId, ...extra });
      if (data.session_id) setSessionId(data.session_id);
      setMessages((m) => [...m, {
        role: 'assistant',
        content: data.answer?.message || data.answer?.detail || '…',
        card: data.ui?.card, actions: data.actions || [], disclosure: data.answer?.disclosure,
        attribution: data.answer?.attribution || [], proactive: data.proactive,
        personalization_applied: data.personalization_applied, level: data.level,
      }]);
    } catch (e) {
      const err = e?.response?.data?.detail || e.message;
      toast.error(`Copilot: ${err}`);
      setMessages((m) => [...m, { role: 'assistant', content: `⚠️ ${err}` }]);
    } finally {
      setBusy(false);
    }
  };

  const clearChat = async () => {
    if (sessionId) { try { await api.post('/copilot-ui/session/close', { session_id: sessionId }); } catch (_) {} }
    setMessages([]); setSessionId(null);
    toast.success('Nueva conversación');
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-neutral-900">
            <Brain size={20} /> ARROBA Copilot
          </h1>
          <p className="text-sm text-neutral-500">Copiloto senior de M&A — pregunta por una compañía, riesgos, valoración o si comprarla.</p>
        </div>
        <Button variant="ghost" size="sm" onClick={clearChat}><Trash2 size={16} /> Nueva</Button>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto rounded-lg border border-neutral-200 bg-neutral-50 p-4">
        {messages.length === 0 && (
          <div className="mt-10 text-center text-sm text-neutral-400">
            Ejemplos: "¿cuál es el EBITDA de ACME?" · "¿qué riesgos tiene?" · "¿deberíamos comprarla?"
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : ''}`}>
            {m.role === 'assistant' && <Bot size={20} className="mt-1 shrink-0 text-neutral-500" />}
            <div className={`max-w-[80%] ${m.role === 'user' ? 'order-1' : ''}`}>
              <div className={`rounded-lg px-3 py-2 text-sm ${m.role === 'user'
                ? 'bg-neutral-900 text-white' : 'bg-white text-neutral-800 border border-neutral-200'}`}>
                {m.content}
              </div>
              {m.role === 'assistant' && (
                <>
                  <EntityCard card={m.card} />
                  <Disclosure disclosure={m.disclosure} />
                  {m.proactive && (
                    <div className="mt-2 rounded-md border-l-2 border-yellow-400 bg-yellow-50 px-3 py-1.5 text-xs text-yellow-900">
                      {m.proactive.message}
                    </div>
                  )}
                  {Array.isArray(m.actions) && m.actions.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {m.actions.map((a) => {
                        const Icon = ACTION_ICON[a.kind] || ArrowRight;
                        return (
                          <button key={a.id} onClick={() => runAction(a, m)}
                            className="inline-flex items-center gap-1 rounded-full border border-neutral-300 bg-white px-3 py-1 text-xs text-neutral-700 hover:border-neutral-900 hover:text-neutral-900">
                            <Icon size={13} /> {a.label}
                          </button>
                        );
                      })}
                    </div>
                  )}
                  {Array.isArray(m.attribution) && m.attribution.length > 0 && (
                    <div className="mt-1 text-[11px] text-neutral-400">
                      Áreas: {m.attribution.map((x) => x.label).join(' · ')}
                    </div>
                  )}
                </>
              )}
            </div>
            {m.role === 'user' && <User size={20} className="order-2 mt-1 shrink-0 text-neutral-500" />}
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-sm text-neutral-400">
            <Loader2 size={16} className="animate-spin" /> El Copilot está pensando…
          </div>
        )}
      </div>

      {sectors.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2" data-testid="copilot-sector-chips">
          <span className="self-center text-xs text-neutral-400">Explora por sector:</span>
          {sectors.map((s) => (
            <button key={s.id} onClick={() => runAsk(`empresas del sector ${s.label}`)} disabled={busy}
              data-testid={`sector-chip-${s.id}`}
              className="rounded-full border border-neutral-300 bg-white px-3 py-1 text-xs text-neutral-700 hover:border-neutral-900 hover:text-neutral-900 disabled:opacity-50">
              {s.label}{typeof s.count === 'number' ? ` (${s.count})` : ''}
            </button>
          ))}
        </div>
      )}

      <div className="mt-3 flex items-end gap-2">
        <Textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown}
          placeholder="Pregunta al Copilot…" rows={2} className="resize-none" />
        <Button onClick={send} disabled={busy || !input.trim()}><Send size={16} /></Button>
      </div>
    </div>
  );
}
