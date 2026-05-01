export interface PaginatedResponse<T> {
  items: T[];
  pagination: PaginationInfo;
}

export interface PaginationInfo {
  next_cursor: string | null;
  has_more: boolean;
  total_count: number;
}

export interface ErrorResponse {
  status_code: number;
  error: string;
  message: string;
  details?: string[] | null;
}
