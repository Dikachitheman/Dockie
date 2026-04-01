import { ArrowLeft, BookOpen, FileText, Mail, Table2 } from "lucide-react";
import type { AgentOutput } from "@/lib/standby-agents";

// Theme-consistent type configs — no off-brand purple/green gradients
const TYPE_CONFIG: Record<string, {
  icon: React.ElementType;
  iconBg: string;
  iconColor: string;
  headerBg: string;
  accentText: string;
  borderColor: string;
}> = {
  report:      { icon: FileText,  iconBg: "bg-[#eef6ff]",  iconColor: "text-apple-blue",      headerBg: "bg-[#f5f8fc]",  accentText: "text-apple-blue",      borderColor: "border-[#d0dff5]" },
  spreadsheet: { icon: Table2,    iconBg: "bg-[#f5f5f7]",  iconColor: "text-[#3c3c43]",       headerBg: "bg-[#f5f5f7]",  accentText: "text-[#3c3c43]",       borderColor: "border-[#d2d2d7]" },
  document:    { icon: BookOpen,  iconBg: "bg-[#f5f5f7]",  iconColor: "text-apple-secondary", headerBg: "bg-[#f5f5f7]",  accentText: "text-apple-secondary", borderColor: "border-[#d2d2d7]" },
  email:       { icon: Mail,      iconBg: "bg-[#fff4ec]",  iconColor: "text-orange-500",      headerBg: "bg-[#fff8f3]",  accentText: "text-orange-500",      borderColor: "border-[#ffd6b8]" },
};

const FALLBACK_CONFIG = {
  icon: FileText,
  iconBg: "bg-[#f5f5f7]",
  iconColor: "text-apple-secondary",
  headerBg: "bg-[#f5f5f7]",
  accentText: "text-apple-secondary",
  borderColor: "border-[#d2d2d7]",
};

// ─── Table parser for spreadsheet content ────────────────────────────────────

function parseTableContent(content: string): string[][] | null {
  const lines = content.trim().split("\n").filter((l) => l.trim());
  if (lines.length < 2) return null;

  // Pipe-delimited markdown table
  if (lines[0].includes("|")) {
    const dataLines = lines.filter((l) => !/^\s*\|[\s\-:]+\|\s*$/.test(l));
    const rows = dataLines.map((l) => {
      const parts = l.split("|").map((c) => c.trim());
      const start = parts[0] === "" ? 1 : 0;
      const end = parts[parts.length - 1] === "" ? parts.length - 1 : parts.length;
      return parts.slice(start, end);
    }).filter((row) => row.length > 1);
    if (rows.length >= 2) return rows;
  }

  // TSV
  if (lines[0].includes("\t")) {
    return lines.map((l) => l.split("\t").map((c) => c.trim()));
  }

  // CSV (simple — no quoted commas)
  const commaCount = (lines[0].match(/,/g) ?? []).length;
  if (commaCount >= 1) {
    const rows = lines.map((l) => l.split(",").map((c) => c.trim().replace(/^"|"$/g, "")));
    const colCount = rows[0].length;
    if (rows.every((r) => r.length === colCount)) return rows;
  }

  return null;
}

// ─── Content renderers ────────────────────────────────────────────────────────

function SpreadsheetContent({ content }: { content: string }) {
  const rows = parseTableContent(content);

  if (!rows || rows.length < 2) {
    return (
      <div className="overflow-x-auto rounded-[16px] border border-[#d2d2d7] bg-[#f5f5f7]">
        <pre className="whitespace-pre-wrap break-words p-5 font-mono text-[12.5px] leading-relaxed text-apple-text">
          {content}
        </pre>
      </div>
    );
  }

  const [header, ...body] = rows;

  return (
    <div className="overflow-x-auto rounded-[16px] border border-[#d2d2d7]">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="bg-[#f5f5f7]">
            {header.map((cell, i) => (
              <th
                key={i}
                className="border-b border-[#d2d2d7] px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-apple-secondary whitespace-nowrap"
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, ri) => (
            <tr key={ri} className={ri % 2 === 0 ? "bg-white" : "bg-[#fafafa]"}>
              {row.map((cell, ci) => (
                <td key={ci} className="border-b border-[#ebebeb] px-4 py-2.5 text-apple-text">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentContent({ content }: { content: string }) {
  const lines = content.split("\n");

  return (
    <div className="flex justify-center py-2">
      <div
        className="w-full max-w-[680px] rounded-[4px] bg-white px-12 py-10"
        style={{ boxShadow: "0 1px 4px rgba(0,0,0,0.08), 0 4px 20px rgba(0,0,0,0.10)" }}
      >
        {lines.map((line, i) => {
          if (!line.trim()) return <div key={i} className="h-4" />;
          if (line.startsWith("# "))
            return (
              <h1 key={i} className="mb-3 mt-6 text-[22px] font-bold leading-tight text-[#1d1d1f] first:mt-0">
                {line.slice(2)}
              </h1>
            );
          if (line.startsWith("## "))
            return (
              <h2 key={i} className="mb-2 mt-5 text-[17px] font-semibold text-[#1d1d1f]">
                {line.slice(3)}
              </h2>
            );
          if (line.startsWith("### "))
            return (
              <h3 key={i} className="mb-1 mt-4 text-[14px] font-semibold text-[#1d1d1f]">
                {line.slice(4)}
              </h3>
            );
          if (line.match(/^[-*] /))
            return (
              <div key={i} className="flex items-start gap-2.5 py-0.5">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#6e6e73]" />
                <p className="text-[14px] leading-relaxed text-[#1d1d1f]">{line.slice(2)}</p>
              </div>
            );
          return (
            <p key={i} className="py-0.5 text-[14px] leading-[1.7] text-[#1d1d1f]">
              {line}
            </p>
          );
        })}
      </div>
    </div>
  );
}

function ReportContent({ content }: { content: string }) {
  const lines = content.split("\n");

  return (
    <div className="space-y-0.5">
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-3" />;
        if (line.startsWith("# "))
          return (
            <h1
              key={i}
              className="mt-6 border-b border-apple-divider pb-2 text-[18px] font-bold text-apple-text first:mt-0"
            >
              {line.slice(2)}
            </h1>
          );
        if (line.startsWith("## "))
          return (
            <div key={i} className="mt-5 flex items-center gap-2 pb-1">
              <span className="inline-block h-4 w-0.5 rounded-full bg-apple-blue" />
              <h2 className="text-[15px] font-semibold text-apple-text">{line.slice(3)}</h2>
            </div>
          );
        if (line.startsWith("### "))
          return (
            <h3 key={i} className="mt-3 text-[11px] font-semibold uppercase tracking-[0.1em] text-apple-secondary">
              {line.slice(4)}
            </h3>
          );
        if (line.match(/^[-*] /))
          return (
            <div key={i} className="flex items-start gap-2.5 py-0.5 pl-2">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-apple-blue" />
              <p className="text-[13px] leading-relaxed text-apple-text">{line.slice(2)}</p>
            </div>
          );
        return (
          <p key={i} className="text-[13px] leading-[1.7] text-apple-text">
            {line}
          </p>
        );
      })}
    </div>
  );
}

function EmailContent({ content }: { content: string }) {
  const lines = content.split("\n");

  return (
    <div className="overflow-hidden rounded-[16px] border border-[#ffd6b8]">
      <div className="border-b border-[#ffd6b8] bg-[#fff8f3] px-5 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-orange-400">Email draft</p>
      </div>
      <div className="bg-white px-6 py-5">
        {lines.map((line, i) => {
          if (!line.trim()) return <div key={i} className="h-3" />;
          const fieldMatch = line.match(/^(To|From|Subject|Date|CC|BCC):\s*(.*)$/i);
          if (fieldMatch)
            return (
              <div key={i} className="flex gap-2 border-b border-[#f5f5f7] py-1.5 last:border-0">
                <span className="w-16 shrink-0 text-[12px] font-semibold text-apple-secondary">{fieldMatch[1]}</span>
                <span className="text-[13px] text-apple-text">{fieldMatch[2]}</span>
              </div>
            );
          return (
            <p key={i} className="pt-1 text-[13px] leading-relaxed text-apple-text">
              {line}
            </p>
          );
        })}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface AgentOutputDetailViewProps {
  output: AgentOutput | null;
  onBack: () => void;
}

export default function AgentOutputDetailView({ output, onBack }: AgentOutputDetailViewProps) {
  if (!output) {
    return (
      <div className="flex flex-1 items-center justify-center bg-white p-8">
        <div className="apple-card w-full max-w-2xl p-8 text-center">
          <p className="text-sm font-medium text-apple-text">Output not found</p>
          <p className="mt-2 text-sm text-apple-secondary">
            The full output could not be loaded. It may have been deleted or is no longer available.
          </p>
          <button onClick={onBack} className="apple-btn-secondary mt-4 px-4 py-2 text-sm">
            Back
          </button>
        </div>
      </div>
    );
  }

  const cfg = TYPE_CONFIG[output.outputType] ?? FALLBACK_CONFIG;
  const TypeIcon = cfg.icon;

  return (
    <div className="flex flex-1 overflow-y-auto bg-[#f5f5f7] p-4 sm:p-8 scrollbar-thin">
      <div className="mx-auto w-full max-w-4xl space-y-4 sm:space-y-5">

        {/* Header card */}
        <div className={`overflow-hidden rounded-[24px] border bg-white shadow-apple ${cfg.borderColor}`}>
          <div className={`${cfg.headerBg} px-6 py-5`}>
            <div className="flex items-start justify-between gap-4">
              <button
                type="button"
                onClick={onBack}
                className="inline-flex items-center gap-2 rounded-full border border-apple-divider bg-white/80 px-3 py-1.5 text-xs font-medium text-apple-text backdrop-blur-sm transition-colors hover:bg-white"
              >
                <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
                Back
              </button>
            </div>
            <div className="mt-4 flex items-center gap-3">
              <div className={`rounded-[12px] ${cfg.iconBg} p-2.5`}>
                <TypeIcon className={`h-5 w-5 ${cfg.iconColor}`} strokeWidth={1.5} />
              </div>
              <div>
                <p className={`text-[10px] font-semibold uppercase tracking-[0.18em] ${cfg.accentText}`}>
                  {output.outputType}
                </p>
                <h1 className="text-xl font-semibold text-apple-text">{output.title}</h1>
              </div>
            </div>
            {output.previewText && (
              <p className="mt-3 max-w-3xl text-sm leading-relaxed text-apple-secondary">{output.previewText}</p>
            )}
          </div>
        </div>

        {/* Meta row */}
        <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4">
          {[
            { label: "Type", value: output.outputType, className: `capitalize ${cfg.accentText}` },
            { label: "Created", value: output.createdAt ? new Date(output.createdAt).toLocaleString() : "Pending" },
            { label: "Shipment", value: output.shipmentId ?? "All shipments" },
            { label: "Agent", value: output.agentId ?? "N/A" },
          ].map(({ label, value, className }) => (
            <div key={label} className="rounded-[18px] border border-apple-divider bg-white px-4 py-4 shadow-apple">
              <p className="text-[11px] uppercase tracking-[0.12em] text-apple-secondary">{label}</p>
              <p className={`mt-2 text-sm font-semibold text-apple-text ${className ?? ""}`}>{value}</p>
            </div>
          ))}
        </div>

        {/* Content area */}
        <div className="rounded-[24px] border border-apple-divider bg-white p-6 shadow-apple">
          <div className="mb-4 flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-apple-text">
              {output.outputType === "spreadsheet"
                ? "Spreadsheet"
                : output.outputType === "document"
                  ? "Document"
                  : output.outputType === "report"
                    ? "Report"
                    : output.outputType === "email"
                      ? "Email"
                      : "Output"}
            </p>
            <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] ${cfg.iconBg} ${cfg.iconColor}`}>
              {output.outputType}
            </span>
          </div>

          {output.outputType === "spreadsheet" ? (
            <SpreadsheetContent content={output.content} />
          ) : output.outputType === "document" ? (
            <DocumentContent content={output.content} />
          ) : output.outputType === "report" ? (
            <ReportContent content={output.content} />
          ) : output.outputType === "email" ? (
            <EmailContent content={output.content} />
          ) : (
            <div className="rounded-[16px] border border-apple-divider bg-[#f5f5f7] p-5">
              <pre className="whitespace-pre-wrap break-words text-sm leading-relaxed text-apple-text">
                {output.content}
              </pre>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
