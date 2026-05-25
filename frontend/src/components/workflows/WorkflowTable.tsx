"use client";

import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type { WorkflowRun } from "@/types";
import Link from "next/link";

interface WorkflowTableProps {
  data: WorkflowRun[];
}

export function WorkflowTable({ data }: WorkflowTableProps) {
  const columns: ColumnDef<WorkflowRun>[] = [
    {
      accessorKey: "id",
      header: "Workflow ID",
      cell: ({ row }) => {
        const id = row.getValue("id") as string;
        const wfType = row.original.workflow_type;
        const linkHref = wfType === "incident_triage" ? `/triage/${id}` : `/review/${id}`;
        return (
          <Link
            href={linkHref}
            className="font-mono text-xs text-primary hover:underline"
          >
            {id.slice(0, 8)}
          </Link>
        );
      },
    },
    {
      accessorKey: "workflow_type",
      header: "Type",
      cell: ({ row }) => {
        const type = row.getValue("workflow_type") as string;
        return (
          <span className="text-sm capitalize">
            {type.replace(/_/g, " ")}
          </span>
        );
      },
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => {
        const status = row.getValue("status") as string;
        return <StatusBadge status={status} />;
      },
    },
    {
      accessorKey: "current_stage",
      header: "Stage",
      cell: ({ row }) => {
        const stage = row.getValue("current_stage") as string | null;
        return (
          <span className="text-sm text-muted-foreground">
            {stage ?? "-"}
          </span>
        );
      },
    },
    {
      accessorKey: "created_at",
      header: "Created",
      cell: ({ row }) => {
        const date = row.getValue("created_at") as string;
        const formatted = date
          ? new Date(date).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })
          : "-";
        return <span className="text-sm text-muted-foreground">{formatted}</span>;
      },
    },
  ];

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="rounded-md border border-border">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id}>
                  {header.isPlaceholder
                    ? null
                    : flexRender(
                        header.column.columnDef.header,
                        header.getContext()
                      )}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.length > 0 ? (
            table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                No workflows found.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
