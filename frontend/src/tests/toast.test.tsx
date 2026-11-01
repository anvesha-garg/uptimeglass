import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../components/glass/ToastProvider";
import { useToast } from "../components/glass/toast-context";
import type { ToastKind } from "../components/glass/toast-context";

function Trigger({ kind }: { kind?: ToastKind }) {
  const { show } = useToast();
  return <button onClick={() => show("Saved!", kind)}>Show</button>;
}

function renderWithProvider(kind?: ToastKind) {
  render(
    <ToastProvider>
      <Trigger kind={kind} />
    </ToastProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Show" }));
}

describe("Toast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows a message and removes it after five seconds", () => {
    renderWithProvider();
    expect(screen.getByText("Saved!")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.queryByText("Saved!")).not.toBeInTheDocument();
  });

  it("can be dismissed by hand", () => {
    renderWithProvider();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(screen.queryByText("Saved!")).not.toBeInTheDocument();
  });

  it("announces errors as alerts", () => {
    renderWithProvider("error");
    expect(screen.getByRole("alert")).toHaveTextContent("Saved!");
  });

  it("refuses to be used outside the provider", () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Trigger />)).toThrow(/ToastProvider/);
    quiet.mockRestore();
  });
});
