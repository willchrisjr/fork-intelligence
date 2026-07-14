"use client";

import {
  ArrowDown,
  ArrowUp,
  FileText,
  GitCommitHorizontal,
  GitPullRequestArrow,
  PackageOpen,
} from "lucide-react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import Link from "next/link";
import { Confidence } from "./confidence";
import {
  classificationLabel,
  formatDate,
  formatNumber,
  formatPercent,
  maintenanceLabel,
} from "@/lib/format";
import type { ForkPage, ForkSummary } from "@/lib/types";

const columnHelper = createColumnHelper<ForkSummary>();

export function ForkTable({
  page,
  analysisId,
  selected,
  sort,
  order,
  onSort,
  onSelect,
  onInspect,
  onPage,
}: {
  page: ForkPage;
  analysisId: string;
  selected: string[];
  sort: string;
  order: "asc" | "desc";
  onSort: (sort: string, order: "asc" | "desc") => void;
  onSelect: (id: string) => void;
  onInspect: (id: string) => void;
  onPage: (page: number) => void;
}) {
  const sorting: SortingState = [{ id: sort, desc: order === "desc" }];
  const columns = [
    columnHelper.display({
      id: "select",
      header: () => <span className="sr-only">Select for comparison</span>,
      cell: ({ row }) => (
        <input
          type="checkbox"
          aria-label={`Select ${row.original.fullName} for comparison`}
          checked={selected.includes(row.original.id)}
          disabled={!selected.includes(row.original.id) && selected.length >= 2}
          onChange={() => onSelect(row.original.id)}
        />
      ),
    }),
    columnHelper.accessor("fullName", {
      id: "name",
      header: "Fork",
      cell: ({ row }) => (
        <div className="repo-cell">
          <button
            className="table-repo-button"
            onClick={() => onInspect(row.original.id)}
          >
            {row.original.fullName}
          </button>
          <small>
            Updated {formatDate(row.original.updatedAt)} ·{" "}
            {row.original.analysisDepth}
          </small>
        </div>
      ),
    }),
    columnHelper.accessor("classification", {
      header: "Classification",
      enableSorting: false,
      cell: ({ getValue }) => (
        <span className="classification">
          <i className="status-dot good" />
          {classificationLabel(getValue())}
        </span>
      ),
    }),
    columnHelper.accessor("maintenance", {
      header: "Maintenance",
      enableSorting: false,
      cell: ({ getValue }) => (
        <span
          className={
            getValue() === "inactive"
              ? "tone-error"
              : getValue() === "low_activity"
                ? "tone-warning"
                : "tone-good"
          }
        >
          {maintenanceLabel(getValue())}
        </span>
      ),
    }),
    columnHelper.accessor("originalWorkPercent", {
      id: "original_development",
      header: "Original work",
      cell: ({ getValue }) => (
        <strong
          className={(getValue() ?? 0) >= 20 ? "tone-good" : "tone-warning"}
        >
          {formatPercent(getValue(), 1)}
        </strong>
      ),
    }),
    columnHelper.accessor("activity30d", {
      id: "recent_activity",
      header: "Activity",
      cell: ({ row }) => (
        <span>
          <strong>{formatNumber(row.original.uniqueCommits)} commits</strong>
          <br />
          <span className="muted">
            30d: {formatNumber(row.original.activity30d)} · 90d:{" "}
            {formatNumber(row.original.activity90d)}
          </span>
        </span>
      ),
    }),
    columnHelper.accessor("confidence", {
      id: "maintained_successor",
      header: "Confidence",
      cell: ({ getValue }) => <Confidence value={getValue()} />,
    }),
    columnHelper.display({
      id: "evidence",
      header: "Evidence",
      cell: ({ row }) => (
        <button
          className="evidence-button"
          onClick={() => onInspect(row.original.id)}
          aria-label={`Inspect evidence for ${row.original.fullName}`}
        >
          <span>
            <GitCommitHorizontal size={13} />
            {row.original.evidenceCounts.commits}
          </span>
          <span>
            <GitPullRequestArrow size={13} />
            {row.original.evidenceCounts.patches}
          </span>
          <span>
            <FileText size={13} />
            {row.original.evidenceCounts.files}
          </span>
          <span>
            <PackageOpen size={13} />
            {row.original.evidenceCounts.releases}
          </span>
        </button>
      ),
    }),
  ];
  // TanStack Table intentionally exposes non-memoizable functions; row state remains local here.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: page.items,
    columns,
    state: { sorting },
    manualSorting: true,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <div className="data-panel">
      <div
        className="table-scroll"
        tabIndex={0}
        aria-label="Scrollable fork results"
      >
        <table className="fork-table">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const canSort = header.column.getCanSort();
                  const active = header.column.id === sort;
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={
                        active
                          ? order === "asc"
                            ? "ascending"
                            : "descending"
                          : undefined
                      }
                    >
                      {canSort ? (
                        <button
                          className="table-sort"
                          onClick={() =>
                            onSort(
                              header.column.id,
                              active && order === "desc" ? "asc" : "desc",
                            )
                          }
                        >
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                          {active ? (
                            order === "desc" ? (
                              <ArrowDown size={12} />
                            ) : (
                              <ArrowUp size={12} />
                            )
                          ) : null}
                        </button>
                      ) : (
                        flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className={selected.includes(row.original.id) ? "selected" : ""}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <footer className="table-footer">
        <span>
          Showing {page.items.length ? (page.page - 1) * page.pageSize + 1 : 0}–
          {Math.min(page.page * page.pageSize, page.total)} of{" "}
          {formatNumber(page.total)} analyzed forks
        </span>
        <nav aria-label="Fork result pages">
          <button
            className="page-button"
            disabled={page.page <= 1}
            onClick={() => onPage(1)}
            aria-label="Return to first page"
          >
            1
          </button>
          <button
            className="page-button"
            aria-current="page"
            aria-label={`Current result batch ${page.page}`}
          >
            {page.page}
          </button>
          <button
            className="page-button"
            disabled={!page.nextCursor}
            onClick={() => onPage(page.page + 1)}
            aria-label="Load next result batch"
          >
            ›
          </button>
        </nav>
        <Link
          className="text-link"
          href={page.total ? `/analyses/${analysisId}/evolution` : "#"}
        >
          Accessible network table
        </Link>
      </footer>
    </div>
  );
}
