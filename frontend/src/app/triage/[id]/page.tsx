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

  const severityLevel =
    (workflow?.payload as Record<string, unknown>)?.severity_level as string | undefined;
  const severityReasoning =
    (workflow?.payload as Record<string, unknown>)?.severity_reasoning as string | undefined;

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

      <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Severity card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Severity
              {severityLevel && (
                <Badge variant={badgeVariant}>{severityLevel}</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {severityReasoning ? (
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                {severityReasoning}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">No reasoning available.</p>
            )}
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
