import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Navbar } from "../components/layout/Navbar";
import { Sidebar } from "../components/layout/Sidebar";

const ITEMS = [
  { id: "a", label: "Alpha", href: "#a" },
  { id: "b", label: "Beta", href: "#b" },
];

describe("Navbar", () => {
  it("shows the brand and its actions", () => {
    render(
      <Navbar>
        <button>Action</button>
      </Navbar>,
    );
    expect(screen.getByText("UptimeGlass")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Action" })).toBeInTheDocument();
  });
});

describe("Sidebar", () => {
  it("lists every link in a labelled navigation", () => {
    render(<Sidebar items={ITEMS} currentId="a" />);
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Alpha" })).toHaveAttribute("href", "#a");
    expect(screen.getByRole("link", { name: "Beta" })).toHaveAttribute("href", "#b");
  });

  it("marks only the current page", () => {
    render(<Sidebar items={ITEMS} currentId="b" />);
    expect(screen.getByRole("link", { name: "Beta" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Alpha" })).not.toHaveAttribute("aria-current");
  });
});
