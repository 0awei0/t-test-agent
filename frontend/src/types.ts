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

export type TestPlanStatus = "planned" | "running" | "passed" | "failed" | "blocked";

export interface TestPlanItem {
  id: string;
  title: string;
  layer: string;
  target: string;
  command: string;
  evidence: string;
  status: TestPlanStatus;
  detail?: string;
  adaptive: boolean;
}

export interface TestPlanEvent {
  summary: string;
  items: Omit<TestPlanItem, "status">[];
}

export interface PlanUpdateEvent {
  id: string;
  status: TestPlanStatus;
  detail?: string;
  command?: string;
  adaptive?: boolean;
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

export interface MemoryEvent {
  mode: string;
  source_chars: number;
  summary_chars: number;
  compression_ratio: number;
  artifact_count: number;
}

export interface IsolationEvent {
  workspace: string;
  source_repo: string;
  command_policy: string;
  temp_write_scope: string;
  remote_mutation: string;
}

export interface ProvenanceEvent {
  run_id: string;
  planner_mode: string;
  strict_tools_passed: boolean;
  tool_calls: number;
  model_tool_calls: number;
  commands: number;
  generated_tests: number;
  evidence: number;
  started_at: number;
}

export interface SafetyCheckEvent {
  action: string;
  target: string;
  status: string;
  blocked_by: string;
  reason: string;
}

export interface AdaptationEvent {
  kind: string;
  status: string;
  detail: string;
}

export interface AppEvent {
  seq: number;
  ts: number;
  type: string;
  data: Record<string, unknown>;
}
