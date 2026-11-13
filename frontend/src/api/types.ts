// Response shapes of the backend (backend/app/schemas). Hand-written for Sprint 1; replace with
// types generated from /openapi.json (openapi-typescript) once the API settles. IDs are UUIDs.

export type UUID = string;

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string | null;
    details?: { field: string; message: string; type: string }[];
  };
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface RoleRef {
  id: UUID;
  name: string;
  is_default: boolean;
}

export interface User {
  id: UUID;
  email: string;
  full_name: string;
  platform_role: "platform_admin" | "service" | null;
  is_active: boolean;
  created_at: string;
}

export interface Me extends User {
  memberships: {
    workspace_id: UUID;
    workspace_name: string;
    role: RoleRef;
    joined_at: string;
  }[];
}

export interface SignupResponse extends TokenResponse {
  user: User;
  join_status: "joined" | "pending_approval";
  workspace_id: UUID | null;
}

export interface WorkspaceMembership {
  id: UUID;
  name: string;
  created_at: string;
  role: RoleRef;
  joined_at: string;
}

export type ProjectStatus = "setup" | "active" | "archived";

export interface Project {
  id: UUID;
  workspace_id: UUID;
  name: string;
  description: string | null;
  status: ProjectStatus;
  context_version: number;
  analysis_enabled: boolean;
  similarity_threshold: number;
  confidence_threshold: number;
  llm_budget_monthly_calls: number;
  required_approvals: number;
  chat_detection_enabled: boolean;
  created_at: string;
}

export interface MyPermissions {
  workspace_id: UUID;
  project_id: UUID | null;
  role: RoleRef;
  permissions: string[];
  protected_only: string[];
}

export type DocumentStatus = "queued" | "processing" | "done" | "failed";
export type ImportMode = "baseline" | "proposals";

export interface DocumentRead {
  document_id: UUID;
  project_id: UUID;
  filename: string;
  format: "pdf" | "docx" | "txt" | "reqif";
  size_bytes: number;
  status: DocumentStatus;
  progress_percent: number;
  error_message: string | null;
  requirement_count: number;
  import_mode: ImportMode;
  stakeholder_group: string | null;
  uploaded_by: UUID;
  uploaded_at: string;
  duplicate_of?: UUID | null;
}

export type RequirementState =
  | "Proposed"
  | "Under_Review"
  | "Approved"
  | "Rejected"
  | "Implemented"
  | "Deprecated";

export type RequirementOrigin = "document" | "post" | "change_request";

export interface RequirementRead {
  requirement_id: UUID;
  project_id: UUID;
  document_id: UUID;
  source_req_id: string | null;
  body: string;
  location: string | null;
  order_index: number;
  stakeholder_group: string | null;
  is_protected: boolean;
  current_version: number;
  state: RequirementState;
  origin: RequirementOrigin;
  owner_id: UUID | null;
  owner_name: string | null;
  section_heading: string | null;
  needs_review: boolean;
  review_reasons: string[];
}

/** Real-time envelope (docs/contracts/realtime.md). */
export interface RealtimeEvent {
  type: string;
  workspace_id: UUID;
  project_id: UUID | null;
  channel_id: UUID | null;
  entity_id: UUID | null;
  at: string;
  data: Record<string, unknown>;
}
