import { useEffect, useRef, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { Chat, type ChatMessage } from "./components/Chat";
import { ExecutionPanel } from "./components/ExecutionPanel";
import { ApprovalModal } from "./components/ApprovalModal";
import { approveTool, listTools, streamChat } from "./lib/api";
import type { ChatEvent, ToolCategory } from "./lib/types";

interface PendingApproval {
  callId: string;
  name: string;
  args: Record<string, unknown>;
}
interface Execution {
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  duration_ms: number;
  dry_run_forced: boolean;
}

export default function App() {
  const [categories, setCategories] = useState<ToolCategory[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [lastExec, setLastExec] = useState<Execution | null>(null);
  const [pendingTool, setPendingTool] = useState<string | null>(null);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const chatIdRef = useRef<string>(crypto.randomUUID());
  const inputAppendRef = useRef<((s: string) => void) | null>(null);

  useEffect(() => {
    listTools().then((r) => setCategories(r.categories)).catch((e) => {
      setMessages((m) => [...m, { role: "assistant", text: `Backend unreachable: ${e.message}` }]);
    });
  }, []);

  const handleSend = async (text: string) => {
    setMessages((m) => [...m, { role: "user", text }]);
    const ctrl = new AbortController();
    let assistantBuffer = "";
    try {
      await streamChat(chatIdRef.current, text, (ev: ChatEvent) => {
        switch (ev.type) {
          case "message_delta":
            assistantBuffer += ev.text;
            setMessages((m) => {
              const copy = [...m];
              const last = copy[copy.length - 1];
              if (last?.role === "assistant") {
                copy[copy.length - 1] = { role: "assistant", text: assistantBuffer };
              } else {
                copy.push({ role: "assistant", text: assistantBuffer });
              }
              return copy;
            });
            break;
          case "tool_call_proposed":
            setPendingTool(ev.name);
            break;
          case "tool_call_pending_approval":
            setPendingApproval({ callId: ev.call_id, name: ev.name, args: ev.args });
            break;
          case "tool_call_executed":
            setPendingTool(null);
            setLastExec({
              name: ev.name, args: ev.args, result: ev.result,
              duration_ms: ev.duration_ms, dry_run_forced: ev.dry_run_forced,
            });
            setMessages((m) => [...m, {
              role: "tool",
              text: `${ev.name} → ${JSON.stringify(ev.result).slice(0, 240)}…`,
            }]);
            break;
          case "error":
            setMessages((m) => [...m, { role: "assistant", text: `⚠ ${ev.message}` }]);
            break;
          case "final":
            assistantBuffer = "";
            setPendingTool(null);
            break;
        }
      }, ctrl.signal);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessages((m) => [...m, { role: "assistant", text: `Stream error: ${msg}` }]);
    }
  };

  const handleApprove = async (decision: "approve" | "reject" | "force_dry_run") => {
    if (!pendingApproval) return;
    await approveTool(chatIdRef.current, pendingApproval.callId, decision);
    setPendingApproval(null);
  };

  return (
    <div className="h-screen flex">
      <Sidebar
        categories={categories}
        onPickTool={(name) => inputAppendRef.current?.(`@${name} `)}
      />
      <Chat messages={messages} pendingToolName={pendingTool} onSend={handleSend} />
      <ExecutionPanel last={lastExec} />
      {pendingApproval && (
        <ApprovalModal
          toolName={pendingApproval.name}
          args={pendingApproval.args}
          onDecision={handleApprove}
        />
      )}
    </div>
  );
}
