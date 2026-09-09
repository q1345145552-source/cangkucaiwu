"use client";
import { useState, useRef, useEffect } from "react";
import { Search, ChevronDown } from "lucide-react";

export interface SearchableOption {
  value: number | string;
  label: string;
  searchText?: string; // 用于模糊匹配的文本（如公司名 + 编号）
}

export default function SearchableSelect(props: {
  value: number | string;
  options: SearchableOption[];
  onChange: (v: number | string) => void;
  placeholder?: string;
  className?: string;
}) {
  const { value, options, onChange, placeholder = "请选择", className } = props;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const selected = options.find(o => o.value === value);
  const q = query.trim().toLowerCase();
  const filtered = q
    ? options.filter(o => (o.searchText || o.label).toLowerCase().includes(q))
    : options;

  return (
    <div ref={ref} className={`relative ${className || ""}`}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="form-input flex items-center justify-between text-left w-full"
      >
        <span className={selected ? "text-gray-800 truncate" : "text-gray-400"}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDown size={14} className="text-gray-400 shrink-0" />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg overflow-hidden">
          <div className="p-2 border-b bg-white">
            <div className="flex items-center gap-1.5 px-2 py-1.5 bg-gray-50 rounded">
              <Search size={14} className="text-gray-400 shrink-0" />
              <input
                autoFocus
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="搜索公司名 / 编号"
                className="flex-1 bg-transparent outline-none text-sm text-gray-700"
              />
            </div>
          </div>
          <div className="max-h-56 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-3 py-5 text-center text-gray-400 text-sm">无匹配客户</div>
            ) : (
              filtered.map(o => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => { onChange(o.value); setOpen(false); setQuery(""); }}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-blue-50 ${o.value === value ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-700"}`}
                >
                  {o.label}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
