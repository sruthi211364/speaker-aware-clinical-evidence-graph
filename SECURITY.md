# Security notes (prototype status)

This is a portfolio/demo build, not a HIPAA-compliant production system. This
document exists so that gap is explicit rather than implied, and so it's
clear what a real deployment would still need to add.

## What this prototype does today

- A single shared bearer token (`API_BEARER_TOKEN`) gates API access. There
  is no per-user identity, session management, or row-level access control --
  see `backend/app/auth.py`.
- No encryption at rest is configured for the Postgres volume.
- Claude API calls send transcript/claim content to Anthropic. No BAA is
  configured or assumed for this prototype.
- Policy engine decisions and attestations are logged with enough detail to
  reconstruct *why* a claim was accepted, blocked, or flagged, but that
  logging currently goes to local stdout/DB, not a retained, access-controlled
  audit store.
- Langfuse tracing (from Phase 5) sends call metadata to Langfuse's hosted
  service by default; no PHI-scrubbing pass is applied before that export.

## What a real deployment would need

1. **Encryption in transit and at rest** -- TLS everywhere, encrypted Postgres
   volumes/backups, encrypted object storage for any raw audio.
2. **Business Associate Agreements** with every third-party processor that
   sees PHI: Anthropic (Claude), AssemblyAI (if the raw-audio path is used),
   Langfuse (if hosted rather than self-hosted), and the hosting provider.
3. **Real authentication and RBAC** -- per-user identity (e.g. OAuth2/OIDC),
   scoped to clinician/patient/caregiver roles, with row-level access control
   so a clinician can only see their own patients' encounters.
4. **Audit log retention policy** -- a durable, tamper-evident, access-controlled
   store for the attestation trail and policy engine decisions, with a defined
   retention period matching applicable regulation.
5. **PHI-safe observability** -- tracing (Langfuse) and error monitoring must
   scrub or avoid transmitting raw transcript/claim text to any third-party
   service unless that service is itself BAA-covered and configured for it.
6. **Durable execution for the review pause.** The clinician-review node uses
   LangGraph's Postgres-backed checkpointer, which persists state across the
   `interrupt()` pause. That is sufficient for this prototype but is *not*
   the same guarantee as full durable execution across process crashes,
   infrastructure failures, or long-running multi-day pauses. A production
   deployment should add a durable-execution layer (e.g. the Temporal
   LangGraph plugin) in front of or around the graph so an in-progress review
   can survive an infrastructure failure without losing state.
7. **Consent and capture governance** for any raw-audio ingestion path --
   several 2026 lawsuits target ambient audio capture under state wiretap/consent
   statutes; a real deployment needs explicit per-encounter consent capture,
   not just a BAA with the ASR vendor.
8. **Secrets management** -- `.env` files are fine for local development only;
   production needs a real secrets manager (e.g. AWS Secrets Manager, Vault)
   and key rotation.
9. **FDA/regulatory pathway assessment** -- depending on how the policy
   engine's clinical-safety check (drug interaction / allergy flagging) is
   marketed and used, this may cross into clinical decision support subject
   to regulatory review. Out of scope for this build; flagged here so it
   isn't silently ignored.

None of the above is implemented in this repository. This file is
documentation of the gap, not a claim that it's closed.
