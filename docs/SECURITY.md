# Security

## Threat model (summary)
| Asset / entry point | Threat | Control |
|---|---|---|
| Accounts (`/auth/*`) | Credential stuffing, brute force | Argon2id; per-IP fixed-window rate limit on login/register/refresh (429 + Retry-After); generic login errors |
| Access tokens | Forgery, confusion | HS256 JWT with iss/aud/typ checks, 15 min TTL; dev secret refused in staging/production |
| Refresh tokens | Theft and replay | Opaque, stored as SHA-256, rotated on use; reuse revokes the whole family |
| Per-user data (inventory, alerts) | IDOR | Every query scoped by user id; other users' objects return 404 |
| Request bodies | Mass assignment, resource exhaustion | Pydantic `extra="forbid"`, field limits, 64 KiB body limit (413) |
| Browser | XSS, clickjacking, MIME sniffing | React escaping (no raw HTML), CSP on API and SPA, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`; tokens kept in memory, never localStorage |
| Cross-origin | Unwanted browser access | CORS closed by default; explicit allowlist via `RECALLGRAPH_CORS_ORIGINS`, no credentials |
| Transport | Downgrade | HSTS in staging/production (TLS terminates at the load balancer) |
| AI explanations | Prompt injection, hallucinated safety claims | Evidence delimited as data; citation guard; forbidden safety claims; deterministic fallback; LLM never decides auth, scope, SQL or recall existence |
| Errors / logs | Information leakage | RFC 9457 problems without stack traces or echoed input; secrets are `SecretStr`, never logged |
| API docs | Reconnaissance | `/docs`, `/redoc`, `/openapi.json` disabled in staging/production |
| Supply chain / secrets | Vulnerable deps, leaked keys | CI: gitleaks (full history), pip-audit, npm audit |

## Known limitations
- The rate limiter is in-process: with several API instances each has its own window. A shared
  store (e.g. Redis) or a WAF rate rule is needed for multi-instance deployments.
- Refresh tokens are returned in the JSON body; the SPA keeps only the access token in memory, so
  a reload signs the user out (deliberate trade-off over storing tokens in the browser).

## Reporting
Please report vulnerabilities privately via GitHub Security Advisories on this repository.
