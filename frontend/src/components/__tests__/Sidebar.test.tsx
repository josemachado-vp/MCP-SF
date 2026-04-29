import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Sidebar } from "../Sidebar";

const fakeCats = [
  { name: "Discovery", tools: [
    { name: "list_entities", description: "List entities", is_destructive: false, parameters_schema: {} },
  ]},
  { name: "Data Import", tools: [
    { name: "execute_upsert", description: "Upsert", is_destructive: true, parameters_schema: {} },
  ]},
];

describe("Sidebar", () => {
  it("renders categories and tools", () => {
    render(<Sidebar categories={fakeCats} onPickTool={() => {}} />);
    expect(screen.getByText("Discovery")).toBeInTheDocument();
    expect(screen.getByText("Data Import")).toBeInTheDocument();
  });

  it("invokes onPickTool with the tool name", () => {
    const onPick = vi.fn();
    render(<Sidebar categories={fakeCats} onPickTool={onPick} />);
    fireEvent.click(screen.getByText("Discovery"));
    fireEvent.click(screen.getByText("list_entities"));
    expect(onPick).toHaveBeenCalledWith("list_entities");
  });
});
