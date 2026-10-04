"use client";

import { FormEvent, useState } from "react";

import { ask, AskError, type AskResponse } from "@/lib/api";
import ResultChart from "./ResultChart";
import ResultTable from "./ResultTable";
import StepTrace from "./StepTrace";

const EXAMPLES = [
  "Why did North sales drop in March 2025?",
  "Which supplier has an unusually high refund rate?",
  "How did monthly revenue change over 2024?",
  "What is the average order value by channel?",
];

export default function Analyst() {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(text: string) {
    const q = text.trim();
    if (!q || loading) return;
    setQuestion(q);
    setAsked(q);
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await ask(q));
    } catch (e) {
      setError(e instanceof AskError ? e.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    submit(question);
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-5 py-10 md:px-8 md:py-14">
      <header className="max-w-2xl">
        <p className="text-sm font-medium text-petal">Larkspur Market</p>
        <h1 className="mt-2 text-3xl font-semibold leading-tight tracking-tight md:text-4xl">
          Ask the shop&apos;s data a question
        </h1>
        <p className="mt-3 text-base leading-relaxed text-night-soft">
          An AI analyst reads the shop&apos;s database guide, writes read-only SQL, checks its own
          work and answers in plain English. Two years of orders, 2024 to 2025.
        </p>
      </header>

      <form onSubmit={onSubmit} className="mt-8 max-w-3xl">
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={500}
            placeholder="e.g. Which region had the most revenue last year?"
            className="min-w-0 flex-1 rounded-lg border border-line bg-paper px-4 py-3 text-base placeholder:text-night-soft/70 focus:border-petal focus:outline-none"
          />
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="rounded-lg bg-petal px-6 py-3 font-medium text-white transition-opacity disabled:opacity-40"
          >
            {loading ? "Analysing…" : "Ask"}
          </button>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => submit(example)}
              disabled={loading}
              className="rounded-full bg-mist px-3 py-1.5 text-left text-sm text-night-soft hover:text-night disabled:opacity-50"
            >
              {example}
            </button>
          ))}
        </div>
      </form>

      {error && (
        <p role="alert" className="mt-8 max-w-3xl rounded-lg bg-rust-soft px-4 py-3 text-rust">
          {error}
        </p>
      )}

      {loading && (
        <p className="mt-10 text-night-soft" aria-live="polite">
          Reading the database guide and running queries. This usually takes 10 to 30 seconds.
        </p>
      )}

      {result && (
        <section className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <div>
            <p className="text-sm text-night-soft">You asked</p>
            <p className="mt-1 font-medium">{asked}</p>
            <div className="mt-6 whitespace-pre-line text-lg leading-relaxed">{result.answer}</div>
            <p className="mt-4 text-sm text-night-soft">
              {(result.latency_ms / 1000).toFixed(1)} s ·{" "}
              {(result.usage.input_tokens + result.usage.output_tokens).toLocaleString()} tokens · $
              {result.usage.cost_usd.toFixed(4)}
            </p>
            <StepTrace steps={result.steps} stoppedEarly={result.stopped_early} />
          </div>

          <div className="min-w-0">
            {result.chart_hint.type !== "none" && (
              <ResultChart hint={result.chart_hint} columns={result.columns} rows={result.rows} />
            )}
            {result.rows.length > 0 ? (
              <ResultTable columns={result.columns} rows={result.rows} />
            ) : (
              <p className="rounded-lg bg-mist px-4 py-6 text-night-soft">
                No table for this answer: the analyst didn&apos;t need to run a query.
              </p>
            )}
            {result.sql.length > 0 && (
              <details className="mt-6 rounded-lg border border-line">
                <summary className="cursor-pointer px-4 py-3 text-sm font-medium">
                  SQL that produced this ({result.sql.length}{" "}
                  {result.sql.length === 1 ? "query" : "queries"})
                </summary>
                <div className="space-y-3 border-t border-line px-4 py-4">
                  {result.sql.map((sql, i) => (
                    <pre
                      key={i}
                      className="overflow-x-auto whitespace-pre-wrap rounded bg-mist p-3 font-mono text-sm leading-relaxed"
                    >
                      {sql}
                    </pre>
                  ))}
                </div>
              </details>
            )}
          </div>
        </section>
      )}
    </main>
  );
}
