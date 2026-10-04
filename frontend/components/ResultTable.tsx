type Cell = string | number | null;

function format(value: Cell): string {
  if (value === null) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return value;
}

export default function ResultTable({ columns, rows }: { columns: string[]; rows: Cell[][] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full border-collapse text-sm">
        <thead className="bg-mist">
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col" className="px-4 py-2.5 text-left font-medium">
                {column.replaceAll("_", " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="border-t border-line">
              {row.map((cell, c) => (
                <td
                  key={c}
                  className={`px-4 py-2 ${typeof cell === "number" ? "text-right tabular-nums" : ""}`}
                >
                  {format(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 200 && (
        <p className="border-t border-line px-4 py-2 text-xs text-night-soft">
          Showing the first 200 rows.
        </p>
      )}
    </div>
  );
}
