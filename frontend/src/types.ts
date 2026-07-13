export type PhaseName =
  | "checkout"
  | "planning"
  | "executing"
  | "validating"
  | "reporting";

export interface PhaseEvent {
  phase: PhaseName;
  status: "start" | "done";
  detail?: string;
}

export interface ToolCallEvent {
  id: string;
  tool: string;
  status: "start" | "ok" | "error";
  input?: string | null;
  output?: string | null;
  error?: string | null;
  model_initiated?: boolean;
}

export interface CommandEvent {
  id: string;
  command: string;
  status: "start" | "ok" | "fail" | "blocked";
  category?: string | null;
  returncode?: number | null;
  log_path?: string | null;
}

export interface PlannerEvent {
  step: string;
}

export interface EvidenceEvent {
  path: string;
  kind: string;
  caption?: string;
}

export interface VerdictEvent {
  verdict: string;
  risk: string;
  failure_category?: string;
  summary?: string;
}

export interface AppEvent {
  seq: number;
  ts: number;
  type: string;
  data: Record<string, unknown>;
}
