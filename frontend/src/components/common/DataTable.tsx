"use client";
import { ChevronLeft, ChevronRight, PackageOpen } from "lucide-react";

interface Column {
  key: string;
  label: string;
  render?: (value: any, row: any) => React.ReactNode;
  align?: "left" | "right" | "center";
}

export default function DataTable({ columns, data, total, page, pageSize, onPageChange, onRowClick }: {
  columns: Column[];
  data: any[];
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (p: number) => void;
  onRowClick?: (row: any) => void;
}) {
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="table-card">
      <div className="overflow-x-auto">
        <table>
          <thead>
            <tr>
              {columns.map(c => (
                <th key={c.key} className={c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : ""}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              <tr>
                <td colSpan={columns.length}>
                  <div className="empty-state py-12">
                    <PackageOpen size={40} className="empty-state-icon" />
                    <span className="empty-state-text">暂无数据</span>
                  </div>
                </td>
              </tr>
            ) : data.map((row, i) => (
              <tr key={row.id || i} className={onRowClick ? "cursor-pointer" : ""} onClick={() => onRowClick?.(row)}>
                {columns.map(c => (
                  <td key={c.key} className={c.align === "right" ? "text-right font-medium tabular-nums" : c.align === "center" ? "text-center" : ""}>
                    {c.render ? c.render(row[c.key], row) : (row[c.key] ?? "-")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t bg-gray-50">
          <span className="text-xs text-gray-500">共 {total} 条</span>
          <div className="flex items-center gap-2">
            <button onClick={() => onPageChange(page - 1)} disabled={page <= 1} className="p-1 rounded hover:bg-gray-200 disabled:opacity-30"><ChevronLeft size={16} /></button>
            <span className="text-sm">{page} / {totalPages}</span>
            <button onClick={() => onPageChange(page + 1)} disabled={page >= totalPages} className="p-1 rounded hover:bg-gray-200 disabled:opacity-30"><ChevronRight size={16} /></button>
          </div>
        </div>
      )}
    </div>
  );
}
