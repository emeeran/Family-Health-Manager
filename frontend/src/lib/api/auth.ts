import { apiRequest } from "../api-client";
import type { LoginRequest, LoginResponse, UserResponse, TwoFASetupResponse } from "../types/auth";

export function login(data: LoginRequest) {
  return apiRequest<LoginResponse>("/auth/login", {
    method: "POST",
    body: data,
  });
}

export function register(data: LoginRequest) {
  return apiRequest<UserResponse>("/auth/register", {
    method: "POST",
    body: data,
  });
}

export function getMe() {
  return apiRequest<UserResponse>("/auth/me");
}

export function setup2FA() {
  return apiRequest<TwoFASetupResponse>("/auth/2fa/setup", { method: "POST" });
}

export function verify2FASetup(code: string) {
  return apiRequest<{ enabled: boolean }>("/auth/2fa/verify", {
    method: "POST",
    body: { code },
  });
}

export function disable2FA(code: string) {
  return apiRequest<{ enabled: boolean }>("/auth/2fa/disable", {
    method: "POST",
    body: { code },
  });
}

export function login2FA(username: string, code: string) {
  return apiRequest<LoginResponse>("/auth/login/2fa", {
    method: "POST",
    body: { username, code },
  });
}
