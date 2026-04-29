import { fetchEventSource } from "@microsoft/fetch-event-source";
import type { ApprovalDecision, ChatEvent, ToolCategory } from "./types";

const BASE = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8001";

export async function listTools(): Promise<{ categories: ToolCategory[] }> {
  const r = await fetch(`${BASE}/api/tools`);
  if (!r.ok) throw new Error(`listTools failed: ${r.status}`);
  return r.json();
}

export async function approveTool(
  chatId: string,
  callId: string,
  decision: ApprovalDecision,
): Promise<void> {
  const r = await fetch(`${BASE}/api/chat/${chatId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ call_id: callId, decision }),
  });
  if (!r.ok) throw new Error(`approve failed: ${r.status}`);
}

export async function streamChat(
  chatId: string,
  message: string,
  onEvent: (e: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  await fetchEventSource(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, message }),
    signal,
    onmessage(ev) {
      if (!ev.data) return;
      try {
        onEvent(JSON.parse(ev.data) as ChatEvent);
      } catch {
        /* ignore malformed */
      }
    },
    onerror(err) {
      throw err;
    },
  });
}
