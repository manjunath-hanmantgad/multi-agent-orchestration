import { PageHeader } from "@/components/shared/PageHeader";

export default function Home() {
  return (
    <div className="min-h-screen">
      <PageHeader title="Dashboard" description="Workflow overview and status" />
      <div className="p-6">
        <p className="text-sm text-muted-foreground">
          Dashboard content will be built in TASK-09.
        </p>
      </div>
    </div>
  );
}
