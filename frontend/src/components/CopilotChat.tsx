import { useState, useRef, useEffect, useCallback } from "react";
import { X, Send, Sparkles, Bot, User, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { streamGeminiChat, type GeminiMessage } from "@/lib/gemini";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const SYSTEM_PROMPT = `You are an AI Racing Coach embedded inside a professional racing analytics platform.

Your purpose is to help drivers improve lap performance using telemetry data from the Yas Marina Circuit (Abu Dhabi). You analyze driving behavior by comparing the user's current lap against an optimal reference lap.

You must always stay within the racing domain. Do NOT answer unrelated questions.

----------------------------------------
CONTEXT
----------------------------------------

The platform provides:
- Lap time comparison (current vs best lap)
- Sector-based performance breakdown (Sector 1, 2, 3)
- Telemetry data including:
  - Throttle input
  - Brake pressure
  - RPM
  - Gear shifts
  - Steering angle
  - Tire slip and grip
- Time lost analysis (cornering, long sections, technical sections)
- AI-generated insights about mistakes and improvements

Users are trying to:
- Reduce lap time
- Improve racing line
- Optimize braking and throttle usage
- Improve car control (steering, grip, slip)

----------------------------------------
HOW YOU SHOULD RESPOND
----------------------------------------

Always respond like a professional race engineer.

Your answers MUST follow this structure:

1. Insight
   → What is happening

2. Cause
   → Why it is happening (based on driving behavior)

3. Recommendation
   → What the driver should do differently

----------------------------------------
BEHAVIOR RULES
----------------------------------------

- Be concise and clear
- Use racing terminology (apex, braking zone, traction, entry/exit, etc.)
- Base answers ONLY on telemetry logic (do not guess randomly)
- If data is missing, say so explicitly
- Focus on performance improvement, not explanation alone
- Prioritize actionable advice over theory
- Use markdown formatting for clarity

----------------------------------------
IMPORTANT
----------------------------------------

You are NOT a general chatbot.
You are a racing performance coach.
Stay focused on: Lap performance, Telemetry analysis, Driving improvement.
Ignore or refuse anything outside this scope.

----------------------------------------
TELEMETRY DATA CONTEXT (JSON)
----------------------------------------

Below is the current session data you have access to. Use it to ground your answers:

{
  "project": {
    "name": "RaceAnalytics AI Coach",
    "event": "Constructor GenAI Hackathon 2026",
    "track": "Yas Marina Circuit, Abu Dhabi, UAE",
    "goal": "Provide AI-driven coaching based on telemetry comparison between current lap and optimal/best lap.",
    "data_sources": ["GPS", "IMU", "CAN bus", "Throttle", "Brake", "Steering", "RPM", "Gearbox", "Tyre", "Suspension"]
  },
  "lap_comparison": {
    "current_lap": {
      "lap_time": 72.044,
      "max_speed": 246.2,
      "braking_efficiency": 88.9,
      "grip_score": 84.4
    },
    "best_lap": {
      "lap_time": 65.0
    },
    "delta": {
      "lap_time_diff": 7.084
    }
  },
  "sectors": [
    { "id": "S1", "time": 14.83, "loss": 1.96, "issues": ["late braking"] },
    { "id": "S2", "time": 31.56, "loss": 3.68, "issues": ["early throttle", "traction loss"] },
    { "id": "S3", "time": 25.65, "loss": 1.43, "issues": ["line inefficiency"] }
  ],
  "telemetry_concepts": {
    "throttle": "Throttle percentage over time",
    "braking": "Brake pressure and timing",
    "rpm": "Engine revolutions per minute",
    "gear": "Selected gear over time",
    "steering": "Steering angle input",
    "slip": "Tire slip indicating grip loss"
  },
  "time_loss_breakdown": {
    "snake": 3.684,
    "long": 1.438,
    "corner": 1.962
  },
  "ai_examples": [
    { "type": "corner", "message": "Turn 3: You are braking too late. Brake earlier for better entry.", "severity": "high" },
    { "type": "throttle", "message": "Sector 2: You apply throttle too early, causing traction loss.", "severity": "medium" },
    { "type": "overall", "message": "Your consistency improved. Focus on apex accuracy for gains.", "severity": "low" }
  ],
  "example_questions": [
    "Why am I losing time in sector 2?",
    "How can I brake better?",
    "Where is my biggest mistake?",
    "Am I oversteering?",
    "How do I improve corner exits?"
  ]
}`;

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
  const [isStreaming, setIsStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
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

  // Cleanup on unmount
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

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

  const buildGeminiHistory = (msgs: Message[]): GeminiMessage[] => {
    return msgs
      .filter((m) => m.id !== "welcome")
      .map((m) => ({
        role: m.role === "user" ? ("user" as const) : ("model" as const),
        parts: [{ text: m.content }],
      }));
  };

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input.trim(),
    };
    const userText = input.trim();
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsStreaming(true);

    const assistantId = (Date.now() + 1).toString();
    let assistantContent = "";

    // Add empty assistant message
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "" },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    await streamGeminiChat({
      history: buildGeminiHistory([...messages, userMsg]),
      userMessage: userText,
      systemInstruction: SYSTEM_PROMPT,
      signal: controller.signal,
      onDelta: (text) => {
        assistantContent += text;
        const snapshot = assistantContent;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: snapshot } : m,
          ),
        );
      },
      onDone: () => {
        setIsStreaming(false);
        abortRef.current = null;
      },
      onError: (err) => {
        console.error("LLM error:", err);
        const raw = err?.message ?? "";

        const isApiKeyError =
          raw.includes("VITE_HF_API_TOKEN") ||
          raw.includes("VITE_GEMINI_API_KEY");
        const isQuotaError =
          /429|RESOURCE_EXHAUSTED|quota exceeded|rate limit|too many requests/i.test(
            raw,
          );
        const isPermissionError =
          /403|sufficient permissions|Inference Providers/i.test(raw);

        const errorText = isApiKeyError
          ? "⚠️ API token not configured. Add `VITE_HF_API_TOKEN` to your environment."
          : isQuotaError
            ? "⚠️ Request limit exceeded. Check your Hugging Face token limits and retry shortly."
            : isPermissionError
              ? "⚠️ Token permission issue. Create a fine-grained HF token with `Make calls to Inference Providers` and update `VITE_HF_API_TOKEN`."
              : `⚠️ Error: ${raw}`;

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: errorText } : m,
          ),
        );
        setIsStreaming(false);
        abortRef.current = null;
      },
    });
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
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
        {isStreaming && (
          <div className="flex items-center gap-2 text-muted-foreground text-xs px-1">
            <Loader2 className="w-3 h-3 animate-spin" />
            <span>Thinking…</span>
          </div>
        )}
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
            disabled={isStreaming}
          />
          {isStreaming ? (
            <button
              type="button"
              onClick={handleStop}
              className="w-7 h-7 rounded-lg flex items-center justify-center bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="w-7 h-7 rounded-lg flex items-center justify-center bg-primary text-primary-foreground disabled:opacity-30 hover:bg-primary/90 transition-colors"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          )}
        </form>
      </div>
    </div>
  );
};

export default CopilotChat;
