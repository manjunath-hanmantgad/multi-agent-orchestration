"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { AuditTimeline } from "@/components/workflows/AuditTimeline";
import { api } from "@/lib/api";
import type { AuditEvent, WorkflowRun } from "@/types";

export default function AuditPage() {
  const params = useParams();
  const workflowId = params.id as string;

  const [workflow, setWorkflow] = useState<WorkflowRun | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      try {
        const [wf, auditEvents] = await Promise.all([
          api.workflows.get(workflowId),
          api.workflows.audit(workflowId),
        ]);
        if (!cancelled) {
          setWorkflow(wf);
          setEvents(Array.isArray(auditEvents) ? auditEvents : []);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load audit trail");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchData();
  }, [workflowId]);

  if (loading) {
    return (
      <div className="min-h-screen">
        <PageHeader title="Audit Trail" description="Loading..." />
        <div className="p-6 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-md" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !workflow) {
    return (
      <div className="min-h-screen">
        <PageHeader title="Audit Trail" description="" />
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

  return (
    <div className="min-h-screen">
      <PageHeader
        title="Audit Trail"
        description={`Workflow: ${workflowId.slice(0, 8)} — ${workflow.workflow_type.replace(/_/g, " ")}`}
      />

      <div className="py-2">
        <AuditTimeline
          events={events.map((e) => ({
            timestamp: e.timestamp,
            actor: e.actor,
            event_type: e.event_type,
            stage: e.stage,
            event_data: (e.event_data ?? {}) as Record<string, unknown>,
          }))}
        />
      </div>
    </div>
  );
}
