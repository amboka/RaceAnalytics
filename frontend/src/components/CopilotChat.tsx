import { useState, useRef, useEffect, useCallback } from "react";
import { X, Send, Sparkles, Bot, User } from "lucide-react";
import ReactMarkdown from "react-markdown";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const DEMO_DISABLED_MESSAGE =
  "Copilot is disabled for demo purposes in this deployment.";

const INITIAL_MESSAGES: Message[] = [
  {
    id: "welcome",
    role: "assistant",
    content:
      "Hey! I'm your race analyst copilot. Ask me anything about your telemetry, lap performance, or setup changes. 🏎️",
  },
];

const CopilotChat = ({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) => {
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const dragState = useRef<{
    startX: number;
    startY: number;
    origX: number;
    origY: number;
  } | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (open) setPosition({ x: 0, y: 0 });
  }, [open]);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      dragState.current = {
        startX: e.clientX,
        startY: e.clientY,
        origX: position.x,
        origY: position.y,
      };
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [position],
  );

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragState.current || !panelRef.current) return;
    const dx = e.clientX - dragState.current.startX;
    const dy = e.clientY - dragState.current.startY;
    let newX = dragState.current.origX + dx;
    let newY = dragState.current.origY + dy;

    const rect = panelRef.current.getBoundingClientRect();
    const baseRight = 16;
    const baseBottom = 16;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    const minX = -(vw - baseRight - rect.width);
    const maxX = baseRight;
    const minY = -(vh - baseBottom - rect.height);
    const maxY = baseBottom;

    newX = Math.max(minX, Math.min(maxX, newX));
    newY = Math.max(minY, Math.min(maxY, newY));

    setPosition({ x: newX, y: newY });
  }, []);

  const onPointerUp = useCallback(() => {
    dragState.current = null;
  }, []);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input.trim(),
    };
    const assistantMsg: Message = {
      id: (Date.now() + 1).toString(),
      role: "assistant",
      content: DEMO_DISABLED_MESSAGE,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
  };

  if (!open) return null;

  return (
    <div
      ref={panelRef}
      style={{ transform: `translate(${position.x}px, ${position.y}px)` }}
      className="fixed bottom-4 right-[76px] z-50 w-[380px] h-[520px] flex flex-col rounded-2xl border border-border bg-card shadow-2xl overflow-hidden animate-in slide-in-from-bottom-4 fade-in duration-300"
    >
      {/* Header — draggable */}
      <div
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        className="flex items-center justify-between px-4 py-3 border-b border-border bg-secondary/50 cursor-grab active:cursor-grabbing select-none touch-none"
      >
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-primary/15 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-primary" />
          </div>
          <div>
            <span className="text-sm font-semibold text-foreground">
              Race Copilot
            </span>
            <span className="block text-[10px] text-muted-foreground leading-none">
              AI Assistant
            </span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="w-7 h-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 scrollbar-thin">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-2.5 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
          >
            <div
              className={`w-6 h-6 rounded-full flex-shrink-0 flex items-center justify-center mt-0.5 ${
                msg.role === "assistant"
                  ? "bg-primary/15 text-primary"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {msg.role === "assistant" ? (
                <Bot className="w-3.5 h-3.5" />
              ) : (
                <User className="w-3.5 h-3.5" />
              )}
            </div>
            <div
              className={`max-w-[75%] px-3 py-2 rounded-xl text-[13px] leading-relaxed ${
                msg.role === "assistant"
                  ? "bg-secondary text-secondary-foreground rounded-tl-sm"
                  : "bg-primary text-primary-foreground rounded-tr-sm"
              }`}
            >
              {msg.role === "assistant" ? (
                <div className="prose prose-sm prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0.5 [&_code]:text-[12px] [&_code]:bg-background/30 [&_code]:px-1 [&_code]:rounded [&_pre]:bg-background/30 [&_pre]:p-2 [&_pre]:rounded-lg [&_pre]:text-[12px]">
                  <ReactMarkdown>{msg.content || "⠿"}</ReactMarkdown>
                </div>
              ) : (
                msg.content
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-3 py-3 border-t border-border">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-2 bg-secondary/60 rounded-xl px-3 py-1.5"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your telemetry…"
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none py-1.5"
          />
          <button
            type="submit"
            disabled={!input.trim()}
            className="w-7 h-7 rounded-lg flex items-center justify-center bg-primary text-primary-foreground disabled:opacity-30 hover:bg-primary/90 transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </form>
      </div>
    </div>
  );
};

export default CopilotChat;
