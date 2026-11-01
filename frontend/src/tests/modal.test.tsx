import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { GlassModal } from "../components/glass/GlassModal";

function Harness({ onClose }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open</button>
      <GlassModal
        open={open}
        onClose={() => {
          onClose?.();
          setOpen(false);
        }}
        title="Confirm"
      >
        <button>Yes</button>
        <button>No</button>
      </GlassModal>
    </>
  );
}

describe("GlassModal", () => {
  it("renders nothing while closed", () => {
    render(
      <GlassModal open={false} onClose={() => {}} title="Hidden">
        content
      </GlassModal>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is a dialog named by its title when open", () => {
    render(
      <GlassModal open onClose={() => {}} title="Delete monitor?">
        content
      </GlassModal>,
    );
    expect(screen.getByRole("dialog", { name: "Delete monitor?" })).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<Harness onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: "Open" }));
    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes when the dark area behind it is pressed", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<Harness onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: "Open" }));
    await user.click(screen.getByTestId("modal-overlay"));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("stays open when something inside it is pressed", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<Harness onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: "Open" }));
    await user.click(screen.getByRole("button", { name: "Yes" }));

    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("moves focus inside, and gives it back to the opener on close", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open" });

    await user.click(opener);
    expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);

    await user.keyboard("{Escape}");
    expect(opener).toHaveFocus();
  });

  it("keeps Tab inside the dialog by wrapping around", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Open" }));

    // Focus starts on the Close button, the first control.
    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();

    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "No" })).toHaveFocus(); // wrapped to the last

    await user.tab();
    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus(); // and back
  });
});
