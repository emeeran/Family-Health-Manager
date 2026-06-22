import { apiRequest } from "../api-client";
import type { LoginRequest, LoginResponse, UserResponse } from "../types/auth";

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

export function changePassword(currentPassword: string, newPassword: string) {
  return apiRequest<{ message: string }>("/auth/change-password", {
    method: "POST",
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

export function login2FA(username: string, code: string) {
  return apiRequest<LoginResponse>("/auth/login/2fa", {
    method: "POST",
    body: { username, code },
  });
}
