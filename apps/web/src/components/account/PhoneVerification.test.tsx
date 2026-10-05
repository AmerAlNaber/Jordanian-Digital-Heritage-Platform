import type { PhoneStatus } from "@jdhp/schemas";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import en from "../../../messages/en.json";

import { PhoneVerification } from "./PhoneVerification";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

function renderPanel(
  status: PhoneStatus = { phone_number: null, verified_at: null, pending: false, expires_at: null },
) {
  render(
    <NextIntlClientProvider locale="en" messages={en}>
      <PhoneVerification status={status} locale="en" />
    </NextIntlClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ACC-1: phone verification panel", () => {
  it("asks for a number, sends the code through the BFF and then asks for the code", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();
    fireEvent.change(screen.getByLabelText(/mobile number/i), {
      target: { value: "+962 79 000 1234" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send code/i }));
    await waitFor(() => expect(screen.getByLabelText(/six-digit code/i)).toBeDefined());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/me/phone",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ phone_number: "+962790001234" }),
      }),
    );
  });

  it("shows the refusal when the code is wrong and never the number in full", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ code: "phone_code_invalid" }), { status: 400 }),
      );
    vi.stubGlobal("fetch", fetchMock);
    renderPanel({
      phone_number: "+962•••••••34",
      verified_at: null,
      pending: true,
      expires_at: null,
    });
    expect(screen.getByText(/\+962•••••••34/)).toBeDefined();
    fireEvent.change(screen.getByLabelText(/six-digit code/i), { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/not accepted/i));
  });
});
