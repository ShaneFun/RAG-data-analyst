export type ChartHint = { type: "line" | "bar" | "none"; x: string | null; y: string | null };

export type Step = {
  tool: "search_knowledge" | "run_sql" | string;
  input: Record<string, unknown>;
  ok: boolean;
  summary: string;
};

export type AskResponse = {
  answer: string;
  sql: string[];
  columns: string[];
  rows: (string | number | null)[][];
  chart_hint: ChartHint;
  steps: Step[];
  usage: { input_tokens: number; output_tokens: number; cost_usd: number };
  latency_ms: number;
  stopped_early: boolean;
};

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class AskError extends Error {}

async function post(path: string, question: string): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    throw new AskError(`Can't reach the analyst API at ${API_URL}. Check that the backend is running.`);
  }
  if (response.status === 429) {
    throw new AskError(
      "The demo's question limit has been reached (10 an hour per visitor, 200 a day in total). Try again later.",
    );
  }
  if (response.status === 422) {
    throw new AskError("Questions need to be between 1 and 500 characters.");
  }
  if (response.status === 503) {
    throw new AskError("The AI service didn't respond. Try again in a moment.");
  }
  if (!response.ok) {
    throw new AskError(`The analyst API returned an error (${response.status}).`);
  }
  return response;
}

export async function ask(question: string): Promise<AskResponse> {
  return (await post("/ask", question)).json();
}

export type StreamEvent =
  | { type: "step"; step: Step }
  | { type: "token"; text: string }
  | { type: "result"; result: AskResponse }
  | { type: "error"; message: string };

/** POST /ask/stream: calls onEvent for each Server-Sent Event, resolves with the final result. */
export async function askStream(
  question: string,
  onEvent: (event: StreamEvent) => void,
): Promise<AskResponse> {
  const response = await post("/ask/stream", question);
  if (!response.body) throw new AskError("This browser can't read streamed responses.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: AskResponse | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n"); // an SSE event ends with a blank line
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const data = block.split("\n").find((line) => line.startsWith("data: "));
      if (!data) continue;
      const event = JSON.parse(data.slice(6)) as StreamEvent;
      if (event.type === "error") throw new AskError(event.message);
      if (event.type === "result") result = event.result;
      onEvent(event);
    }
  }
  if (!result) throw new AskError("The answer stopped before it finished. Try again.");
  return result;
}
