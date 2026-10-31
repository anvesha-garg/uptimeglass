import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnimatedBackground } from "../components/layout/AnimatedBackground";

describe("AnimatedBackground", () => {
  it("is decorative: hidden from assistive technology, with three blobs", () => {
    render(<AnimatedBackground />);
    const background = screen.getByTestId("animated-background");
    expect(background).toHaveAttribute("aria-hidden", "true");
    expect(background.querySelectorAll(".bg__blob")).toHaveLength(3);
  });
});
