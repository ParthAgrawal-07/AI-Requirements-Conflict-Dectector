import type { EarsTemplate, TemplateKey } from "./api";

export interface EarsTemplatePickerProps {
  templates: EarsTemplate[];
  value: TemplateKey | null;
  onChange: (template: TemplateKey) => void;
}

/** The five EARS chips plus free text (interface design §5.1), as a radio group: arrow keys move
 *  between chips, and each chip says its pattern for screen readers. */
export function EarsTemplatePicker({ templates, value, onChange }: EarsTemplatePickerProps) {
  return (
    <div className="ears-picker" role="radiogroup" aria-label="Template (EARS patterns)">
      {templates.map((template) => (
        <label
          key={template.template}
          className={`pill${value === template.template ? " pill-active" : ""}`}
          title={template.example}
        >
          <input
            type="radio"
            name="ears-template"
            className="sr-only"
            value={template.template}
            checked={value === template.template}
            onChange={() => onChange(template.template)}
          />
          {template.chip}
          <span className="sr-only">: {template.pattern.replace(/\{(\w+)\}/g, "<$1>")}</span>
        </label>
      ))}
    </div>
  );
}
