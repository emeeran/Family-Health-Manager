export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
}

export interface UserResponse {
  id: string;
  username: string;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
}
