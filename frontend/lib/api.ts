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

export async function ask(question: string): Promise<AskResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    throw new AskError(`Can't reach the analyst API at ${API_URL}. Check that the backend is running.`);
  }
  if (response.status === 429) {
    throw new AskError("This demo allows 10 questions an hour per visitor. Try again later.");
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
  return response.json();
}
