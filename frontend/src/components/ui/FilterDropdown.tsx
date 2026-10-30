import React, { useState, useRef, useEffect } from "react";
import { ChevronDownIcon, CheckIcon } from "./Icons";

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterDropdownProps {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
  className?: string;
}

export function FilterDropdown({
  label,
  value,
  options,
  onChange,
  className = "",
}: FilterDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((opt) => opt.value === value) || options[0];
  const isFiltered = value !== "all" && value !== "";

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  const handleSelect = (val: string) => {
    onChange(val);
    setIsOpen(false);
  };

  return (
    <div className={`relative inline-block text-left ${className}`} ref={containerRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`
          inline-flex items-center justify-between gap-2 px-3 py-2 text-sm rounded-lg border transition-all duration-150
          bg-white shadow-xs focus:outline-none focus:ring-2 focus:ring-blue-100
          ${
            isFiltered
              ? "border-blue-500 text-blue-700 bg-blue-50/50 font-medium"
              : "border-slate-300 text-slate-700 hover:border-slate-400"
          }
        `}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className="text-slate-500 font-normal">{label}:</span>
        <span className="font-medium text-slate-800">
          {selectedOption ? selectedOption.label : "All"}
        </span>
        <ChevronDownIcon
          size={15}
          className={`text-slate-400 transition-transform duration-150 ${
            isOpen ? "rotate-180" : ""
          }`}
        />
      </button>

      {isOpen && (
        <div
          className="absolute z-30 mt-1 min-w-[180px] rounded-lg bg-white py-1 shadow-lg border border-slate-200 text-sm focus:outline-none animate-in fade-in zoom-in-95 duration-100"
          role="listbox"
        >
          {options.map((option) => {
            const isSelected = option.value === value;
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => handleSelect(option.value)}
                className={`
                  w-full text-left px-3.5 py-2 flex items-center justify-between text-sm transition-colors
                  ${
                    isSelected
                      ? "bg-blue-50 text-blue-700 font-semibold"
                      : "text-slate-700 hover:bg-slate-50 hover:text-slate-900"
                  }
                `}
                role="option"
                aria-selected={isSelected}
              >
                <span>{option.label}</span>
                {isSelected && (
                  <CheckIcon size={14} className="text-blue-600 shrink-0" />
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
