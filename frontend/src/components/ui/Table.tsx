import React from "react";

export interface TableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  className?: string;
  children?: React.ReactNode;
}

export function Table({ className = "", children, ...props }: TableProps) {
  return (
    <div className="w-full overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table
        className={`w-full text-left text-sm text-slate-700 border-collapse ${className}`}
        {...props}
      >
        {children}
      </table>
    </div>
  );
}

export interface TableHeaderProps
  extends React.HTMLAttributes<HTMLTableSectionElement> {
  className?: string;
  children?: React.ReactNode;
}

export function TableHeader({
  className = "",
  children,
  ...props
}: TableHeaderProps) {
  return (
    <thead
      className={`border-b border-slate-200 bg-slate-50/75 text-xs font-semibold uppercase tracking-wider text-slate-500 ${className}`}
      {...props}
    >
      {children}
    </thead>
  );
}

export interface TableBodyProps
  extends React.HTMLAttributes<HTMLTableSectionElement> {
  className?: string;
  children?: React.ReactNode;
}

export function TableBody({
  className = "",
  children,
  ...props
}: TableBodyProps) {
  return (
    <tbody
      className={`divide-y divide-slate-100 bg-white ${className}`}
      {...props}
    >
      {children}
    </tbody>
  );
}

export interface TableFooterProps
  extends React.HTMLAttributes<HTMLTableSectionElement> {
  className?: string;
  children?: React.ReactNode;
}

export function TableFooter({
  className = "",
  children,
  ...props
}: TableFooterProps) {
  return (
    <tfoot
      className={`border-t border-slate-200 bg-slate-50/50 text-xs font-medium text-slate-600 ${className}`}
      {...props}
    >
      {children}
    </tfoot>
  );
}

export interface TableRowProps
  extends React.HTMLAttributes<HTMLTableRowElement> {
  className?: string;
  isClickable?: boolean;
  children?: React.ReactNode;
}

export function TableRow({
  className = "",
  isClickable = false,
  children,
  ...props
}: TableRowProps) {
  return (
    <tr
      className={`
        transition-colors
        ${isClickable ? "cursor-pointer hover:bg-slate-50/80" : "hover:bg-slate-50/50"}
        ${className}
      `}
      {...props}
    >
      {children}
    </tr>
  );
}

export interface TableHeadProps
  extends React.ThHTMLAttributes<HTMLTableCellElement> {
  className?: string;
  children?: React.ReactNode;
}

export function TableHead({
  className = "",
  children,
  ...props
}: TableHeadProps) {
  return (
    <th className={`px-4 py-3.5 text-left font-semibold ${className}`} {...props}>
      {children}
    </th>
  );
}

export interface TableCellProps
  extends React.TdHTMLAttributes<HTMLTableCellElement> {
  className?: string;
  children?: React.ReactNode;
}

export function TableCell({
  className = "",
  children,
  ...props
}: TableCellProps) {
  return (
    <td className={`px-4 py-3.5 align-middle ${className}`} {...props}>
      {children}
    </td>
  );
}

export interface TableCaptionProps
  extends React.HTMLAttributes<HTMLTableCaptionElement> {
  className?: string;
  children?: React.ReactNode;
}

export function TableCaption({
  className = "",
  children,
  ...props
}: TableCaptionProps) {
  return (
    <caption
      className={`mt-3 text-xs text-slate-500 text-left px-4 ${className}`}
      {...props}
    >
      {children}
    </caption>
  );
}
