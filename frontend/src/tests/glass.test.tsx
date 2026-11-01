import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EmptyState } from "../components/glass/EmptyState";
import { GlassButton } from "../components/glass/GlassButton";
import { GlassCard } from "../components/glass/GlassCard";
import { GlassInput } from "../components/glass/GlassInput";
import { Skeleton } from "../components/glass/Skeleton";
import { StatusBadge } from "../components/glass/StatusBadge";
import type { MonitorStatus } from "../components/glass/StatusBadge";

describe("GlassButton", () => {
  it("calls onClick and is a non-submitting button by default", async () => {
    const onClick = vi.fn();
    render(<GlassButton onClick={onClick}>Save</GlassButton>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveAttribute("type", "button");

    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("is disabled and busy while loading, so it cannot be clicked twice", async () => {
    const onClick = vi.fn();
    render(
      <GlassButton loading onClick={onClick}>
        Save
      </GlassButton>,
    );
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");

    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("uses the variant class", () => {
    render(<GlassButton variant="danger">Delete</GlassButton>);
    expect(screen.getByRole("button", { name: "Delete" })).toHaveClass("glass-button--danger");
  });
});

describe("GlassInput", () => {
  it("links the label to the input", () => {
    render(<GlassInput label="Email" />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("accepts typing", async () => {
    render(<GlassInput label="Email" />);
    const input = screen.getByLabelText("Email");
    await userEvent.type(input, "a@b.co");
    expect(input).toHaveValue("a@b.co");
  });

  it("shows an error, marks the input invalid and describes it", () => {
    render(<GlassInput label="Email" error="Required" hint="We never share it" />);
    const input = screen.getByLabelText("Email");
    expect(screen.getByRole("alert")).toHaveTextContent("Required");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(/Required/);
  });

  it("is not invalid without an error", () => {
    render(<GlassInput label="Email" />);
    expect(screen.getByLabelText("Email")).not.toHaveAttribute("aria-invalid");
  });
});

describe("GlassCard", () => {
  it("renders its children on a glass surface", () => {
    render(<GlassCard data-testid="card">Hello</GlassCard>);
    const card = screen.getByTestId("card");
    expect(card).toHaveClass("glass");
    expect(card).toHaveTextContent("Hello");
  });
});

describe("StatusBadge", () => {
  it.each(["UP", "DEGRADED", "DOWN", "PAUSED", "PENDING"] as MonitorStatus[])(
    "writes the %s status out as text",
    (status) => {
      render(<StatusBadge status={status} />);
      expect(screen.getByText(new RegExp(`^${status}$`, "i"))).toBeInTheDocument();
    },
  );
});

describe("Skeleton", () => {
  it("is hidden from assistive technology", () => {
    render(<Skeleton width="50%" />);
    expect(screen.getByTestId("skeleton")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("EmptyState", () => {
  it("shows the title, text and action", () => {
    render(
      <EmptyState title="Nothing here" description="Add one." action={<button>Add</button>} />,
    );
    expect(screen.getByRole("heading", { name: "Nothing here" })).toBeInTheDocument();
    expect(screen.getByText("Add one.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });

  it("works with only a title", () => {
    render(<EmptyState title="Empty" />);
    expect(screen.getByRole("heading", { name: "Empty" })).toBeInTheDocument();
  });
});
