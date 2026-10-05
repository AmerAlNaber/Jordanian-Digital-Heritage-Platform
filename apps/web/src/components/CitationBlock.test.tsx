import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CitationBlock } from "./CitationBlock";

describe("CitationBlock (CAT-1, SRC-3)", () => {
  it("shows the citation with its ARK and copies it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(
      <CitationBlock
        locale="ar"
        ark="ark:/99999/w8abc"
        text="يعقوب الطحّان. أخبار بلدة سُمَيْرة. 1923. ark:/99999/w8abc"
        heading="الاستشهاد"
        copyLabel="انسخ"
        copiedLabel="تم النسخ"
        identifierLabel="المعرّف"
      />,
    );
    expect(screen.getByTestId("ark")).toHaveTextContent("ark:/99999/w8abc");
    fireEvent.click(screen.getByRole("button", { name: "انسخ" }));
    await waitFor(() => expect(screen.getByRole("button")).toHaveTextContent("تم النسخ"));
    expect(writeText).toHaveBeenCalledWith(
      "يعقوب الطحّان. أخبار بلدة سُمَيْرة. 1923. ark:/99999/w8abc",
    );
  });
});
