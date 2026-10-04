# Frontend

Next.js 16 (App Router) + Tailwind v4 + recharts. One page: ask a question, read the answer,
see the evidence (chart, table, SQL) and the step trace showing how the agent got there.

```bash
cp .env.example .env.local   # points at the backend, default http://localhost:8000
npm install
npm run dev                   # http://localhost:3000
```

- `lib/api.ts`: typed client for `POST /ask`, turns HTTP errors (429, 422, 503) into readable messages.
- `components/Analyst.tsx`: the page (form, example questions, answer, evidence).
- `components/StepTrace.tsx`: numbered timeline of tool calls; failed SQL steps are marked so the self-correction is visible.
- `components/ResultChart.tsx`: line or bar chart chosen by the backend's `chart_hint`.
- `components/ResultTable.tsx`: the result rows.
