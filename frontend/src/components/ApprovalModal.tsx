import type { ApprovalDecision } from "../lib/types";

interface Props {
  toolName: string;
  args: Record<string, unknown>;
  onDecision: (d: ApprovalDecision) => void;
}

export function ApprovalModal({ toolName, args, onDecision }: Props) {
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center">
      <div className="bg-white rounded-lg shadow-xl w-[560px] max-w-[90vw] border border-gray-200">
        <header className="px-5 py-4 border-b border-gray-200">
          <h2 className="text-navy font-semibold">
            Confirm destructive tool
          </h2>
          <p className="text-xs text-gray-secondary mt-1">
            Gemini wants to execute <code className="font-mono">{toolName}</code>
          </p>
        </header>
        <div className="px-5 py-4">
          <pre className="text-xs bg-bg-soft rounded p-3 max-h-[260px] overflow-auto border border-gray-200">
{JSON.stringify(args, null, 2)}
          </pre>
        </div>
        <footer className="px-5 py-3 border-t border-gray-200 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => onDecision("reject")}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-bg-soft"
          >
            Reject
          </button>
          <button
            type="button"
            onClick={() => onDecision("force_dry_run")}
            className="px-3 py-1.5 text-sm bg-success text-white rounded hover:opacity-90"
          >
            Force dry_run
          </button>
          <button
            type="button"
            onClick={() => onDecision("approve")}
            className="px-3 py-1.5 text-sm bg-navy text-white rounded hover:bg-navy-dark"
          >
            Approve
          </button>
        </footer>
      </div>
    </div>
  );
}
