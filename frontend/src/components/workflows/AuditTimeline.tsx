"use client";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface AuditTimelineItem {
  timestamp: string;
  actor: string;
  event_type: string;
  stage: string;
  event_data: Record<string, unknown>;
}

interface AuditTimelineProps {
  events: AuditTimelineItem[];
}

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
}

export function AuditTimeline({ events }: AuditTimelineProps) {
  if (events.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-8">
        No audit events found for this workflow.
      </p>
    );
  }

  return (
    <div className="space-y-0">
      {events.map((event, index) => {
        const isHuman = event.actor === "HUMAN";
        const hasData =
          event.event_data &&
          typeof event.event_data === "object" &&
          Object.keys(event.event_data).length > 0;

        return (
          <div key={index}>
            {/* Event row */}
            <div className="flex items-start gap-4 py-4 px-6">
              {/* Actor badge */}
              <Badge
                variant={isHuman ? "default" : "outline"}
                className={cn(
                  "shrink-0 mt-0.5",
                  isHuman
                    ? "bg-indigo-600 hover:bg-indigo-700 text-white"
                    : "bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800"
                )}
              >
                {event.actor}
              </Badge>

              {/* Event content */}
              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-muted-foreground">
                    {formatTimestamp(event.timestamp)}
                  </span>
                  <span className="text-xs font-medium text-foreground capitalize">
                    {event.event_type.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Stage: <span className="font-medium">{event.stage}</span>
                </p>

                {/* Expandable event data */}
                {hasData && (
                  <Collapsible className="mt-2">
                    <CollapsibleTrigger className="flex items-center gap-1 text-xs text-primary hover:underline cursor-pointer">
                      <ChevronDown className="h-3 w-3" />
                      Event Data
                    </CollapsibleTrigger>
                    <CollapsibleContent className="mt-1">
                      <div className="rounded-md bg-muted p-3 text-xs space-y-1 max-h-40 overflow-y-auto">
                        {Object.entries(event.event_data).map(([key, value]) => (
                          <div key={key} className="flex gap-2">
                            <span className="font-medium text-muted-foreground shrink-0">
                              {key.replace(/_/g, " ")}:
                            </span>
                            <span className="text-foreground break-all">
                              {typeof value === "object"
                                ? JSON.stringify(value)
                                : String(value)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </CollapsibleContent>
                  </Collapsible>
                )}
              </div>
            </div>

            {index < events.length - 1 && <Separator />}
          </div>
        );
      })}
    </div>
  );
}
