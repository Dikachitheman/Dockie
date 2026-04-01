import { ArrowLeft, FileSpreadsheet, FileText, Mail, Table2 } from "lucide-react";
import type { AgentOutput } from "@/lib/standby-agents";

const TYPE_CONFIG: Record<string, {
  icon: React.ElementType;
  iconBg: string;
  iconColor: string;
  headerGradient: string;
  accentText: string;
  borderColor: string;
}> = {
  report:      { icon: FileText,       iconBg: "bg-[#eef6ff]",  iconColor: "text-apple-blue",   headerGradient: "bg-[linear-gradient(135deg,#f0f7ff_0%,#e8f2ff_100%)]", accentText: "text-apple-blue",   borderColor: "border-[#c8deff]" },
  spreadsheet: { icon: Table2,          iconBg: "bg-[#edfaf3]",  iconColor: "text-emerald-600",  headerGradient: "bg-[linear-gradient(135deg,#f0fdf6_0%,#e6fbf0_100%)]", accentText: "text-emerald-600",  borderColor: "border-[#b8f0d4]" },
  document:    { icon: FileSpreadsheet, iconBg: "bg-[#f3eeff]",  iconColor: "text-violet-600",   headerGradient: "bg-[linear-gradient(135deg,#f8f4ff_0%,#f0eaff_100%)]", accentText: "text-violet-600",   borderColor: "border-[#d8c8ff]" },
  email:       { icon: Mail,            iconBg: "bg-[#fff4ec]",  iconColor: "text-orange-500",   headerGradient: "bg-[linear-gradient(135deg,#fff8f3_0%,#fff0e6_100%)]", accentText: "text-orange-500",   borderColor: "border-[#ffd6b8]" },
};

const FALLBACK_CONFIG = { icon: FileText, iconBg: "bg-apple-surface", iconColor: "text-apple-secondary", headerGradient: "bg-apple-surface", accentText: "text-apple-secondary", borderColor: "border-apple-divider" };

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
    <div className="flex flex-1 overflow-y-auto bg-white p-8 scrollbar-thin">
      <div className="mx-auto w-full max-w-4xl space-y-6">
        {/* Type-styled hero header */}
        <div className={`overflow-hidden rounded-[24px] border shadow-apple ${cfg.borderColor}`}>
          <div className={`${cfg.headerGradient} px-6 py-6`}>
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
            <div className="mt-5 flex items-center gap-3">
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

        <div className="grid gap-4 md:grid-cols-4">
          <div className="apple-card p-4">
            <p className="text-[11px] uppercase tracking-[0.12em] text-apple-secondary">Type</p>
            <p className={`mt-2 text-sm font-semibold capitalize ${cfg.accentText}`}>{output.outputType}</p>
          </div>
          <div className="apple-card p-4">
            <p className="text-[11px] uppercase tracking-[0.12em] text-apple-secondary">Created</p>
            <p className="mt-2 text-sm font-semibold text-apple-text">
              {output.createdAt ? new Date(output.createdAt).toLocaleString() : "Pending"}
            </p>
          </div>
          <div className="apple-card p-4">
            <p className="text-[11px] uppercase tracking-[0.12em] text-apple-secondary">Shipment</p>
            <p className="mt-2 text-sm font-semibold text-apple-text">{output.shipmentId ?? "All shipments"}</p>
          </div>
          <div className="apple-card p-4">
            <p className="text-[11px] uppercase tracking-[0.12em] text-apple-secondary">Agent</p>
            <p className="mt-2 text-sm font-semibold text-apple-text">{output.agentId ?? "N/A"}</p>
          </div>
        </div>

        <div className="apple-card p-6">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-apple-text">Full output</p>
            <span className="apple-badge-blue">{output.outputType}</span>
          </div>
          {output.outputType === "spreadsheet" ? (
            <div className="mt-4 overflow-x-auto rounded-[16px] border border-apple-divider bg-apple-surface">
              <pre className="whitespace-pre-wrap break-words p-4 font-mono text-[13px] leading-relaxed text-apple-text">
                {output.content}
              </pre>
            </div>
          ) : (
            <pre className="mt-4 whitespace-pre-wrap break-words rounded-[16px] bg-apple-surface p-4 text-sm leading-relaxed text-apple-text">
              {output.content}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
