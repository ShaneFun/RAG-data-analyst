import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// The model answers in Markdown (bold numbers, lists, small tables). Raw HTML is not rendered.
export default function Answer({ text }: { text: string }) {
  return (
    <div className="mt-6 space-y-3 text-lg leading-relaxed [&_li]:ml-5 [&_ol]:list-decimal [&_strong]:font-semibold [&_ul]:list-disc">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <p className="font-semibold">{children}</p>,
          h2: ({ children }) => <p className="font-semibold">{children}</p>,
          h3: ({ children }) => <p className="font-semibold">{children}</p>,
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-base">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-line px-2 py-1 text-left font-medium">{children}</th>
          ),
          td: ({ children }) => <td className="border-b border-line px-2 py-1">{children}</td>,
          code: ({ children }) => <code className="font-mono text-base">{children}</code>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
