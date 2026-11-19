// Inline-comment offsets from the keyboard quote box (US-35 review, DiffView).
import { expect, it } from "vitest";
import { originalOffset } from "../src/features/changes/DiffView";
it("maps textarea offsets back over CRLF", () => {
  const original = "one\r\ntwo";
  const shown = "one\ntwo";
  const start = originalOffset(original, shown.indexOf("two"));
  const end = originalOffset(original, shown.indexOf("two") + 3);
  expect(original.slice(start, end)).toBe("two");
  expect(originalOffset("plain text", 6)).toBe(6);
});
