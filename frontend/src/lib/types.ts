export type ApprovalDecision = "approve" | "reject" | "force_dry_run";

export interface ToolMeta {
  name: string;
  description: string;
  is_destructive: boolean;
  parameters_schema: Record<string, unknown>;
}

export interface ToolCategory {
  name: string;
  tools: ToolMeta[];
}

export type ChatEvent =
  | { type: "message_delta"; text: string }
  | { type: "tool_call_proposed"; call_id: string; name: string; args: Record<string, unknown> }
  | { type: "tool_call_pending_approval"; call_id: string; name: string; args: Record<string, unknown> }
  | {
      type: "tool_call_executed";
      call_id: string;
      name: string;
      args: Record<string, unknown>;
      result: unknown;
      duration_ms: number;
      dry_run_forced: boolean;
    }
  | { type: "error"; message: string }
  | { type: "final" };
