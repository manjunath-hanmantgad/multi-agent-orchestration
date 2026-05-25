import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";

export default function ReviewPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Compliance Review"
        description="Human review screen for compliance workflows."
      />
      <Card>
        <CardContent className="py-12">
          <EmptyState
            title="Review page loading"
            description="This workflow's review screen will be available shortly."
          />
        </CardContent>
      </Card>
    </div>
  );
}
