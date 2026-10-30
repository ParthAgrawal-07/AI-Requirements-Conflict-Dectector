import React, { useState, useMemo } from "react";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "./Table";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  ArrowUpDownIcon,
} from "./Icons";
import { Button } from "./Button";

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  render?: (item: T, index: number) => React.ReactNode;
  sortable?: boolean;
  align?: "left" | "center" | "right";
  className?: string;
}

export interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  pageSize?: number;
  initialSortKey?: string;
  initialSortDirection?: "asc" | "desc";
  emptyMessage?: string;
  isLoading?: boolean;
  onRowClick?: (item: T) => void;
  footerNote?: React.ReactNode;
  className?: string;
}

export function DataTable<T extends object>({
  data,
  columns,
  pageSize = 10,
  initialSortKey,
  initialSortDirection = "asc",
  emptyMessage = "No records found.",
  isLoading = false,
  onRowClick,
  footerNote,
  className = "",
}: DataTableProps<T>) {
  const [currentPage, setCurrentPage] = useState(1);
  const [sortKey, setSortKey] = useState<string | undefined>(initialSortKey);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">(
    initialSortDirection
  );

  const handleSort = (key: string) => {
    if (sortKey === key) {
      if (sortDirection === "asc") {
        setSortDirection("desc");
      } else {
        setSortKey(undefined);
        setSortDirection("asc");
      }
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  };

  const sortedData = useMemo(() => {
    if (!sortKey) return data;
    return [...data].sort((a, b) => {
      const valA = (a as Record<string, unknown>)[sortKey];
      const valB = (b as Record<string, unknown>)[sortKey];
      if (valA === valB) return 0;
      if (valA === null || valA === undefined) return 1;
      if (valB === null || valB === undefined) return -1;

      let comparison = 0;
      if (typeof valA === "number" && typeof valB === "number") {
        comparison = valA - valB;
      } else {
        comparison = String(valA).localeCompare(String(valB));
      }
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [data, sortKey, sortDirection]);

  const totalPages = Math.max(1, Math.ceil(sortedData.length / pageSize));
  const startIndex = (currentPage - 1) * pageSize;
  const paginatedData = sortedData.slice(startIndex, startIndex + pageSize);

  const startRecord = sortedData.length === 0 ? 0 : startIndex + 1;
  const endRecord = Math.min(startIndex + pageSize, sortedData.length);

  const alignStyles = {
    left: "text-left",
    center: "text-center",
    right: "text-right",
  };

  return (
    <div className={`space-y-3 ${className}`}>
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((col) => {
              const isSorted = sortKey === col.key;
              return (
                <TableHead
                  key={col.key}
                  className={`${alignStyles[col.align || "left"]} ${col.className || ""}`}
                >
                  {col.sortable ? (
                    <button
                      type="button"
                      onClick={() => handleSort(col.key)}
                      className="inline-flex items-center gap-1.5 font-semibold text-slate-600 hover:text-slate-900 focus:outline-none"
                    >
                      <span>{col.header}</span>
                      {isSorted ? (
                        sortDirection === "asc" ? (
                          <ChevronUpIcon size={14} className="text-blue-600" />
                        ) : (
                          <ChevronDownIcon size={14} className="text-blue-600" />
                        )
                      ) : (
                        <ArrowUpDownIcon size={13} className="text-slate-400" />
                      )}
                    </button>
                  ) : (
                    <span>{col.header}</span>
                  )}
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>

        <TableBody>
          {isLoading ? (
            Array.from({ length: 4 }).map((_, rIdx) => (
              <TableRow key={`skeleton-${rIdx}`}>
                {columns.map((col, cIdx) => (
                  <TableCell key={`col-${cIdx}`}>
                    <div className="h-4 bg-slate-200/80 rounded animate-pulse w-3/4" />
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : paginatedData.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={columns.length}
                className="text-center py-8 text-slate-500"
              >
                {emptyMessage}
              </TableCell>
            </TableRow>
          ) : (
            paginatedData.map((item, index) => {
              const itemObj = item as Record<string, unknown>;
              const rowKey =
                "id" in itemObj && itemObj.id !== undefined && itemObj.id !== null
                  ? String(itemObj.id)
                  : index;
              return (
                <TableRow
                  key={rowKey}
                  isClickable={Boolean(onRowClick)}
                  onClick={onRowClick ? () => onRowClick(item) : undefined}
                >
                  {columns.map((col) => (
                    <TableCell
                      key={col.key}
                      className={`${alignStyles[col.align || "left"]} ${
                        col.className || ""
                      }`}
                    >
                      {col.render
                        ? col.render(item, startIndex + index)
                        : String((item as Record<string, unknown>)[col.key] ?? "")}
                    </TableCell>
                  ))}
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>

      {/* Pagination & Footer controls */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500 px-1 py-1">
        <div className="flex items-center gap-4">
          <span>
            Showing {startRecord}–{endRecord} of {sortedData.length} findings
          </span>
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                aria-label="Previous page"
              >
                <ChevronLeftIcon size={14} />
              </Button>
              <span className="px-2 font-medium text-slate-700">
                Page {currentPage} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                aria-label="Next page"
              >
                <ChevronRightIcon size={14} />
              </Button>
            </div>
          )}
        </div>

        {footerNote && (
          <div className="text-slate-400 italic font-normal text-right">
            {footerNote}
          </div>
        )}
      </div>
    </div>
  );
}
