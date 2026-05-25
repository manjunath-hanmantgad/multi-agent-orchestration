"use client";

import { useEffect, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircle } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { WorkflowTable } from "@/components/workflows/WorkflowTable";
import { api } from "@/lib/api";
import type { WorkflowRun } from "@/types";

export default function Dashboard() {
  const [data, setData] = useState<WorkflowRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchWorkflows() {
      try {
        const workflows = await api.workflows.list();
        if (!cancelled) {
          setData(workflows);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to fetch workflows");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchWorkflows();
    const interval = setInterval(fetchWorkflows, 10_000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="min-h-screen">
      <PageHeader title="Dashboard" description="Workflow overview and status" />

      <div className="p-6">
        {/* Loading state */}
        {loading && (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full rounded-md" />
            ))}
          </div>
        )}

        {/* Error state */}
        {!loading && error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Empty state */}
        {!loading && !error && data && data.length === 0 && (
          <EmptyState
            title="No workflows yet"
            description="Workflows will appear here once they are created."
          />
        )}

        {/* Data state */}
        {!loading && !error && data && data.length > 0 && (
          <WorkflowTable data={data} />
        )}
      </div>
    </div>
  );
}
