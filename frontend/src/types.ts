// Shapes returned by the API (see backend/app/schemas.py).

export type Role = "client" | "operator" | "admin";
export type Quality = "good" | "usable" | "bad";
export type Status = "submitted" | "in_progress" | "delivered" | "accepted" | "rejected";

export const STATUSES: Status[] = ["submitted", "in_progress", "delivered", "accepted", "rejected"];

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  organisation: string | null;
}

export interface StatusEvent {
  from_status: Status | null;
  to_status: Status;
  actor_id: number;
  actor_name: string;
  created_at: string;
}

export interface DatasetRequest {
  id: number;
  client_id: number;
  client_name: string;
  task_name: string;
  episodes_requested: number;
  deadline: string;
  notes: string | null;
  status: Status;
  assigned_count: number;
  created_at: string;
  updated_at: string;
}

export interface RequestDetail extends DatasetRequest {
  events: StatusEvent[];
}

export interface Episode {
  id: number;
  episode_id: string;
  robot_id: string;
  task_name: string;
  recorded_at: string;
  duration_seconds: number;
  operator_name: string | null;
  quality: Quality;
  assigned_request_id: number | null;
}

export interface EpisodePage {
  items: Episode[];
  total: number;
  limit: number;
  offset: number;
}
