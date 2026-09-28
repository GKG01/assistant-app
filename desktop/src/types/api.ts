export interface HealthResponse {
  status: "ok";
  service: "nova-backend";
}

export type BackendStatus = "checking" | "connected" | "offline";

export interface IndexedFile {
  id: number;
  name: string;
  extension: string;
  path: string;
  size: number;
  created_at: string;
  modified_at: string;
  indexed_at: string;
}

export interface SearchFilters {
  q?: string;
  extension?: string;
  directory?: string;
  modified_after?: string;
  modified_before?: string;
  min_size?: number;
  max_size?: number;
  sort?: "name_asc" | "name_desc" | "modified_asc" | "modified_desc" | "size_asc" | "size_desc";
  limit?: number;
  offset?: number;
}

export interface SearchResponse {
  results: IndexedFile[];
  total: number;
  limit: number;
  offset: number;
}

export interface IndexStats {
  indexed: number;
  created: number;
  updated: number;
  unchanged: number;
  removed: number;
  skipped: number;
  duration_ms: number;
  roots_indexed: number;
  roots_failed: number;
  warnings: string[];
}

export interface FileActionResponse {
  status: "requested";
  file_id: number;
  action: "open_file" | "show_in_folder";
}
