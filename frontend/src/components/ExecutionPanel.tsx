interface Execution {
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  duration_ms: number;
  dry_run_forced: boolean;
}

interface Props {
  last: Execution | null;
}

export function ExecutionPanel({ last }: Props) {
  if (!last) {
    return (
      <aside className="w-[360px] h-full border-l border-gray-200 bg-bg-soft p-4 text-sm text-gray-secondary">
        No tool calls yet.
      </aside>
    );
  }
  return (
    <aside className="w-[360px] h-full border-l border-gray-200 bg-bg-soft flex flex-col">
      <header className="px-4 py-3 border-b border-gray-200">
        <h3 className="text-navy font-semibold text-sm">Last execution</h3>
        <div className="mt-1 flex items-center gap-2 text-xs">
          <code className="font-mono text-navy">{last.name}</code>
          <span className="text-gray-secondary">{last.duration_ms} ms</span>
          {last.dry_run_forced && (
            <span className="text-success uppercase tracking-wide">dry-run</span>
          )}
        </div>
      </header>
      <section className="px-4 py-3 border-b border-gray-200">
        <h4 className="text-xs uppercase tracking-wide text-gray-secondary mb-1">Args</h4>
        <pre className="text-xs bg-white border border-gray-200 rounded p-2 overflow-auto max-h-[180px]">
{JSON.stringify(last.args, null, 2)}
        </pre>
      </section>
      <section className="px-4 py-3 flex-1 overflow-auto">
        <h4 className="text-xs uppercase tracking-wide text-gray-secondary mb-1">Result</h4>
        <pre className="text-xs bg-white border border-gray-200 rounded p-2 overflow-auto">
{JSON.stringify(last.result, null, 2)}
        </pre>
      </section>
    </aside>
  );
}
