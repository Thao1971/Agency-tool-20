import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2, Trash2, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import api from '@/lib/api';

export default function AIChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, streaming]);

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', content: text }, { role: 'assistant', content: '' }]);
    setStreaming(true);

    try {
      const { data } = await api.post('/ai-chat/message', { message: text, session_id: sessionId });
      if (data.session_id) setSessionId(data.session_id);
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { role: 'assistant', content: data.reply || '' };
        return copy;
      });
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message;
      toast.error(`Chat error: ${msg}`);
      setMessages((m) => {
        const copy = [...m];
        if (copy[copy.length - 1]?.role === 'assistant' && !copy[copy.length - 1].content) {
          copy[copy.length - 1] = { role: 'assistant', content: `⚠️ ${msg}` };
        }
        return copy;
      });
    } finally {
      setStreaming(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
    setSessionId(null);
    toast.success('Nueva conversación');
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]" data-testid="ai-chat-page">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-500">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold">AI Chat</h1>
            <p className="text-sm text-muted-foreground">OpenAI · gpt-5.5 · utilidad de pruebas</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={clearChat} data-testid="ai-chat-new-btn" disabled={streaming}>
          <Trash2 className="w-4 h-4 mr-2" /> Nueva
        </Button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto rounded-lg border bg-card p-4 space-y-4" data-testid="ai-chat-messages">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground gap-2">
            <Bot className="w-10 h-10 opacity-40" />
            <p className="text-sm">Escribe un mensaje para empezar a chatear con gpt-5.5</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`} data-testid={`ai-chat-msg-${m.role}`}>
            {m.role === 'assistant' && (
              <div className="shrink-0 p-2 rounded-full bg-emerald-500/10 text-emerald-500 h-8 w-8 flex items-center justify-center">
                <Bot className="w-4 h-4" />
              </div>
            )}
            <div className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${m.role === 'user' ? 'bg-emerald-500 text-white' : 'bg-muted'}`}>
              {m.content || (streaming && i === messages.length - 1 ? <Loader2 className="w-4 h-4 animate-spin" /> : '')}
            </div>
            {m.role === 'user' && (
              <div className="shrink-0 p-2 rounded-full bg-muted h-8 w-8 flex items-center justify-center">
                <User className="w-4 h-4" />
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-end gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Escribe tu mensaje… (Enter para enviar, Shift+Enter salto de línea)"
          className="resize-none min-h-[52px] max-h-40"
          data-testid="ai-chat-input"
          disabled={streaming}
        />
        <Button onClick={send} disabled={streaming || !input.trim()} data-testid="ai-chat-send-btn" className="h-[52px]">
          {streaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </Button>
      </div>
    </div>
  );
}
