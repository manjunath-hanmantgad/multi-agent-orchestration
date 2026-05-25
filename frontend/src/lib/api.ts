import type {
  ApiResponse,
  AuditEvent,
  DecisionPayload,
  WorkflowRun,
  WorkflowStartRequest,
  WorkflowStartResponse,
} from "@/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const errorBody = await res.text().catch(() => "");
    throw new Error(`API ${method} ${path}: ${res.status} ${errorBody}`);
  }
  const json: ApiResponse<T> = await res.json();
  if (!json.success || json.error) {
    throw new Error(json.error ?? `API returned success=false`);
  }
  return json.data as T;
}

export const api = {
  workflows: {
    list: () =>
      request<WorkflowRun[]>("GET", "/api/workflows"),

    get: (id: string) =>
      request<WorkflowRun>("GET", `/api/workflows/${id}`),

    start: (payload: WorkflowStartRequest) =>
      request<WorkflowStartResponse>("POST", "/api/workflows/start", payload),

    decide: (id: string, payload: DecisionPayload) =>
      request<Record<string, unknown>>(
        "POST",
        `/api/workflows/${id}/decide`,
        payload
      ),

    audit: (id: string) =>
      request<AuditEvent[]>("GET", `/api/workflows/${id}/audit`),
  },
};
