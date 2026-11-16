import type { EarsTemplate } from "./api";

export interface SlotFieldsProps {
  template: EarsTemplate;
  slots: Record<string, string>;
  onChange: (key: string, value: string) => void;
}

/** One labelled field per slot of the chosen template, laid out in sentence order with the fixed
 *  words of the pattern between them ("When … , the … shall …"). */
export function SlotFields({ template, slots, onChange }: SlotFieldsProps) {
  const parts = template.pattern.split(/(\{\w+\})/).filter(Boolean);
  return (
    <div className="slot-fields">
      {parts.map((part, index) => {
        const match = /^\{(\w+)\}$/.exec(part);
        if (!match) {
          const words = part.trim();
          return words ? (
            <span key={index} className="slot-word" aria-hidden="true">
              {words}
            </span>
          ) : null;
        }
        const slot = template.slots.find((s) => s.key === match[1]);
        if (!slot) return null;
        const id = `slot-${slot.key}`;
        const multiline = slot.key === "statement";
        return (
          <span key={index} className="slot-field">
            <label htmlFor={id} className="sr-only">
              {slot.label}
            </label>
            {multiline ? (
              <textarea
                id={id}
                rows={3}
                value={slots[slot.key] ?? ""}
                placeholder={slot.placeholder}
                maxLength={4000}
                onChange={(event) => onChange(slot.key, event.target.value)}
              />
            ) : (
              <input
                id={id}
                value={slots[slot.key] ?? ""}
                placeholder={slot.placeholder}
                maxLength={500}
                onChange={(event) => onChange(slot.key, event.target.value)}
              />
            )}
          </span>
        );
      })}
    </div>
  );
}
