// The live sentence preview (Pranshu — US-30, FR-81). A line-for-line mirror of
// backend/app/intake/ears.py render_statement, so the preview is exactly what will be stored;
// tests/composer.test.tsx pins the cases the backend tests pin.

import type { EarsTemplate } from "./api";

function cleanSlot(key: string, value: string): string {
  if (key === "statement") return value.trim(); // free text is stored as written (FR-04)
  let text = value.replace(/\s+/g, " ").trim();
  if (key === "system") text = text.replace(/^the\s+/i, ""); // the pattern says "the {system}"
  if (key === "response") text = text.replace(/^shall\s+/i, ""); // …and "shall {response}"
  return text.replace(/[ .,;]+$/, ""); // the pattern adds its own punctuation
}

/** The slots still empty, in template order. */
export function missingSlots(template: EarsTemplate, slots: Record<string, string>): string[] {
  return template.slots
    .filter((slot) => !cleanSlot(slot.key, slots[slot.key] ?? ""))
    .map((slot) => slot.label);
}

/** The sentence, or null while a slot is empty. */
export function renderStatement(
  template: EarsTemplate,
  slots: Record<string, string>,
): string | null {
  if (missingSlots(template, slots).length > 0) return null;
  return template.pattern.replace(/\{(\w+)\}/g, (_, key: string) =>
    cleanSlot(key, slots[key] ?? ""),
  );
}
