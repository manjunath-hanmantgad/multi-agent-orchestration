"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { DecisionForm } from "@/components/workflows/DecisionForm";
import { api } from "@/lib/api";
import type { WorkflowRun } from "@/types";

/** Extract checkpoint state from the run's payload. */
function checkpointState(run: WorkflowRun): Record<string, unknown> {
  const payload = (run.payload ?? {}) as Record<string, unknown>;
  const checkpoint = (payload.checkpoint_data ?? {}) as Record<string, unknown>;
  return (checkpoint.state ?? {}) as Record<string, unknown>;
}

function formatKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function severityBadgeVariant(
  sev: string
): "default" | "secondary" | "destructive" | "outline" {
  const s = sev.toUpperCase();
  if (s === "HIGH" || s === "CRITICAL") return "destructive";
  if (s === "MEDIUM") return "default";
  if (s === "LOW") return "outline";
  return "secondary";
}

function statusBadgeVariant(
  status: string
): "default" | "secondary" | "destructive" | "outline" {
  const s = status.toUpperCase();
  if (s === "PASSED") return "default";
  if (s === "FAILED") return "destructive";
  return "secondary";
}

export default function ReviewPage() {
  const params = useParams();
  const workflowId = params.id as string;

  const [workflow, setWorkflow] = useState<WorkflowRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchWorkflow() {
      try {
        const wf = await api.workflows.get(workflowId);
        if (!cancelled) {
          setWorkflow(wf);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load workflow"
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchWorkflow();
  }, [workflowId]);

  // ── Loading state ──────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen">
        <PageHeader title="Compliance Review" description="Loading..." />
        <div className="p-6 space-y-4">
          <Skeleton className="h-24 w-full rounded-md" />
          <Skeleton className="h-48 w-full rounded-md" />
          <Skeleton className="h-32 w-full rounded-md" />
        </div>
      </div>
    );
  }

  // ── Error state ────────────────────────────────────────────────────────
  if (error || !workflow) {
    return (
      <div className="min-h-screen">
        <PageHeader title="Compliance Review" description="" />
        <div className="p-6">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>
              {error ?? "Workflow not found."}
            </AlertDescription>
          </Alert>
        </div>
      </div>
    );
  }

  // ── Data extraction ────────────────────────────────────────────────────
  const state = checkpointState(workflow);
  const extractedData = (state.extracted_data ?? {}) as Record<
    string,
    unknown
  >;
  const metadata = (extractedData.metadata ?? {}) as Record<string, unknown>;
  const fields = (extractedData.structured_fields ?? {}) as Record<
    string,
    unknown
  >;
  const ruleResults = (state.rule_results ?? {}) as Record<
    string,
    unknown[]
  >;
  const riskScore = state.risk_score;
  const riskReasoning = state.risk_reasoning;

  // Build field entries from extracted_data / structured_fields
  const fieldEntries: { label: string; value: string }[] = [];
  if (metadata.file_type) {
    fieldEntries.push({
      label: "Document Type",
      value: String(metadata.file_type),
    });
  }
  if (metadata.page_count) {
    fieldEntries.push({
      label: "Page Count",
      value: String(metadata.page_count),
    });
  }
  fieldEntries.push({
    label: "Field Count",
    value: String(Object.keys(fields).length),
  });
  const keys = Object.keys(fields)
    .filter((k) => k !== "full_text")
    .map((k) => formatKey(k))
    .join(", ");
  fieldEntries.push({ label: "Fields", value: keys || "-" });

  // Build rule summary
  const passedCount = (ruleResults.passed ?? []).length;
  const failedCount = (ruleResults.failed ?? []).length;
  const flaggedCount = (ruleResults.flagged ?? []).length;

  // Build rule rows
  const ruleRows: {
    name: string;
    field: string;
    severity: string;
    status: string;
  }[] = [];
  for (const [bucket, items] of Object.entries(ruleResults)) {
    if (!Array.isArray(items)) continue;
    for (const rule of items) {
      if (typeof rule !== "object" || rule === null) continue;
      const r = rule as Record<string, unknown>;
      ruleRows.push({
        name: String(r.name ?? "Unnamed Rule"),
        field: String(r.field ?? "-"),
        severity: String(r.severity ?? "-").toUpperCase(),
        status: bucket.toUpperCase(),
      });
    }
  }

  return (
    <div className="min-h-screen">
      <PageHeader
        title="Compliance Review"
        description={`Workflow: ${workflowId.slice(0, 8)} — ${workflow.workflow_type.replace(/_/g, " ")}`}
      />

      <div className="p-6 space-y-6">
        {/* Extracted Fields Card */}
        <Card>
          <CardHeader>
            <CardTitle>Extracted Data Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Field</TableHead>
                  <TableHead>Value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fieldEntries.length > 0 ? (
                  fieldEntries.map((entry) => (
                    <TableRow key={entry.label}>
                      <TableCell className="font-medium">
                        {entry.label}
                      </TableCell>
                      <TableCell>{entry.value}</TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell
                      colSpan={2}
                      className="text-center text-muted-foreground"
                    >
                      No extracted data available.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Rule Results Card */}
        <Card>
          <CardHeader>
            <CardTitle>Rule Check Results</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Summary badges */}
            <div className="flex gap-3">
              <div className="flex items-center gap-1.5">
                <Badge variant="default">Passed</Badge>
                <span className="text-sm font-medium">{passedCount}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Badge variant="destructive">Failed</Badge>
                <span className="text-sm font-medium">{failedCount}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Badge variant="secondary">Flagged</Badge>
                <span className="text-sm font-medium">{flaggedCount}</span>
              </div>
            </div>

            {/* Rule rows table */}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Rule</TableHead>
                  <TableHead>Field</TableHead>
                  <TableHead>Severity</TableHead>
                  <TableHead>Result</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ruleRows.length > 0 ? (
                  ruleRows.map((row, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-medium">
                        {row.name}
                      </TableCell>
                      <TableCell>{formatKey(row.field)}</TableCell>
                      <TableCell>
                        <Badge variant={severityBadgeVariant(row.severity)}>
                          {row.severity}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusBadgeVariant(row.status)}>
                          {row.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell
                      colSpan={4}
                      className="text-center text-muted-foreground"
                    >
                      No rule rows available.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Risk Score Card */}
        <Card>
          <CardHeader>
            <CardTitle>Risk Analysis</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-baseline gap-2">
                <span className="text-sm text-muted-foreground">
                  Risk Score:
                </span>
                <span className="text-lg font-bold">
                  {riskScore != null ? String(riskScore) : "-"}
                </span>
              </div>
              {riskReasoning ? (
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                  {String(riskReasoning)}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground italic">
                  No risk reasoning available.
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Decision Card */}
        <Card>
          <CardHeader>
            <CardTitle>Decision</CardTitle>
          </CardHeader>
          <CardContent>
            <DecisionForm
              workflowId={workflowId}
              showRequestMoreInfo={true}
              onSuccess={() => {
                toast.success("Decision submitted successfully");
                api.workflows
                  .get(workflowId)
                  .then((wf) => setWorkflow(wf))
                  .catch(() => {});
              }}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
