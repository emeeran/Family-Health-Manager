# ADR-002: JWT in HTTP-only Cookie for Session Management

## Status: Accepted

## Context

The application requires secure user authentication (FR-034, FR-035, NFR-006):
- Username/password authentication for v1
- Session tokens expire after 24 hours of inactivity
- Protection against XSS and CSRF attacks
- Stateless authentication for horizontal scalability (future)
- Works seamlessly with reverse proxy TLS termination

Key constraints:
- Single-page application or mobile client (unknown at spec time)
- Docker Compose deployment with nginx reverse proxy
- TLS termination at nginx layer

## Decision

Use **JWT (JSON Web Tokens) stored in HTTP-only secure cookies** for session management.

**Implementation details:**

**Token structure:**
```json
{
  "sub": "user-uuid",
  "exp": 1704153600,
  "iat": 1704067200,
  "type": "access"
}
```

**Algorithm:** HS256 (HMAC-SHA256)

**Cookie configuration:**
```
Set-Cookie: session_token=<JWT>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=86400
```

**Token lifecycle:**
1. User logs in → POST /api/v1/auth/login
2. Server validates credentials, creates JWT with 24h expiry
3. JWT returned as HTTP-only cookie (not in response body)
4. Browser automatically includes cookie on subsequent requests
5. Middleware extracts JWT, validates signature, loads user
6. Token invalidated on logout (client deletes cookie)

**Secret management:**
- JWT_SECRET: 32+ character random string from environment
- Stored in Docker secrets or .env file (not version controlled)

## Consequences

**Positive:**
- **XSS protection** — HTTP-only flag prevents JavaScript access to token
- **CSRF protection** — SameSite=Lax prevents cross-site request forgery
- **Stateless** — No server-side session storage required
- **TLS integration** — Secure flag ensures token only sent over HTTPS
- **Simple invalidation** — Client deletes cookie on logout
- **Works with any frontend** — No frontend token storage logic needed

**Negative:**
- **No immediate revocation** — Token valid until expiry (mitigated by 24h window)
- **Cookie size limit** — JWT must fit in 4KB cookie (sufficient for our payload)
- **CSRF still possible** — SameSite=Lax allows same-site requests (acceptable risk)
- **Token size** — JWT larger than opaque token (~200 bytes vs 32 bytes)

**Mitigations:**
- Immediate revocation: Add token to blacklist on logout (Redis/memory cache) — deferred to v2
- CSRF: Include CSRF token in forms if state-changing GET endpoints added
- Token size: Keep JWT payload minimal (user_id, exp, iat only)

**Security considerations:**
1. JWT_SECRET must be cryptographically random (use `secrets.token_urlsafe(32)`)
2. TLS mandatory — cookie never sent without Secure flag
3. Password never included in token
4. User roles/permissions looked up from DB on each request (not cached in token)

## Alternatives Considered

### Opaque session tokens (database-backed)
- **Pros:** Immediate revocation, full control over session lifecycle
- **Cons:** Requires database lookup on every request, session cleanup job needed
- **Verdict:** Considered for v2 if immediate revocation becomes critical

### JWT in Authorization header (Bearer scheme)
- **Pros:** Standard REST pattern, works with API clients
- **Cons:** Requires frontend to store token (XSS risk), manual token attachment
- **Verdict:** Rejected — HTTP-only cookie is more secure for browser clients

### Session cookies (server-side session store)
- **Pros:** Full control, immediate invalidation
- **Cons:** Requires Redis or database for session storage, not stateless
- **Verdict:** Rejected — adds infrastructure complexity for v1

### OAuth 2.0 / OpenID Connect
- **Pros:** Industry standard, supports SSO, third-party login providers
- **Cons:** Complex setup, overkill for single-household v1
- **Verdict:** Rejected — can add OAuth providers in v2 without changing token format

### API keys
- **Pros:** Simple, long-lived
- **Cons:** No expiry, no user context, poor security
- **Verdict:** Rejected — not suitable for user authentication

---

**Date:** 2026-04-02  
**Author:** Principal Engineer (AI)  
**Reviewers:** Specification Review Gate
