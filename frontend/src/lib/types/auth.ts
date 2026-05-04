export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  requires_2fa?: boolean;
  username?: string;
}

export interface UserResponse {
  id: string;
  username: string;
  is_active: boolean;
  totp_enabled: boolean;
  created_at: string;
  last_login: string | null;
}

export interface TwoFASetupResponse {
  secret: string;
  qr_code_base64: string;
  backup_codes: string[];
}
