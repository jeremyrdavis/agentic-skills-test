# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **spec plus a conformance suite**. It holds the input that is handed to different models/Skills, and the tests used to compare the implementations they produce. There is no application code here. The use case is a single-event conference registration app (sample event: "DevConf 2027").

Files:
- `conference-registration-spec.md` — behavior spec (requirements `FR-x.y`, `NFR-x`, business rules in section 6, acceptance criteria `AC-xx` in section 9, version plan in section 11).
- `openapi.yaml` — OpenAPI 3.1 HTTP contract that every build must implement.
- `postman/` — Newman/Postman conformance suite that runs against a live implementation (see below).
- `README.md` — one-line description.

## Conformance suite

```bash
npm install                  # newman
npm run test:v1              # runs the "v1 - Buy a ticket" folder against http://localhost:8080/api
uv run --with pyyaml postman/build_collection.py   # regenerate the collection
```

- `postman/conference-registration.postman_collection.json` is **generated** by `postman/build_collection.py` — edit the script, not the JSON. Response schemas are dereferenced from `openapi.yaml`, so regenerate after changing the contract.
- One top-level collection folder per spec version; only v1 exists so far. Requests within a folder depend on each other and must run in order against a server that has test support on (the first request calls `POST /test/reset`).
- When a requirement, operation or AC changes, update the matching tests in the builder as well as the version table in the spec. `postman/README.md` has more detail.

## How the two documents relate

- **The spec wins over the contract** wherever they disagree on behavior (stated in both files). Endpoints, payloads and status codes live in `openapi.yaml`; behavior lives in the spec.
- `openapi.yaml` descriptions cite spec requirement ids (FR/NFR/AC). When renaming, renumbering or removing a requirement, grep both files for the id and keep them consistent.
- Requirement numbering is intentionally not contiguous: section 5.8 uses `FR-9.x`, and the acceptance criteria skip AC-14, 15 and 20. Don't "fix" the gaps without checking references in section 11.
- The spec is stack-agnostic (language, framework, DB, hosting are chosen by the Skill). Don't add stack-specific requirements.

## Architecture the spec defines (big picture)

- **Users:** only attendees have identities. Buyers and attendees authenticate by **magic link** (`{baseUrl}/access/{token}`; token sent as `X-Access-Token`; ≥128-bit, stored hashed, scoped to one order or one attendee). Admin uses a shared passcode from the properties file → bearer token from `POST /admin/session` (8h idle expiry).
- **Configuration:** all event, ticket-type, question, consent, discount-code, admin-passcode and base-URL settings come from a **properties file read at startup** (sample values in spec section 4); no admin UI to edit them.
- **Externals are mocked or delegated:** payment is mocked (card ending `0002` declines; `4242…` approves; only last four digits stored). Email is never sent — the app stores generated emails (status starts `pending`) and an external sender polls/updates them via `/delivery/emails`.
- **Key invariants** that span many requirements: ticket caps = `floor(baseline × (1 + overbook%/100))` and discount usage limits must hold under concurrency; order placement is all-or-nothing; money is integer cents with per-ticket half-up percent rounding; times stored in UTC and shown in the event timezone; discount uses are not returned on cancellation; every mutation is audit-logged; GDPR deletion cancels/refunds first and keeps financial fields.
- **Test hooks required of every build:** a clock override (`/test/clock`) and reset-to-sample-state (`/test/reset`), enabled only when test support is on in config (otherwise 404).

## Versioned build plan

Spec section 11 splits the app into five incremental versions (v1 buy a ticket → v2 complete registration/magic links → v3 discounts, self-service, generated content → v4 admin/ops API → v5 front end). Each version lists the exact requirements, `openapi.yaml` operations and acceptance criteria it covers, and some v1 behavior is deliberately accepted-but-not-enforced until v2. When editing a requirement, operation or AC, update the corresponding row in the version table.
