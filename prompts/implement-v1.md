# Prompt: implement v1 of the Conference Registration API

Copy everything below the line into a fresh session, started in an empty directory that contains copies of `conference-registration-spec.md`, `openapi-v1.yaml`, `implementation-plan-v1.md`, `package.json` and the `postman/` folder. Give every model the same prompt and the same files, so the results can be compared.

---

Implement **v1 ("Buy a ticket")** of the Conference Registration app. It is a backend-only HTTP API with no front end.

## Inputs, in order of precedence

1. `conference-registration-spec.md` is the behavior spec. Read section 11 (the version plan) first, then the sections it references: 4, 5.1, 5.2, 5.4, 5.5, 6.1, 7, 8 and 9.
2. `openapi-v1.yaml` is the HTTP contract. Implement all four of its operations exactly as written: paths, status codes, field names, money as integer cents, and `application/problem+json` errors with the `code` values it lists.
3. `implementation-plan-v1.md` sets the stack (Java, Quarkus, PostgreSQL, Flyway), the DDD layering, the transaction and locking design, and the order of the test-first slices.

Where the contract and the spec disagree on behavior, the spec wins. Where the plan marks something as a proposal to confirm, take the proposal as decided and record it under "Decisions" in the README. Don't stop to ask.

## Scope

- **In scope:** `GET /api/event`, `GET /api/ticket-types`, `POST /api/orders` and `POST /api/test/reset`, with the behavior described in `openapi-v1.yaml`. That includes capacity with overbooking, the order maximum, unique attendee emails per order, Luhn validation, the mock card decline on `0002`, `Idempotency-Key` replay, and never storing or echoing the card number or CVC.
- **Out of scope:** anything the plan lists as not in v1, such as magic links, discounts, email, QR images, cancellation, admin, audit log, sale-window enforcement, and consent or CVC checks. Don't build stubs or placeholders for them.
- **Configuration:** load it from a properties file that ships with the sample values in spec section 4. Test support (the reset endpoint) is off by default and is turned on by one documented setting.

## How to work

- Follow the plan's slices in order (section 5 of the plan). Work test-first: write one failing test, make it pass, then refactor.
- Commit at each green step with a message naming the slice.
- Concurrency (AC-06) must be proven with a test that sends real simultaneous requests to a real PostgreSQL database. A lock that only holds inside one JVM thread doesn't count.
- Don't add dependencies, layers or patterns the plan doesn't call for.

## Definition of done

1. `./mvnw verify` passes, including the integration and ArchUnit tests.
2. The app starts on `http://localhost:8080` with the sample configuration, an empty database and test support switched on. For example:
   `./mvnw quarkus:dev -Dregistration.test-support.enabled=true`
   Use whatever property name you chose, and document it.
3. The black-box conformance suite passes against the running app:
   `npm install && npm run test:v1`
   It is in the repository's `postman/` folder and will be run against your build. Don't change it. If a test seems wrong, explain why in the README rather than working around it.
4. The `docs/` diagrams below exist and match the code.
5. `README.md` covers how to build, run, test and reset the app, the property that switches on test support, "Decisions" (every choice the inputs left open), and "Known gaps" (anything not done or not verified, stated plainly).

## Diagrams

Write the diagrams **after** the code is green, by reading the code you wrote. Don't draw them from the plan. Each diagram is a fenced ` ```mermaid ` block in a Markdown file under `docs/`, with a sentence or two of explanation above it. Use real class, table, column and method names from the code. If a diagram and the code disagree, the diagram is wrong.

### `docs/class-diagrams.md` (`classDiagram`)

- **One diagram per layer:** `domain`, `application`, `api` and `infrastructure`. Show classes, records, interfaces and enums with their key fields and public methods. Use the right relationships: composition for aggregate-to-child, dependency, realization for interface implementations, and multiplicities.
- **The aggregate:** mark the aggregate root with the `<<AggregateRoot>>` stereotype, value objects with `<<ValueObject>>` and repositories with `<<Repository>>`.
- **An overview diagram of the layers:** show only the cross-layer dependencies, so it is visible that the domain depends on nothing else.
- Leave out getters, setters, constructors and framework boilerplate.

### `docs/entity-relationship.md` (`erDiagram`)

- Derive it from the Flyway migrations, not from the domain classes. One entity per table, with every column, its SQL type, and `PK`, `FK` and `UK` markers.
- Relationships must use the correct cardinality notation, for example `||--o{`.
- Below the diagram, list the unique constraints, check constraints, indexes, and the lock or version column used for the capacity invariant. Say which of them enforce NFR-4 or AC-22.
- If any table or column stores payment data, say which, and confirm it holds no full card number or CVC.

### `docs/sequence-diagrams.md` (`sequenceDiagram`)

Use the real participants: client, REST resource, application service, aggregate, mock payment, repository and database. Show where the transaction begins and commits or rolls back, and where the row lock is taken. Write one diagram per scenario:

1. `POST /api/orders` succeeds (AC-01): validation, lock, capacity check, payment approval, persist, commit, then 201.
2. The card is declined (AC-04): 402, rollback, and nothing persisted.
3. Sold out (AC-05): 409 with `remaining`, and no seats consumed.
4. Two concurrent orders compete for the last seat (AC-06): show the second request waiting on the lock and then getting 409. Use `par` blocks.
5. An `Idempotency-Key` replay returns the original confirmation, with no second payment or sale.
6. `POST /api/test/reset`, both enabled (204) and disabled (404). Use `alt`.
7. `GET /api/ticket-types`: how availability is computed without exposing counts.

Use `alt`, `opt`, `par` and `critical` blocks rather than separate near-duplicate diagrams where that reads better.

**Check that the diagrams render.** If `npx @mermaid-js/mermaid-cli` (`mmdc`) can be installed, render every block and fix any syntax errors. If it can't, say so in the README under "Known gaps".

## Final report

When you finish, reply with:

- what was built
- the exact commands you ran to verify it, with pass and fail counts from `./mvnw verify` and from `npm run test:v1`
- the decisions you made
- the known gaps

Don't claim anything you didn't run.
