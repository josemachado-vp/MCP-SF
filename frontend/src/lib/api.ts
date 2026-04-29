import { fetchEventSource } from "@microsoft/fetch-event-source";
import type { ApprovalDecision, ChatEvent, ToolCategory } from "./types";

const BASE = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8001";

export interface ConfigSnapshot {
  sf: {
    api_host: string;
    company_id: string;
    user_id: string;
    password_masked: string;
    ias_host: string;
    oidc_client_id: string;
    oidc_client_secret_masked: string;
    ias_dependency_name: string;
  };
  gemini: { api_key_masked: string; model: string };
}

export async function listTools(): Promise<{ categories: ToolCategory[] }> {
  const r = await fetch(`${BASE}/api/tools`);
  if (!r.ok) throw new Error(`listTools failed: ${r.status}`);
  return r.json();
}

export async function getConfig(): Promise<ConfigSnapshot> {
  const r = await fetch(`${BASE}/api/config`);
  if (!r.ok) throw new Error(`getConfig failed: ${r.status}`);
  return r.json();
}

export async function reloadConfig(): Promise<ConfigSnapshot & { ok: boolean }> {
  const r = await fetch(`${BASE}/api/config/reload`, { method: "POST" });
  if (!r.ok) throw new Error(`reloadConfig failed: ${r.status}`);
  return r.json();
}

export async function testGemini(): Promise<{ ok: boolean; model: string; reply?: string; error?: string }> {
  const r = await fetch(`${BASE}/api/config/test-gemini`, { method: "POST" });
  if (!r.ok) throw new Error(`testGemini failed: ${r.status}`);
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
        const parsed = JSON.parse(ev.data) as ChatEvent;
        // eslint-disable-next-line no-console
        console.debug("[SSE]", ev.event, parsed);
        onEvent(parsed);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("[SSE] malformed", ev.data, err);
      }
    },
    onerror(err) {
      throw err;
    },
  });
}
