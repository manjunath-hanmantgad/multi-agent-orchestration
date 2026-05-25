"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { DecisionForm } from "@/components/workflows/DecisionForm";
import { api } from "@/lib/api";
import type { WorkflowRun } from "@/types";

const severityColor: Record<string, "destructive" | "secondary" | "default" | "outline"> = {
  P1: "destructive",
  P2: "outline",
  P3: "default",
  P4: "secondary",
};

function checkpointState(run: WorkflowRun): Record<string, unknown> {
  const payload = (run.payload ?? {}) as Record<string, unknown>;
  const checkpoint = (payload.checkpoint_data ?? {}) as Record<string, unknown>;
  return (checkpoint.state ?? {}) as Record<string, unknown>;
}

export default function TriagePage() {
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
          setError(err instanceof Error ? err.message : "Failed to load workflow");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchWorkflow();
  }, [workflowId]);

  const state = workflow ? checkpointState(workflow) : {};
  const severityLevel = state.severity_level as string | undefined;
  const severityReasoning = state.severity_reasoning as string | undefined;
  const incidentText = state.incident_text as string | undefined;
  const metadata = (state.metadata ?? {}) as Record<string, string>;

  if (loading) {
    return (
      <div className="min-h-screen">
        <PageHeader title="Incident Triage Review" description="Loading workflow..." />
        <div className="p-6 space-y-4">
          <Skeleton className="h-32 w-full rounded-md" />
          <Skeleton className="h-48 w-full rounded-md" />
        </div>
      </div>
    );
  }

  if (error || !workflow) {
    return (
      <div className="min-h-screen">
        <PageHeader title="Incident Triage Review" description="" />
        <div className="p-6">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error ?? "Workflow not found."}</AlertDescription>
          </Alert>
        </div>
      </div>
    );
  }

  const badgeVariant = severityColor[severityLevel ?? ""] ?? "default";

  return (
    <div className="min-h-screen">
      <PageHeader
        title="Incident Triage Review"
        description={`Workflow: ${workflowId}`}
      />

      <div className="p-6 space-y-6">
        {/* Severity card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Severity Assessment
              {severityLevel && (
                <Badge variant={badgeVariant}>{severityLevel}</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {incidentText && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Incident</p>
                <p className="text-sm whitespace-pre-wrap">{incidentText}</p>
              </div>
            )}
            {Object.keys(metadata).length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Metadata</p>
                <div className="grid grid-cols-2 gap-1">
                  {Object.entries(metadata).map(([k, v]) => (
                    <div key={k} className="text-sm">
                      <span className="font-medium">{k}: </span>
                      <span className="text-muted-foreground">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Reasoning</p>
              {severityReasoning ? (
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                  {severityReasoning}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground italic">No reasoning available.</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Decision card */}
        <Card>
          <CardHeader>
            <CardTitle>Decision</CardTitle>
          </CardHeader>
          <CardContent>
            <DecisionForm
              workflowId={workflowId}
              onSuccess={() => {
                toast.success("Decision submitted successfully");
                // Refresh workflow data
                api.workflows.get(workflowId).then((wf) => setWorkflow(wf)).catch(() => {});
              }}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
