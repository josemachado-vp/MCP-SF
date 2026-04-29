import { useRef } from "react";

export interface ChatMessage {
  role: "user" | "assistant" | "tool";
  text: string;
}

interface Props {
  messages: ChatMessage[];
  pendingToolName: string | null;
  onSend: (text: string) => void;
}

export function Chat({ messages, pendingToolName, onSend }: Props) {
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const v = inputRef.current?.value.trim();
    if (!v) return;
    onSend(v);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <main className="flex-1 h-full flex flex-col bg-white">
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.map((m, i) => (
          <div
            key={i}
            className={
              m.role === "user"
                ? "max-w-[80%] ml-auto bg-navy text-white rounded-lg px-3 py-2 text-sm whitespace-pre-wrap"
                : m.role === "tool"
                ? "max-w-[80%] bg-bg-soft border border-gray-200 rounded-lg px-3 py-2 text-xs font-mono whitespace-pre-wrap"
                : "max-w-[80%] bg-bg-soft border border-gray-200 rounded-lg px-3 py-2 text-sm whitespace-pre-wrap"
            }
          >
            {m.text}
          </div>
        ))}
        {pendingToolName && (
          <div className="text-xs text-gray-secondary italic">
            Gemini is calling <code className="font-mono">{pendingToolName}</code>…
          </div>
        )}
      </div>
      <div className="border-t border-gray-200 p-3 flex gap-2">
        <textarea
          ref={inputRef}
          rows={2}
          placeholder="Ask Gemini something about your SF tenant…"
          className="flex-1 resize-none border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-navy"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button
          type="button"
          onClick={submit}
          className="px-4 py-2 bg-navy text-white rounded text-sm hover:bg-navy-dark"
        >
          Send
        </button>
      </div>
    </main>
  );
}
