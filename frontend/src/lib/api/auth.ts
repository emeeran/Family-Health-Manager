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
