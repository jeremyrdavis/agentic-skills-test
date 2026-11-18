# Conference Registration: v1 Implementation Plan

## Goal and source of truth

Deliver the backend-only "Buy a ticket" release from section 11 of
`conference-registration-spec.md`, using Java, Quarkus, Domain-Driven Design,
and test-driven development. Implement the applicable operations from
`openapi.yaml`; the behavior specification takes precedence where they differ.

This is a plan, not an instruction to implement the entire MVP. No frontend,
quotes, discounts, email, QR images, magic links, cancellation, refunds, admin,
audit log, or data-deletion functionality belongs in v1.

## 1. Establish the v1 contract

All paths below are relative to the contract's `/api` base path.

| Operation | v1 behavior | HTTP outcomes |
| --- | --- | --- |
| `GET /event` | Return configured event details, questions, policies, currency, and order maximum. Convert configured local event times using the IANA timezone to UTC. | `200` |
| `GET /ticket-types` | Return configured types, prices, UTC sale dates, and `available` or `sold_out`. Do not enforce sale windows or expose remaining counts. | `200` |
| `POST /orders` | Validate the v1 purchase rules, calculate prices on the server, check capacity atomically, simulate payment, and return a paid order with confirmed attendees and distinct confirmation numbers. | `201`, `402`, `409`, `422` |
| `POST /test/reset` | Restore the empty-registration state with sample configuration when test support is enabled. | `204`; `404` when disabled |

Use JSON for successful bodies and RFC 9457 `application/problem+json` for
documented business errors. Preserve the contract's lowercase status values,
integer-minor-unit money objects, UUID identifiers, and UTC timestamps.

### Version-specific compatibility rules

Write a small v1 contract-validation profile rather than changing the supplied
OpenAPI document or blindly generating all validation from its final-MVP schemas:

- Omit `buyerAccessUrl` from `OrderConfirmation`; section 11 explicitly permits it.
- Include all other required response fields. Use empty invoice details and
  answers, zero discount and refunded amounts, and `accommodationsRequested=false`
  rather than storing the deferred inputs.
- Include the required receipt and invoice URI references, but document that their
  target operations arrive in v3. Do not implement placeholder receipt pages.
- Return questions and policies from configuration even though v1 does not enforce
  answers or consent. Fill sample configuration gaps such as organizer details,
  policy URLs, and policy versions with clearly documented demo values.
- Accept requests without consents, as explicitly permitted by section 11. Do not
  validate or persist submitted consents, invoice details, or question answers.
- Do not enforce expiry freshness or CVC format. Do not accidentally enable these
  checks through generated validation annotations. Tolerate omitted deferred
  attendee fields; normalize their response representation to the defaults above.
- Accept but do not apply `discountCode` in v1; calculate and expose undiscounted
  prices and create no discount-usage records. Document this version limitation.
- Enforce v1 buyer/attendee identity fields, nonempty attendee collections, known
  ticket types, the order maximum, and card-number format plus Luhn.
- For a positive total, missing payment returns `422` with `payment_required`.
  The sample ticket prices are positive; free-order behavior belongs to v2.
- Honor the optional `Idempotency-Key` on order creation. A committed success
  replay returns the original confirmation without another sale or payment.
  Serialize simultaneous uses of the same key. Do not retain request bodies,
  card numbers, or CVCs to implement replay.

Before coding, turn these rules into explicit request/response fixtures and
review the v1 exceptions together. In particular, discount handling and tolerance
of omitted deferred fields are implementation proposals where section 11 does
not spell out every request-shape detail.

## 2. Bootstrap only the necessary stack

Proposed defaults, to confirm before generation:

| Setting | Proposal |
| --- | --- |
| Java | 25 |
| Build | Maven with Maven Wrapper |
| Coordinates | `io.arrogantprogrammer:conference-registration:1.0.0-SNAPSHOT` |
| Quarkus | Latest stable community release, verified and pinned at implementation time |
| Database | PostgreSQL, started by Quarkus Dev Services for development/tests |
| Extensions | `rest-jackson`, `hibernate-orm-panache`, `jdbc-postgresql`, `hibernate-validator`, `flyway` |
| Test tooling | Platform-compatible JUnit, AssertJ, REST Assured, ArchUnit |

Prefer the official Quarkus CLI with `--no-code`; use the official platform Maven
plugin if the CLI is unavailable. Manage Quarkus extensions through its tooling.
Resolve current test extension names against the selected platform rather than
assuming names embedded in the skills are still current.

The inspected environment has Docker on PATH, but Java, Maven, and the Quarkus
CLI were not found on PATH. Check the actual implementation environment and
Docker daemon access before installing anything. The current directory is not a
Git repository; agree on Git initialization before using the skills' green-commit
cadence. Scaffold into this project without overwriting the spec, contract, or
existing `.github/skills/`.

## 3. Proposed DDD model and transaction boundary

Use one bounded context, `registration`, in a modular monolith:

```text
{base}.registration.domain
{base}.registration.application
{base}.registration.infrastructure
{base}.registration.api
```

Enforce these boundaries with ArchUnit. Domain types use only Java and domain
types. Application depends on domain contracts. API resources call application
services. Infrastructure implements domain interfaces and owns ORM mappings.

### Consistency boundary

Capacity is shared across orders, and a mixed-ticket order must either place all
its tickets or none. Do not model each order and each ticket inventory as
independently committed aggregates and attempt eventual capacity reconciliation:
that would violate NFR-4.

Proposed demo-sized aggregate: `ConferenceRegistrationLedger`, representing
registration for this one conference. It owns recorded orders, their attendee
tickets, and the sales state needed to enforce caps. Orders and attendee tickets
are child entities, not independently persisted aggregate roots. Their conceptual
entities in section 7 do not mandate separate aggregate boundaries.

This deliberately coarse boundary fits a single-conference demo with no scale
target and satisfies the installed skills' one-aggregate-per-transaction rule.
It serializes purchases and is not proposed as a production-scale design.
Confirm this tradeoff before implementation; do not silently substitute
multi-aggregate writes or asynchronous seat accounting.

Suggested types, refined by the tests rather than generated in advance:

- Immutable records for `Money`, `EmailAddress`, typed IDs, `ConfirmationNumber`,
  event details, and ticket definitions.
- Named aggregate creation and `rehydrate(...)` factories; private mutable state,
  no public setters, and invariant-enforcing placement methods.
- Child order data includes the buyer, price snapshots, approved payment summary,
  attendees, order number, timestamp, and any successful idempotency key.
- No separate buyer account, payment aggregate, or attendee repository.
- One domain `ConferenceRegistrationLedgerRepository`, implemented under the same
  simple name in infrastructure. Query methods may return immutable domain
  availability summaries; application services map them to API DTOs.
- Application services for event queries, ticket queries, order placement, and
  the gated test reset. Transactions belong on application-service methods only.
- Pure mock-card logic produces approval/decline and a sanitized summary. Raw
  payment input is transient, never part of persisted aggregate state.

No event bus, Kafka, or transactional messaging outbox is needed in v1: there
are no required asynchronous side effects. Add event delivery when a later
version requires it, not to move a strict capacity invariant out of transaction.

## 4. Persistence and concurrency

Use Flyway migrations for the registration ledger, orders, attendees, sanitized
payment records, uniqueness constraints, and root version. ORM mirror types
remain in infrastructure; domain objects have no ORM annotations.

The order-placement application service owns one transaction:

1. Load and lock the conference registration root through its repository.
2. Check for an already committed result for the supplied idempotency key.
3. Validate the entire requested purchase and aggregate quantities by ticket type.
4. Recheck every requested type against its current confirmed sales and cap.
5. Apply the mock-card decision. A decline creates no persisted purchase state.
6. Create the complete order and confirmed tickets, with their identifiers and
   sanitized approved-payment summary; update sales within the root.
7. Persist and commit once. Return `201` only after successful transaction
   completion.

Use a database row lock on the singleton registration root for this demo.
Acquire it before checking capacity and hold it until commit; do not rely on a
Java `synchronized` block or an unlocked count-then-insert.

Keep a plain root version with infrastructure `@Version` protection. Repository
methods do not demarcate transactions or swallow conflicts. Enforce unique
confirmation numbers, order numbers, and non-null idempotency keys in the
database as well. If a generated confirmation collides, roll back and retry the
whole placement from the application boundary with a bounded policy.

Caps are exact integer calculations: `floor(baseline * (100 + percent) / 100)`,
using checked/wide arithmetic. Sample caps are Early Bird 110, General 440,
and Student 55. Price calculations use integer cents, not floating point.

For sold-out requests return `409`, `code=sold_out`, `ticketTypeId`, and current
`remaining`. A failed mixed-type purchase must not consume any seats.

## 5. Ordered test-first delivery slices

For each slice, write behavioral `[TEST]` comments in the relevant test file,
then select exactly one test at a time. Observe red, implement the minimum
green, and refactor separately. New types first produce a compile red, then a
behavioral red after adding stubs. Do not write the whole suite in advance.

| Slice | Behavior and first tests | Completion evidence |
| --- | --- | --- |
| 1. Configured event | Empty registration state returns the sample event; event times map to UTC; questions and policies are present. | `GET /api/event` contract tests and configuration mapping tests. |
| 2. Ticket catalog | Initially all sample types are available; prices are 29900, 49900, and 9900 USD; sale dates are returned but do not restrict purchases; listings omit counts. | `GET /api/ticket-types` tests. |
| 3. First purchase | One General ticket with the approved card costs 49900; order is `paid`, ticket is `confirmed`; a valid eight-character confirmation is returned. | AC-01 without email or QR-image checks; persisted aggregate round trip. |
| 4. Group purchase | A nonattending buyer buys three tickets; attendee confirmations differ; mixed types sum correctly; exactly ten tickets work; an email may recur in a different order. | AC-02 without emails and group boundary tests. |
| 5. Rejected purchases | Duplicate attendee emails, more than ten attendees, empty orders, unknown ticket types, invalid identity fields, missing payment, and invalid/Luhn-failing card numbers are refused. | `422` Problem Details tests, including `duplicate_attendee_email` and `order_too_large`; no changed sales after failure. |
| 6. Decline and retry | Luhn-valid `4000000000000002` declines; no order, tickets, or payment rows exist; retry with `4242424242424242` succeeds. | AC-04 and rollback tests; `402 payment_declined`. |
| 7. Capacity boundaries | Public purchases continue beyond baseline to cap; one remaining seat rejects a two-seat request without mutation; one-seat purchase succeeds and makes the type sold out. | AC-05 and AC-07; exact-cap and mixed-type rollback tests. |
| 8. Concurrent placement | Two simultaneous one-seat purchases compete for the last Student seat; exactly one succeeds. Replaying a successful idempotency key does not consume another seat. | AC-06 against real PostgreSQL, including simultaneous keyed requests. |
| 9. Sensitive data | Only last four digits, generated transaction ID, amount, approved result, and timestamp survive payment handling. Responses never echo raw card input. | AC-22 database-only checks across all application tables; response redaction tests. |
| 10. Reset and demo | Reset clears purchases, sales, replay state, and generated identifiers as appropriate; sample availability returns; reset is inaccessible when disabled. | `204`/`404` tests and a fresh-purchase-after-reset test. |

Within each slice, order cases from zero to one to many, then boundaries and
failures. Include "still works after failure" cases. Test repeat confirmations
and uniqueness behavior without depending on random luck; use a controllable
identifier source to force a collision where needed.

### Test tiers

- Plain-JVM tests cover aggregate invariants, amounts, caps, email normalization,
  confirmation format, and mock-card decisions without `@QuarkusTest`.
- `@QuarkusTest` with PostgreSQL Dev Services covers repository translation,
  application transactions, rollback, persistence constraints, and concurrency.
  Concurrency tests use separate real requests/transactions, not one wrapping
  `@TestTransaction`, and coordinate contenders rather than relying on sleeps.
- REST Assured tests check status, media type, contract fields, and externally
  visible behavior. Use the v1 compatibility profile for deliberate schema
  exceptions rather than falsely claiming full final-MVP OpenAPI compliance.
- Black-box HTTP tests get `@QuarkusIntegrationTest` companions for the packaged
  application; those tests must not depend on test-JVM injection or mocks.
- ArchUnit checks the four-layer dependency rules and framework-free domain.

Create capacity fixtures through application operations, not direct inserts.
For example, reach 54 Student tickets with valid orders of at most ten tickets.
Reset only between isolated scenarios, never while a concurrency test is active.

## 6. Reset, safety, and reproducibility

Expose reset only behind an explicit test-support setting, disabled by default.
It clears application registration data transactionally and preserves/reloads
the configured event definition. Repeated resets are harmless. The database has
no sample orders; initializing an empty ledger is infrastructure initialization,
not seeded attendee data.

Document a one-command reset using the enabled endpoint, for example:

```sh
curl --fail-with-body -X POST http://localhost:8080/api/test/reset
```

Keep card/CVC fields out of entity mirrors, request `toString()` output, request
body logging, and validation-error values. v1 acceptance scans the database;
avoid introducing logging leaks now even though the formal log scan arrives
in v2. Test fixtures use synthetic data only.

## 7. Verification and definition of done

During implementation, use continuous testing or focused Maven selectors.
Run the plain-JVM regression tier at each step and the container tier at green
and after refactoring. Run the existing formatter/linter if one is configured.
Final verification includes:

```sh
./mvnw verify -DskipITs=false
```

v1 is complete when:

- The four listed operations implement the v1 behavior and documented response
  profile, with no accidental sale-window, consent, expiry, or CVC enforcement.
- AC-01 and AC-02 pass with their v1 exclusions; AC-03 through AC-07 pass;
  AC-22 passes for the database.
- Orders, attendees, payments, sales, and replay state commit together or not
  at all; the real-database race never exceeds the cap.
- Confirmation numbers match `^[2-9A-HJ-NP-Z]{8}$` and are unique.
- The packaged app starts with sample properties and an empty database, can be
  reset with one command when enabled, and refuses reset when disabled.
- Architecture checks pass; all behavior-list items are resolved and no
  correctness concern remains untested.
- Startup, tests, reset, v1 limitations, and the approved/declined demo requests
  are documented. Deferred v2-v5 work remains deferred.

The spec's 15-20 minute sizing is a demo estimate, not a delivery guarantee;
toolchain setup, contract clarification, and real concurrency verification are
explicit prerequisites rather than work to skip to meet that estimate.
