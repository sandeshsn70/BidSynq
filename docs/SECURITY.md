# Security
Implemented: bcrypt hashing, JWT with required exp/sub, server-side role and ownership checks, rate limiting on auth, upload type/size validation and safe filenames, security headers, strict CORS, production config guard, prompt-injection-hardened Groq prompt (document text treated as untrusted), tamper-evident audit log, no secrets in the repo.

This is **not** a claim that the app is completely secure. Residual risks:
- Rate limiting is in-memory per process (not shared across instances).
- JWT is kept in localStorage (readable by any XSS); there is no refresh/revocation mechanism.
- Uploaded documents are on local disk; ephemeral on Render without a persistent disk.
- Frontend `npm audit` still reports 5 high findings: `braces`/`micromatch` via `eslint-config-next` (dev/lint tooling only, no patched release exists at time of writing). `postcss` inside Next was overridden to 8.5.x; this works with the build but is not an officially tested combination.
- No real Groq call, Render deployment, or production-data test was performed by the author of this rebuild.
- No antivirus scanning of uploads; no email verification or password reset.
