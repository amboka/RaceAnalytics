const DEFAULT_HF_MODEL = "Qwen/Qwen2.5-7B-Instruct";
const HF_ROUTER_ORIGIN = "https://router.huggingface.co";

const getHfConfig = () => {
  const token = import.meta.env.VITE_HF_API_TOKEN as string | undefined;
  if (!token) {
    throw new Error("VITE_HF_API_TOKEN is not set. Add it to your .env file.");
  }

  const model =
    (import.meta.env.VITE_HF_MODEL as string | undefined)?.trim() ||
    DEFAULT_HF_MODEL;

  return {
    token,
    model,
    // In dev we route through Vite proxy to avoid browser CORS failures.
    url: `${import.meta.env.DEV ? "/hf-router" : HF_ROUTER_ORIGIN}/v1/chat/completions`,
  };
};

export interface GeminiMessage {
  role: "user" | "model";
  parts: { text: string }[];
}

/**
 * The UI expects token streaming callbacks, so we emit the full HF response via onDelta once.
 */
export async function streamGeminiChat({
  history,
  userMessage,
  systemInstruction,
  onDelta,
  onDone,
  onError,
  signal,
}: {
  history: GeminiMessage[];
  userMessage: string;
  systemInstruction?: string;
  onDelta: (text: string) => void;
  onDone: () => void;
  onError: (err: Error) => void;
  signal?: AbortSignal;
}) {
  const { token, model, url } = getHfConfig();

  const messages: Array<{ role: "system" | "user" | "assistant"; content: string }> = [];

  if (systemInstruction?.trim()) {
    messages.push({ role: "system", content: systemInstruction.trim() });
  }

  for (const message of history) {
    const text = message.parts.map((p) => p.text).join("\n").trim();
    if (!text) continue;
    messages.push({
      role: message.role === "user" ? "user" : "assistant",
      content: text,
    });
  }

  messages.push({ role: "user", content: userMessage.trim() });

  const body = {
    model,
    messages,
    stream: false,
    max_tokens: 420,
    temperature: 0.35,
    top_p: 0.9,
  };

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal,
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`Hugging Face API error ${response.status}: ${errText}`);
    }

    const payload = await response.json();

    const generatedText = payload?.choices?.[0]?.message?.content;

    if (!generatedText || typeof generatedText !== "string") {
      throw new Error("Hugging Face returned an empty response.");
    }

    onDelta(generatedText);

    onDone();
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      onDone();
      return;
    }
    if (err instanceof TypeError && /Failed to fetch/i.test(err.message)) {
      onError(
        new Error(
          "Network/CORS error reaching Hugging Face. In development, ensure Vite proxy is running and restart `npm run dev`.",
        ),
      );
      return;
    }
    onError(err instanceof Error ? err : new Error(String(err)));
  }
}
