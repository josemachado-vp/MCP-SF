import { useState } from "react";
import type { ToolCategory } from "../lib/types";

interface Props {
  categories: ToolCategory[];
  onPickTool: (name: string) => void;
}

export function Sidebar({ categories, onPickTool }: Props) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const toggle = (name: string) =>
    setOpen((s) => ({ ...s, [name]: !s[name] }));

  return (
    <aside className="w-[280px] h-full bg-bg-soft border-r border-gray-200 flex flex-col">
      <div className="p-4 border-b border-gray-200 flex items-center gap-3">
        <img
          src="/veritas-prime-logo.jpg"
          alt="Veritas Prime"
          className="h-9 w-auto"
        />
      </div>
      <nav className="flex-1 overflow-y-auto py-2">
        {categories.map((cat) => (
          <div key={cat.name}>
            <button
              type="button"
              onClick={() => toggle(cat.name)}
              className="w-full text-left px-4 py-2 text-sm font-semibold text-navy hover:bg-white"
            >
              {cat.name}
              <span className="float-right text-gray-secondary">
                {open[cat.name] ? "−" : "+"}
              </span>
            </button>
            {open[cat.name] && (
              <ul className="pb-1">
                {cat.tools.map((t) => (
                  <li key={t.name}>
                    <button
                      type="button"
                      onClick={() => onPickTool(t.name)}
                      className="w-full text-left px-6 py-1.5 text-xs font-mono text-gray-700 hover:text-navy hover:bg-white flex items-center gap-2"
                      title={t.description}
                    >
                      <span className="truncate">{t.name}</span>
                      {t.is_destructive && (
                        <span className="text-[10px] uppercase tracking-wide text-danger">
                          ⚠
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </nav>
    </aside>
  );
}
