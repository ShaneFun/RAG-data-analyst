"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartHint } from "@/lib/api";

type Cell = string | number | null;

export default function ResultChart({
  hint,
  columns,
  rows,
}: {
  hint: ChartHint;
  columns: string[];
  rows: Cell[][];
}) {
  if (!hint.x || !hint.y) return null;
  const xi = columns.indexOf(hint.x);
  const yi = columns.indexOf(hint.y);
  const data = rows.map((row) => ({
    x: hint.type === "line" ? String(row[xi]).slice(0, 7) : row[xi],
    y: row[yi],
  }));
  const label = hint.y.replaceAll("_", " ");

  const axes = (
    <>
      <CartesianGrid stroke="var(--line)" vertical={false} />
      <XAxis dataKey="x" tick={{ fill: "var(--night-soft)", fontSize: 12 }} tickLine={false} />
      <YAxis
        tick={{ fill: "var(--night-soft)", fontSize: 12 }}
        tickLine={false}
        axisLine={false}
        width={64}
      />
      <Tooltip
        formatter={(value) => [Number(value).toLocaleString(), label]}
        contentStyle={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 8 }}
      />
    </>
  );

  return (
    <figure className="mb-6">
      <figcaption className="mb-2 text-sm text-night-soft">
        {label} by {hint.x.replaceAll("_", " ")}
      </figcaption>
      <div className="h-64 w-full">
        <ResponsiveContainer>
          {hint.type === "line" ? (
            <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              {axes}
              <Line type="monotone" dataKey="y" stroke="var(--petal)" strokeWidth={2} dot={false} />
            </LineChart>
          ) : (
            <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              {axes}
              <Bar dataKey="y" fill="var(--petal)" radius={[4, 4, 0, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
