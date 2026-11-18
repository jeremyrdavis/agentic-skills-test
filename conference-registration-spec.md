# Conference Registration App — MVP Spec

Nov 12, 2026 · Jeremy Davis

## 1. Overview

This spec defines a web app for registering for a single, general-purpose conference. Its purpose is a demo: the same spec is handed to different Skills so the code each one produces can be compared.

- **Stack-agnostic.** Language, framework, database and hosting are set by the Skill under test, not by this spec.
- **API contract in openapi.yaml.** Endpoints, payloads and status codes are defined in the accompanying openapi.yaml, which every build must implement. This spec describes behavior.
- **Mocked externals.** Payment is mocked. Email delivery is delegated to another system; this app only generates and stores the email content.
- **Never launched.** There are no production, scale or uptime targets.

## 2. Scope

### In scope

- Event, ticket, question and discount-code configuration loaded from a properties file
- Public registration flow with group purchase and mock payment
- Confirmation numbers and QR codes per attendee
- Generated content: email text (stored in the database), invoice web page, calendar (.ics) file
- Attendee self-service through magic links
- Admin pages: attendee list, export, manual/comp registrations, cancellation with mock refund, dashboard, email outbox
- Accessibility, audit log, GDPR consent/export/deletion

### Out of scope

- Event lifecycle states (draft, published, closed) and editing event setup in the UI
- Real payment processing and real refunds
- Sending email (delivery, SPF/DKIM, bounces)
- Tax and VAT
- Refund and ticket-transfer policies
- On-site check-in; session or workshop selection (phase 2)
- Speakers and call for papers, sponsors, waitlists, badge printing
- Multiple currencies, attendee SSO, native mobile apps, CRM integrations, multi-tenancy
- Production concerns: scale, uptime, deployment

## 3. Users and access

Attendees are the only user type with identities. Admin pages exist but have no user accounts.

| Who | How they get in | Can do |
| --- | --- | --- |
| Buyer | Magic link for the order | View the order, all its attendees, the receipt and invoice; cancel the whole order or single tickets |
| Attendee | Magic link for their own registration | View and edit their details, view their receipt, cancel their own ticket |
| Admin | Shared admin passcode from the properties file | Everything in section 5.7 and the email outbox |

- The buyer does not have to attend. A buyer who also attends is listed as one of the attendees.
- No attendee passwords. Losing a magic link is handled by regenerating the confirmation from the admin pages.
- The admin passcode session expires after 8 hours of inactivity.

## 4. Configuration

All event setup lives in one properties file read at startup; there is no admin UI for it. The file format may follow the stack's conventions, but every implementation must support the settings below and ship with the sample values so builds are comparable.

| Group | Settings |
| --- | --- |
| Event | Name, description, start and end date-time, IANA timezone, venue name and address or virtual URL, organizer name and contact email, logo/banner image path |
| Currency | One ISO 4217 code for all prices |
| Ticket types | Per type: id, name, description, price, baseline capacity, sale start, sale end |
| Overbooking | Percentage over baseline capacity the public may buy (default 10) |
| Group purchase | Maximum tickets per order (default 10) |
| Questions | Per question: id, label, type (text, select, checkbox), required flag, options for select |
| Consents | Code of conduct URL and text; privacy policy URL and text |
| Discount codes | Per code: code, type (percent or fixed), amount, usage limit, optional allowed ticket type ids, optional expiry |
| Admin | Shared admin passcode |
| Links | Public base URL used in magic links and emails |

### Sample values

```
event.name=DevConf 2027
event.start=2027-04-14T09:00
event.end=2027-04-15T17:00
event.timezone=America/Chicago
event.venue=Austin Convention Center, 500 E Cesar Chavez St, Austin, TX
currency=USD

ticket.early.name=Early Bird
ticket.early.price=299.00
ticket.early.capacity=100
ticket.early.saleStart=2026-11-01T00:00
ticket.early.saleEnd=2027-01-31T23:59

ticket.general.name=General Admission
ticket.general.price=499.00
ticket.general.capacity=400
ticket.general.saleStart=2026-11-01T00:00
ticket.general.saleEnd=2027-04-13T23:59

ticket.student.name=Student
ticket.student.price=99.00
ticket.student.capacity=50
ticket.student.saleStart=2026-11-01T00:00
ticket.student.saleEnd=2027-04-13T23:59

capacity.overbookPercent=10
order.maxTickets=10

question.company.label=Company
question.company.type=text
question.company.required=false
question.shirt.label=T-shirt size
question.shirt.type=select
question.shirt.options=XS,S,M,L,XL,XXL
question.shirt.required=true
question.diet.label=Dietary requirements
question.diet.type=select
question.diet.options=None,Vegetarian,Vegan,Gluten-free,Other
question.diet.required=false

discount.SAVE20.type=percent
discount.SAVE20.amount=20
discount.SAVE20.limit=50
discount.SPEAKER100.type=percent
discount.SPEAKER100.amount=100
discount.SPEAKER100.limit=20
discount.SPEAKER100.ticketTypes=general
discount.FIFTYOFF.type=fixed
discount.FIFTYOFF.amount=50.00
discount.FIFTYOFF.limit=5

admin.passcode=change-me
app.baseUrl=http://localhost:8080
```

The accommodations checkbox and the two consent checkboxes are built in, not configurable questions.

## 5. Functional requirements

Requirement ids (FR-x.y) are referenced by the acceptance criteria in section 9.

### 5.1 Public event page

- **FR-1.1** Show event name, description, dates and times in the event timezone, venue or virtual link, organizer contact, and logo/banner.
- **FR-1.2** List ticket types with name, description, price and availability: "Available", "Not on sale yet", "Sale ended" or "Sold out".
- **FR-1.3** A ticket type is "Sold out" when sold tickets reach its overbooking cap (section 6.1). The page does not show remaining counts.

### 5.2 Registration and group purchase

- **FR-2.1** The buyer chooses a quantity per ticket type, from 1 up to the order maximum across all types.
- **FR-2.2** The buyer enters their name and email, plus optional invoice details: company name, billing address, PO number.
- **FR-2.3** For each ticket the buyer enters an attendee's first name, last name and email, the configured questions, and the accommodations checkbox ("I need special accommodations to attend"). A "This ticket is for me" shortcut copies the buyer's name and email into one ticket.
- **FR-2.4** Attendee emails must be unique within an order. The same email may hold tickets from different orders.
- **FR-2.5** The buyer must accept the code of conduct and privacy policy before paying. The acceptance time and policy version are stored.
- **FR-2.6** A review step shows every ticket, attendee, line price, discount and total before payment.
- **FR-2.7** Availability is checked again at payment. If any ticket type has run out, the order is not placed and the buyer is told which type and how many remain.

### 5.3 Discount codes

- **FR-3.1** The buyer may enter one discount code per order on the review step.
- **FR-3.2** Invalid, expired, used-up or not-applicable codes are rejected with a specific message.
- **FR-3.3** The discount applies per ticket to eligible ticket types only, and each discounted ticket counts as one use.
- **FR-3.4** A fixed-amount discount cannot take a ticket below zero. A 100% discount makes the ticket free.

### 5.4 Mock payment

- **FR-4.1** The payment form takes cardholder name, card number, expiry and CVC, and validates their format (number passes the Luhn check, expiry not in the past, CVC 3–4 digits).
- **FR-4.2** A card number ending in `0002` is declined; any other valid number succeeds. A declined order is not placed and the buyer can retry.
- **FR-4.3** Only the last four digits and a generated mock transaction id are stored. Full card number and CVC are never stored or logged.
- **FR-4.4** Orders with a total of zero skip the payment form.

### 5.5 Confirmation

- **FR-5.1** A successful order gets an order number. Each ticket gets its own confirmation number (8 characters, no ambiguous characters such as 0/O and 1/I) and a QR code that encodes it.
- **FR-5.2** The confirmation page shows the order summary, every attendee's confirmation number, the buyer's magic link, and links to the receipt and invoice.
- **FR-5.3** Generated on success: one order confirmation email to the buyer and one ticket email to each attendee (section 5.8).

### 5.6 Attendee self-service

- **FR-6.1** An attendee's magic link opens their registration: details, ticket type, confirmation number, QR code, .ics download and receipt.
- **FR-6.2** Attendees can edit their name, email, question answers and accommodations checkbox until the event starts. Ticket type cannot be changed.
- **FR-6.3** Attendees can cancel their own ticket until the event starts, after confirming. This triggers a mock refund and a cancellation email.
- **FR-6.4** The buyer's magic link shows the whole order, receipt and invoice, lets the buyer edit invoice details, and lets the buyer cancel any ticket or the whole order.
- **FR-6.5** Attendees can download their personal data as JSON and request deletion (section 6.5).

### 5.7 Admin

- **FR-7.1** Attendee list with search (name, email, confirmation number, order number) and filters (ticket type, status, accommodations requested). Paged, sortable by name and registration date.
- **FR-7.2** CSV export of the current filtered list, including question answers and the accommodations flag.
- **FR-7.3** Attendee detail view showing all fields, order, payment status and audit history.
- **FR-7.4** Add an attendee manually at full price (marked "paid offline") or as a comp (price zero). Comps need a reason.
- **FR-7.5** Cancel any ticket or order with a mock refund and a reason.
- **FR-7.6** Regenerate the confirmation or ticket email, which issues a new magic link and invalidates the old one.
- **FR-7.7** Dashboard: per ticket type, sold vs. baseline vs. cap; totals for gross revenue, discounts, refunds and net revenue; count of accommodation requests; uses left per discount code.
- **FR-7.8** Email outbox: list generated emails, filter by type and recipient, and preview the text and HTML versions.
- **FR-7.9** Audit log viewer, filterable by attendee and by action.

### 5.8 Generated content

- **FR-9.1** Every email is stored in the database with: type, recipient, subject, plain-text body, HTML body, related order/attendee, created time, and a delivery status (starts as "pending") for the external sender to update.
- **FR-9.2** Email types: order confirmation (buyer), ticket (attendee, with QR code, confirmation number, magic link and .ics), receipt (buyer), cancellation (buyer and affected attendee), and reminder (each active attendee).
- **FR-9.3** Reminders are generated from an admin button, once per attendee. Pressing it again only reaches attendees who have not had one.
- **FR-9.4** Receipt and invoice pages are printable HTML: seller details, invoice/order number, date, buyer and invoice details, line items, discount, total, payment method ("Card ending 4242" or "Comp"), and any refunds.
- **FR-9.5** The .ics file holds the event title, start and end with timezone, location and the attendee's confirmation number.

## 6. Business rules

### 6.1 Capacity and overbooking

- Each ticket type's cap = floor(baseline capacity × (1 + overbooking percent / 100)). With the sample values: Early Bird 110, General 440, Student 55.
- Sold = tickets in Confirmed state. Cancelled tickets free their seat immediately.
- The public can buy until sold reaches the cap. Concurrent orders must never push sold past the cap.
- Admins may exceed the cap only with an explicit override, which is recorded in the audit log.

### 6.2 Discounts and money

- One code per order. If eligible tickets in the order exceed the code's remaining uses, the code is rejected with the number of uses left.
- Uses are consumed when the order is placed and are not returned on cancellation. Concurrent orders must never exceed a code's usage limit.
- Store money as integer minor units (cents). Percent discounts round half-up to the cent, per ticket.
- A refund equals the amount actually paid for that ticket after its discount.

### 6.3 Ticket lifecycle

- A ticket is created as **Confirmed** when its order is paid (or is free). There is no pending or held state.
- **Confirmed → Cancelled** by the attendee, buyer or admin, with a mock refund. Cancelled is final.
- An order is **Paid** while all its tickets are active, **Partially cancelled** when some are, and **Cancelled** when all are.
- Attendee edits and cancellations close at the event start time. Admin actions stay open.

### 6.4 Magic links

- Tokens are random with at least 128 bits of entropy and stored only as a hash.
- Each link is scoped to one attendee or one order (buyer). An order link never grants access to another order.
- Links stay valid until 30 days after the event ends, or until regenerated (FR-7.6).

### 6.5 Personal data deletion

- An active ticket is cancelled (with mock refund) before its attendee's data is deleted.
- Deletion replaces name with "Deleted attendee" and clears email, question answers and the accommodations flag. Bodies of that person's stored emails are cleared.
- Kept for financial records: confirmation number, ticket type, amounts, payment and refund records.
- Audit entries stay, with personal details replaced by the attendee's internal id.

### 6.6 Time

- Store all times in UTC. Show them in the event timezone, labelled with the zone abbreviation.

## 7. Data model (conceptual)

These are the entities and the facts they must hold; table design, naming and keys are left to the implementation. Ticket types, questions and discount-code definitions come from configuration and are referenced by id.

| Entity | Key facts | Relationships |
| --- | --- | --- |
| Order | Order number, buyer name and email, invoice details (company, billing address, PO), status, subtotal, discount, total, created time | Has many Attendees; one Payment; zero or more Refunds |
| Attendee (ticket) | Confirmation number, ticket type id, first/last name, email, accommodations flag, status, price paid, source (public, admin paid offline, comp) and comp reason | Belongs to one Order; has many Answers |
| Answer | Question id, value | Belongs to one Attendee |
| Consent | Policy type, policy version, accepted time | Belongs to one Order |
| Payment | Mock transaction id, card last four, amount, result (approved, declined), time | Belongs to one Order |
| Refund | Amount, reason, mock refund id, time, who triggered it | Belongs to one Order and one Attendee |
| Discount usage | Code, uses consumed | One row per configured code; Orders record which code they used |
| Magic link | Token hash, scope (attendee or order), expiry, revoked flag | Belongs to one Attendee or Order |
| Email message | Type, recipient, subject, text body, HTML body, delivery status, created time | Linked to an Order and/or Attendee |
| Audit entry | Time, actor (public, buyer, attendee, admin), action, target, before/after values | References the affected record |

## 8. Non-functional requirements

- **NFR-1 Accessibility.** All pages meet WCAG 2.1 AA: keyboard-only use, visible focus, labelled form fields, errors announced to screen readers, 4.5:1 text contrast, no information carried by colour alone.
- **NFR-2 Responsive.** Every page works from 360 px wide phones to desktop.
- **NFR-3 Payment data.** No full card number or CVC is stored, logged or sent to the browser after submission (FR-4.3).
- **NFR-4 Consistency.** Ticket caps and discount usage limits hold under concurrent requests (sections 6.1 and 6.2). Placing an order is all-or-nothing: tickets, payment, discount use and emails are recorded together or not at all.
- **NFR-5 Audit log.** Every create, edit, cancel, refund, override, link regeneration, data export and deletion is recorded with actor, time and before/after values. Entries cannot be edited or deleted through the app.
- **NFR-6 Privacy.** Consent captured per FR-2.5, data export per FR-6.5, deletion per section 6.5. The accommodations flag is shown only on admin pages and in the CSV export.
- **NFR-7 Security basics.** Admin pages require the passcode; magic-link pages show only their scope; inputs are validated on the server; output is escaped; forms are protected against cross-site request forgery.
- **NFR-8 Testability.** The app starts from the sample properties file with an empty database, and can be reset to that state with one command.

## 9. Acceptance criteria

Each build passes when every criterion below holds, starting from the sample properties file and an empty database. Card `4242 4242 4242 4242` is approved; `4000 0000 0000 0002` is declined.

| ID | Covers | Given | When | Then |
| --- | --- | --- | --- | --- |
| AC-01 | FR-2, FR-4, FR-5 | General is on sale | A buyer buys 1 General ticket for themselves with the approved card | The order is Paid at 499.00; one confirmation number and QR code exist; an order confirmation and a ticket email are stored as "pending" |
| AC-02 | FR-2.1, FR-2.3, FR-5.3 | General is on sale | A buyer who is not attending buys 3 General tickets for 3 different attendees | 3 tickets with distinct confirmation numbers; 1 order confirmation to the buyer and 1 ticket email to each attendee; the buyer is not listed as an attendee |
| AC-03 | FR-2.4 | A cart with 2 tickets | Both attendees are given the same email | The review step is blocked with a duplicate-email error |
| AC-04 | FR-4.2 | A valid cart | The buyer pays with the declined card | No order, tickets, discount use or emails are created; the buyer can retry with another card |
| AC-05 | FR-2.7, 6.1 | 54 Student tickets sold (cap 55) | A buyer orders 2 Student tickets | The order is rejected with "1 remaining"; ordering 1 succeeds; Student then shows "Sold out" |
| AC-06 | 6.1, NFR-4 | 54 Student tickets sold | Two orders for 1 Student ticket are submitted at the same moment | Exactly one succeeds; sold ends at 55 |
| AC-07 | 6.1 | 50 Student tickets sold (baseline 50) | The public page is loaded | Student shows "Available" and can be bought |
| AC-08 | FR-3.3, 6.2 | SAVE20 has 50 uses left | A buyer applies SAVE20 to 2 General tickets | Each ticket costs 399.20; total 798.40; SAVE20 has 48 uses left |
| AC-09 | FR-3.2, FR-3.4, FR-4.4 | SPEAKER100 is limited to General | It is applied to an Early Bird ticket, then to a General ticket | Early Bird: rejected as not applicable. General: total 0.00 and the payment form is skipped |
| AC-10 | 6.2 | FIFTYOFF has 1 use left | It is applied to 2 General tickets | Rejected with "1 use left" |
| AC-11 | FR-1.2 | The current time is after Early Bird's sale end | The public page is loaded | Early Bird shows "Sale ended" and cannot be bought |
| AC-12 | FR-6.3, 6.2 | An attendee paid 399.20 with SAVE20 | The attendee cancels from their magic link | Ticket Cancelled; a 399.20 mock refund is recorded; the seat is freed; SAVE20 uses are unchanged; cancellation emails go to buyer and attendee; an audit entry exists |
| AC-13 | FR-6.2, FR-6.3 | The event has started | An attendee tries to edit or cancel | Both are refused with a message; an admin can still do both |
| AC-16 | FR-7.4 | Admin is signed in | Admin adds a comp ticket without a reason, then with one | Without: rejected. With: ticket at 0.00, invoice shows "Comp", source recorded as comp |
| AC-17 | 6.1 | General has reached its cap of 440 | Admin adds one more General ticket, first without and then with the override | Without: rejected. With: created, sold is 441, the override is in the audit log |
| AC-18 | FR-7.6, 6.4 | An attendee has a magic link | Admin regenerates the ticket email | The old link is refused; the new link works |
| AC-19 | FR-7.2, NFR-6 | Some attendees requested accommodations | Admin filters by accommodations and exports CSV | Only those attendees are exported, with answers and the flag |
| AC-21 | 6.5 | An attendee holds a Confirmed paid ticket | They request deletion | Ticket cancelled with refund; name shows "Deleted attendee"; email, answers and flag cleared; amounts and confirmation number kept; audit entries show only the internal id |
| AC-22 | FR-4.3, NFR-3 | Several orders were paid | The database and logs are searched for the full test card numbers and CVCs | Nothing is found; only last four digits are stored |
| AC-23 | FR-9.3 | 3 active and 1 cancelled attendee | Admin presses "Generate reminders" twice | Exactly 3 reminder emails exist |
| AC-24 | FR-7.7 | After AC-08 and AC-12 have run | The dashboard is opened | Gross, discounts, refunds and net match the orders, and sold counts match the tickets |
| AC-25 | NFR-1 | Any public or self-service page | An automated accessibility scan (e.g., axe-core) runs | No serious or critical violations |

## 10. Notes for implementers and agreed decisions

### Notes

- **Clock override.** AC-11 and AC-13 depend on the current time. Every build must let tests set the current time (for example, a config value or test-only hook) without changing the system clock.
- **API contract.** The HTTP API is defined in openapi.yaml, delivered alongside this spec. Builds must implement it as written. Where this spec and the contract disagree on behavior, this spec wins.
- **Seed state.** Builds start empty; tests create their own data through the app (NFR-8).

### Agreed decisions

These rules were proposed while drafting and agreed on Nov 18, 2026.

- Admins can exceed the ticket cap with an audit-logged override (6.1)
- Discount uses are not returned when a ticket is cancelled (6.2)
- A code with fewer uses left than eligible tickets is rejected, not partly applied (6.2)
- Maximum 10 tickets per order (section 4)
- Reminders are generated from an admin button, not on a schedule (FR-9.3)
- Magic links expire 30 days after the event; admin sessions after 8 hours idle (6.4, section 3)
- Deleting personal data cancels and refunds an active ticket first (6.5)

## 11. Version plan

The app is built in five steps: four backend-only versions (API, no pages), then the front end. Each version adds to the previous one, and each has its own acceptance criteria so it can be demoed and tested alone. A version implements `openapi.yaml` for the operations it lists; the notes below say what v1 leaves out of those operations.

| Version | Theme | Requirements | API operations (openapi.yaml) | Acceptance criteria |
| --- | --- | --- | --- | --- |
| v1 | Buy a ticket | Configuration (section 4: event, currency, ticket types, overbooking, order maximum); FR-1.1; FR-1.2 and FR-1.3 with availability "Available" or "Sold out" only; FR-2.1; FR-2.2 (buyer name and email); FR-2.3 (attendee name and email); FR-2.4; FR-2.7; FR-4.1 (Luhn check only); FR-4.2; FR-4.3; FR-5.1 (confirmation numbers, no QR image); capacity and overbooking (6.1); NFR-3, NFR-4, NFR-8 | `GET /event`, `GET /ticket-types`, `POST /orders`, `POST /test/reset` | AC-01 and AC-02 (without the email checks), AC-03 to AC-07, AC-22 (database only) |
| v2 | Complete registration | FR-1.2 sale windows ("Not on sale yet", "Sale ended"); rest of FR-2.2 (invoice details); rest of FR-2.3 (questions, accommodations checkbox); FR-2.5; rest of FR-4.1 (expiry, CVC); FR-4.4; magic links, read-only (6.4); clock override; questions and consents configuration (section 4) | `POST /quotes`, `GET /my`, `GET /my/order`, `GET /my/attendee`, `/test/clock` | AC-11; AC-22 (logs) |
| v3 | Discounts, self-service and generated content | FR-3.1–3.4 and 6.2; FR-5.3; FR-6.1–6.5 (edit, cancel, mock refund, data export and deletion, 6.3, 6.5); FR-9.1, FR-9.2, FR-9.4, FR-9.5; QR code image; audit entries recorded (NFR-5); admin passcode sign-in, needed to read the outbox | `discountCode` on quotes and orders; `PATCH /my/attendee`; the cancel, invoice-details, qr, calendar, receipt, invoice, data-export and data-deletion operations under `/my`; `/admin/session`; `/admin/emails`; `/delivery/emails` | Email checks of AC-01 and AC-02; AC-08 to AC-10, AC-12, AC-13 (attendee part), AC-21 |
| v4 | Admin and operations API | FR-7.1–7.7, FR-7.9; FR-9.3 reminders; cap override (6.1) | `/admin/attendees` and its sub-paths, `/admin/orders`, `/admin/dashboard`, `/admin/reminders`, `/admin/audit-log` | AC-13 (admin part), AC-16 to AC-19, AC-23, AC-24 |
| v5 | Front end | Every page over the v1–v4 API: public event page and registration flow (FR-2.6 review step), confirmation page (FR-5.2), self-service pages, admin pages (FR-7.8 preview); NFR-1, NFR-2, form protections in NFR-7 | No new operations | AC-25, plus a walkthrough of AC-01, AC-08 and AC-12 in the browser |

### Notes on the split

- **v1 is one flow plus two rules:** buy tickets with the mock card and get confirmation numbers, plus capacity under concurrency and no stored card data. It is sized to build in about 15 to 20 minutes.
- **What v1 leaves out of its operations.** v1 responses carry every required contract field except `buyerAccessUrl` on the order confirmation, which arrives with magic links in v2. `GET /event` returns questions and policies as configured. `GET /ticket-types` returns sale dates as data but does not act on them.
- **What v1 accepts but does not enforce.** `POST /orders` accepts contract-valid requests. v1 does not check or store consents, question answers or invoice details, and does not check card expiry or CVC format. v2 starts enforcing them. This is the one place where a later version tightens earlier behavior: a request that v1 accepted without consents is refused from v2 on.
- **v2 completes the original v1.** v1 and v2 together are the "core registration API" of the earlier four-version plan.
- **Printable receipt and invoice** are HTML returned by the API, so they sit in v3 as generated content, not in the front end.
- **Audit recording starts in v3**, where the first edits and cancellations appear, and must also cover order placement from v1. The viewer arrives in v4.
- **Fewer versions:** merge v1 and v2 for the earlier core API, or merge v3 and v4 into one backend release.
