import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import en from "../../../messages/en.json";

import { Toolbar } from "./Toolbar";

function renderToolbar(overrides: Partial<Parameters<typeof Toolbar>[0]> = {}) {
  const handlers = {
    onPrev: vi.fn(),
    onNext: vi.fn(),
    onFirst: vi.fn(),
    onLast: vi.fn(),
    onGoTo: vi.fn(),
    onZoomIn: vi.fn(),
    onZoomOut: vi.fn(),
    onFit: vi.fn(),
    onRotate: vi.fn(),
    onToggleTwoPage: vi.fn(),
    onPanel: vi.fn(),
  };
  render(
    <NextIntlClientProvider locale="en" messages={en}>
      <Toolbar
        locale="en"
        pageLabel="3"
        pageNumber={3}
        pageCount={40}
        twoPage={false}
        panel={null}
        printable
        disabled={false}
        {...handlers}
        {...overrides}
      />
    </NextIntlClientProvider>,
  );
  return handlers;
}

describe("RDR-3: the reader toolbar is operable from the keyboard and labelled", () => {
  it("turns pages and jumps to a page number", () => {
    const handlers = renderToolbar();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(handlers.onNext).toHaveBeenCalledTimes(1);
    expect(handlers.onPrev).toHaveBeenCalledTimes(1);
    const input = screen.getByLabelText("Go to page");
    fireEvent.change(input, { target: { value: "12" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);
    expect(handlers.onGoTo).toHaveBeenCalledWith(12);
    expect(screen.getByText("3 of 40")).toBeInTheDocument();
  });
  it("disables the ends and exposes the toggles' state", () => {
    const handlers = renderToolbar({ pageNumber: 1, pageLabel: "1" });
    expect(screen.getByRole("button", { name: "First page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Two-page view" }));
    expect(handlers.onToggleTwoPage).toHaveBeenCalled();
    const print = screen.getByRole("button", { name: "Print" });
    expect(print).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(print);
    expect(handlers.onPanel).toHaveBeenCalledWith("print");
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(handlers.onZoomIn).toHaveBeenCalled();
  });
  it("hides print when the work cannot be printed", () => {
    renderToolbar({ printable: false });
    expect(screen.queryByRole("button", { name: "Print" })).toBeNull();
  });
});
