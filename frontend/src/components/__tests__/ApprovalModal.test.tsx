import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ApprovalModal } from "../ApprovalModal";

describe("ApprovalModal", () => {
  it("renders the tool name and args", () => {
    render(
      <ApprovalModal
        toolName="execute_upsert"
        args={{ records: [{ id: 1 }], dry_run: false }}
        onDecision={() => {}}
      />,
    );
    expect(screen.getByText(/execute_upsert/)).toBeInTheDocument();
    expect(screen.getAllByText(/dry_run/).length).toBeGreaterThan(0);
  });

  it("emits the right decision", () => {
    const cb = vi.fn();
    render(<ApprovalModal toolName="execute_upsert" args={{}} onDecision={cb} />);
    fireEvent.click(screen.getByText(/Approve/));
    fireEvent.click(screen.getByText(/Reject/));
    fireEvent.click(screen.getByText(/Force dry/i));
    expect(cb.mock.calls.map((c) => c[0])).toEqual([
      "approve", "reject", "force_dry_run",
    ]);
  });
});
