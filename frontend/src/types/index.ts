export interface QueryRequest {
  user_query: string;
  session_id?: string;
  repo_url?: string;
  github_token?: string;
  allow_web_search?: boolean;
}

export interface SolveTicketResponse {
  status: "success" | "needs_ingestion" | "error";
  answer?: string;
  metadata?: {
    detected_feature: string;
    docs_retrieved: number;
    github_issues_found: number;
    session_id: string;
    is_relevant: boolean;
  };
  detail?: string;
}

export interface PrepareRepoResponse {
  status: "processing" | "interrupted" | "resuming";
  metadata?: { session_id: string };
  session_id?: string;
  completed_phases?: string[];
  message?: string;
}

export interface StatusResponse {
  status: "ok" | "needs_ingestion";
  data?: {
    session_id: string;
    stage: string;
    message: string;
    percent?: number;
    current?: number;
    total?: number;
    eta_seconds?: number;
    completed_phases?: string[];
  };
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  metadata?: SolveTicketResponse["metadata"];
}

export interface FeedbackRequest {
  query: string;
  answer: string;
  feature_detected: string;
  thumbs_up: boolean;
  session_id: string;
}
