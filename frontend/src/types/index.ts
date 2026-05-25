/** TypeScript interfaces matching core/models.py and core/schemas.py. */

export interface WorkflowRun {
  id: string;
  workflow_type: string;
  status: WorkflowStatus;
  current_stage: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export type WorkflowStatus =
  | "PENDING"
  | "RUNNING"
  | "PAUSED"
  | "APPROVED"
  | "REJECTED"
  | "COMPLETED"
  | "FAILED";

export type AuditActor = "SYSTEM" | "HUMAN";

export type WorkflowDecisionValue =
  | "APPROVED"
  | "REJECTED"
  | "REQUEST_MORE_INFO";

export interface AuditEvent {
  id: string;
  workflow_id: string;
  timestamp: string;
  stage: string;
  actor: AuditActor;
  event_type: string;
  event_data: Record<string, unknown>;
}

export interface DecisionPayload {
  actor: AuditActor;
  decision: WorkflowDecisionValue;
  notes?: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: string | null;
}

export interface WorkflowStartRequest {
  workflow_type: string;
  input_data: Record<string, unknown>;
}

export interface WorkflowStartResponse {
  workflow_id: string;
  result: Record<string, unknown>;
}
