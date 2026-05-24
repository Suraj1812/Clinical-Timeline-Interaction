export type InstructionType = "medication" | "temperature";
export type Actor = "doctor" | "patient" | "system";
export type Severity = "neutral" | "success" | "warning" | "critical";

export type Task = {
  id: string;
  type: InstructionType;
  instruction: string;
  status: "pending" | "completed";
  response: null | { outcome?: "taken" | "not_taken"; value?: number };
  created_at: string;
  updated_at: string;
};

export type TimelineEvent = {
  id: string;
  task_id: string;
  type: string;
  actor: Actor;
  title: string;
  summary: string;
  severity: Severity;
  created_at: string;
};

export type TimelineState = {
  tasks: Task[];
  events: TimelineEvent[];
};
