import type { Step } from "@/lib/api";

function describe(step: Step): { title: string; detail: string } {
  if (step.tool === "search_knowledge") {
    return {
      title: `Looked up “${String(step.input.query ?? "")}”`,
      detail: step.ok ? `Found: ${step.summary}` : step.summary,
    };
  }
  if (step.tool === "run_sql") {
    return {
      title: step.ok ? "Ran a query" : "Query failed, so it tried again",
      detail: step.summary,
    };
  }
  return { title: `Called ${step.tool}`, detail: step.summary };
}

export default function StepTrace({ steps, stoppedEarly }: { steps: Step[]; stoppedEarly: boolean }) {
  if (steps.length === 0) return null;
  return (
    <div className="mt-8">
      <h2 className="text-sm font-medium text-night-soft">How the analyst got here</h2>
      <ol className="mt-4">
        {steps.map((step, i) => {
          const { title, detail } = describe(step);
          const last = i === steps.length - 1;
          return (
            <li key={i} className="relative flex gap-4 pb-5">
              {!last && (
                <span aria-hidden className="absolute left-[13px] top-7 h-[calc(100%-1.75rem)] w-px bg-line" />
              )}
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                  step.ok ? "bg-stem-soft text-stem" : "bg-rust-soft text-rust"
                }`}
              >
                {i + 1}
              </span>
              <div className="min-w-0 pt-0.5">
                <p className="font-medium">{title}</p>
                <p className="mt-0.5 break-words text-sm text-night-soft">{detail}</p>
              </div>
            </li>
          );
        })}
        <li className="flex gap-4">
          <span
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
              stoppedEarly ? "bg-rust-soft text-rust" : "bg-petal text-white"
            }`}
            aria-hidden
          >
            {stoppedEarly ? "!" : "✓"}
          </span>
          <p className="pt-0.5 font-medium">
            {stoppedEarly ? "Stopped at the step limit" : "Wrote the answer"}
          </p>
        </li>
      </ol>
    </div>
  );
}
