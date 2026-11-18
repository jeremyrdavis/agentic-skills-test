#!/usr/bin/env python3
"""Generate the Postman collection from openapi.yaml plus the test definitions below.

    uv run --with pyyaml postman/build_collection.py

The committed collection JSON is a build artifact of this script. Response schemas are
dereferenced from openapi.yaml so the suite checks conformance to the real contract and
cannot drift from it. To add a version (v2, v3, ...), add a `build_vN()` folder and
append it to `collection["item"]` in `main()`.
"""
import copy
import json
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent
OPENAPI = yaml.safe_load((ROOT.parent / "openapi.yaml").read_text())
OUT = ROOT / "conference-registration.postman_collection.json"

# ----------------------------------------------------------------------------- schemas

# Annotation-only keywords: dropped so strict JSON Schema validators accept the schema.
ANNOTATIONS = {"description", "example", "examples", "writeOnly", "readOnly", "summary"}


def deref(node):
    """Inline every $ref and strip annotations, giving a standalone JSON Schema."""
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[1]
            return deref(OPENAPI["components"]["schemas"][name])
        return {k: deref(v) for k, v in node.items() if k not in ANNOTATIONS}
    if isinstance(node, list):
        return [deref(v) for v in node]
    return node


def schema(name):
    return deref(OPENAPI["components"]["schemas"][name])


def schema_vars():
    # v1 does not return buyerAccessUrl (magic links arrive in v2) - spec section 11.
    order_v1 = schema("OrderConfirmation")
    order_v1["required"] = [r for r in order_v1["required"] if r != "buyerAccessUrl"]
    return {
        "schema_Event": schema("Event"),
        "schema_TicketTypes": {"type": "array", "items": schema("TicketType")},
        "schema_OrderConfirmation_v1": order_v1,
        "schema_Problem": schema("Problem"),
    }


# ----------------------------------------------------------------------------- helpers

APPROVED_CARD = {"cardholderName": "Pat Buyer", "number": "4242424242424242",
                 "expMonth": 12, "expYear": 2035, "cvc": "123"}
SECOND_CARD = {**APPROVED_CARD, "number": "5555555555554444"}   # a different Luhn-valid card
DECLINED_CARD = {**APPROVED_CARD, "number": "4000000000000002"}  # Luhn-valid, ends in 0002
BAD_LUHN_CARD = {**APPROVED_CARD, "number": "4242424242424241"}  # fails the Luhn check

BUYER = {"name": "Pat Buyer", "email": "pat.buyer@example.com"}


def attendee(ticket, first, last, email, accommodations=False):
    # `answers` is optional in v1 but the sample config makes the shirt question
    # required from v2 on, so send it now and the same requests keep working.
    return {"ticketTypeId": ticket, "firstName": first, "lastName": last, "email": email,
            "answers": {"shirt": "M"}, "accommodationsRequested": accommodations}


def order(attendees, card=APPROVED_CARD, buyer=BUYER):
    body = {
        "buyer": buyer,
        "attendees": attendees,
        "consents": [
            {"type": "code_of_conduct", "version": "{{cocVersion}}", "accepted": True},
            {"type": "privacy", "version": "{{privacyVersion}}", "accepted": True},
        ],
    }
    if card:
        body["payment"] = card
    return body


def request(name, method, path, tests, description, body=None):
    req = {"method": method, "header": [], "description": description,
           "url": {"raw": "{{baseUrl}}" + path, "host": ["{{baseUrl}}"],
                   "path": path.strip("/").split("/")}}
    if body is not None:
        req["header"].append({"key": "Content-Type", "value": "application/json"})
        req["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2),
                       "options": {"raw": {"language": "json"}}}
    return {"name": name, "request": req,
            "event": [{"listen": "test",
                       "script": {"type": "text/javascript", "exec": tests}}]}


def folder(name, items, description=None):
    out = {"name": name, "item": items}
    if description:
        out["description"] = description
    return out


def gwt(given, when, then):
    return f"**Given** {given}\n\n**When** {when}\n\n**Then** {then}"


# Reusable test snippets (JavaScript, run in Postman's sandbox / Newman).
def status(code, label):
    return f'pm.test("Status is {code} {label}", () => pm.response.to.have.status({code}));'


def matches_schema(var, label):
    return (f'pm.test("Response matches the {label} schema in openapi.yaml", () => '
            f"pm.response.to.have.jsonSchema(JSON.parse(pm.collectionVariables.get('{var}'))));")


def is_problem(code):
    return [
        'pm.test("Error is RFC 9457 application/problem+json", () => {',
        "  pm.expect(pm.response.headers.get('Content-Type') || '').to.include('application/problem+json');",
        "  pm.response.to.have.jsonSchema(JSON.parse(pm.collectionVariables.get('schema_Problem')));",
        "});",
        f'pm.test("Error code is {code}", () => pm.expect(pm.response.json().code).to.eql("{code}"));',
    ]


def student_ticket_types_test(expected):
    return [
        status(200, "OK"),
        f'pm.test("Student availability is {expected}", () => {{',
        '  const student = pm.response.json().find(t => t.id === "student");',
        f'  pm.expect(student.availability).to.eql("{expected}");',
        "});",
    ]


# ----------------------------------------------------------------------------- v1

STUDENT_SEQ = {"n": 0}


def sell_students(count, label, description):
    """A visible setup request that buys `count` Student tickets (unique emails)."""
    atts = []
    for _ in range(count):
        STUDENT_SEQ["n"] += 1
        n = STUDENT_SEQ["n"]
        atts.append(attendee("student", "Student", f"No{n}", f"student{n}@example.com"))
    return request(
        label, "POST", "/orders",
        [status(201, "Created"),
         f'pm.test("{count} Student tickets were issued", () => '
         f"pm.expect(pm.response.json().order.attendees.length).to.eql({count}));"],
        description, order(atts))


def build_v1():
    STUDENT_SEQ["n"] = 0

    reset = folder("Reset (NFR-8)", [
        request(
            "Reset to an empty database with sample configuration", "POST", "/test/reset",
            [status(204, "No Content"),
             "pm.test(\"Response has no body\", () => pm.expect(pm.response.text()).to.eql(''));"],
            "Every run starts from the sample properties file and an empty database. "
            "Test support must be switched on, otherwise this returns 404 and the whole run is invalid.")])

    public = folder("Public pages (FR-1.1, FR-1.2, FR-1.3)", [
        request(
            "FR-1.1: GET /event returns the configured event", "GET", "/event",
            [status(200, "OK"),
             matches_schema("schema_Event", "Event"),
             'const event = pm.response.json();',
             'pm.test("Sample event values from spec section 4", () => {',
             '  pm.expect(event.name).to.eql("DevConf 2027");',
             '  pm.expect(event.timezone).to.eql("America/Chicago");',
             '  pm.expect(event.startsAt).to.eql("2027-04-14T14:00:00Z");  // 09:00 CDT',
             '  pm.expect(event.endsAt).to.eql("2027-04-15T22:00:00Z");    // 17:00 CDT',
             '  pm.expect(event.currency).to.eql("USD");',
             '  pm.expect(event.maxTicketsPerOrder).to.eql(10);',
             '});',
             'pm.test("Venue is present", () => pm.expect(event.venue.address).to.include("Austin"));',
             "// Later requests need the current policy versions to send consents.",
             "const version = type => ((event.policies || []).find(p => p.type === type) || {}).version || '1';",
             "pm.collectionVariables.set('cocVersion', version('code_of_conduct'));",
             "pm.collectionVariables.set('privacyVersion', version('privacy'));"],
            "Returns event name, dates, timezone, venue, organizer, currency, order maximum, "
            "questions and policies, all from the properties file."),
        request(
            "FR-1.2 / FR-1.3: GET /ticket-types lists the three sample types", "GET", "/ticket-types",
            [status(200, "OK"),
             matches_schema("schema_TicketTypes", "TicketType[]"),
             'const types = pm.response.json();',
             'pm.test("Early Bird, General Admission and Student, with sample prices in cents", () => {',
             '  const byId = Object.fromEntries(types.map(t => [t.id, t]));',
             '  pm.expect(Object.keys(byId).sort()).to.eql(["early", "general", "student"]);',
             '  pm.expect(byId.early.price).to.eql({ amount: 29900, currency: "USD" });',
             '  pm.expect(byId.general.price).to.eql({ amount: 49900, currency: "USD" });',
             '  pm.expect(byId.student.price).to.eql({ amount: 9900, currency: "USD" });',
             '});',
             'pm.test("Every type is Available on an empty database", () =>',
             '  types.forEach(t => pm.expect(t.availability).to.eql("available")));',
             'pm.test("Remaining counts and capacity are never exposed (FR-1.3)", () =>',
             '  types.forEach(t => ["remaining", "capacity", "cap", "sold", "available"].forEach(k =>',
             '    pm.expect(t).to.not.have.property(k))));'],
            "Availability is `available` or `sold_out` in v1. Sale dates are returned as data but "
            "not enforced until v2. The public page never shows how many tickets are left.")])

    ac01 = folder("AC-01: Buy 1 General ticket for yourself", [
        request(
            "AC-01: order 1 General ticket with the approved card", "POST", "/orders",
            [status(201, "Created"),
             matches_schema("schema_OrderConfirmation_v1", "OrderConfirmation (v1: no buyerAccessUrl)"),
             "const body = pm.response.json();",
             "const o = body.order;",
             'pm.test("Order is paid at 499.00 USD", () => {',
             '  pm.expect(o.status).to.eql("paid");',
             '  pm.expect(o.subtotal).to.eql({ amount: 49900, currency: "USD" });',
             '  pm.expect(o.discount).to.eql({ amount: 0, currency: "USD" });',
             '  pm.expect(o.total).to.eql({ amount: 49900, currency: "USD" });',
             '});',
             'pm.test("Order has an order number", () => pm.expect(o.orderNumber).to.be.a("string").and.not.empty);',
             'pm.test("Exactly one attendee with an 8-character confirmation number (FR-5.1)", () => {',
             '  pm.expect(o.attendees).to.have.lengthOf(1);',
             '  pm.expect(o.attendees[0].confirmationNumber).to.match(/^[2-9A-HJ-NP-Z]{8}$/);',
             '  pm.expect(o.attendees[0].status).to.eql("confirmed");',
             '  pm.expect(o.attendees[0].pricePaid.amount).to.eql(49900);',
             '});',
             'pm.test("Payment shows card ending 4242 and a mock transaction id (FR-4.3)", () => {',
             '  pm.expect(o.payment.method).to.eql("card");',
             '  pm.expect(o.payment.cardLast4).to.eql("4242");',
             '  pm.expect(o.payment.transactionId).to.be.a("string").and.not.empty;',
             '  pm.expect(o.payment.result).to.eql("approved");',
             '  pm.expect(o.payment.amount.amount).to.eql(49900);',
             '});',
             'pm.test("AC-22 (API part): full card number and CVC are not echoed back (NFR-3)", () => {',
             "  const text = pm.response.text();",
             '  pm.expect(text).to.not.include("4242424242424242");',
             "  pm.expect(text).to.not.match(/\"cvc\"/i);",
             '  pm.expect(text).to.not.match(/\"number\"/i);',
             '});',
             "pm.collectionVariables.set('ac01Confirmation', o.attendees[0].confirmationNumber);"],
            gwt("General is on sale",
                "a buyer buys 1 General ticket for themselves with card 4242 4242 4242 4242",
                "the order is Paid at 499.00, one confirmation number exists, and the response "
                "contains no full card number or CVC. (QR image and emails are v3.)"),
            order([attendee("general", "Pat", "Buyer", "pat.buyer@example.com")]))])

    ac02 = folder("AC-02: Buyer who is not attending buys 3 General tickets", [
        request(
            "AC-02: order 3 General tickets for 3 other people", "POST", "/orders",
            [status(201, "Created"),
             matches_schema("schema_OrderConfirmation_v1", "OrderConfirmation (v1: no buyerAccessUrl)"),
             "const o = pm.response.json().order;",
             'pm.test("Order is paid at 1,497.00 (3 x 499.00)", () => {',
             '  pm.expect(o.status).to.eql("paid");',
             '  pm.expect(o.total).to.eql({ amount: 149700, currency: "USD" });',
             '});',
             'pm.test("3 tickets with distinct confirmation numbers", () => {',
             '  pm.expect(o.attendees).to.have.lengthOf(3);',
             '  const nums = o.attendees.map(a => a.confirmationNumber);',
             '  pm.expect(new Set(nums).size).to.eql(3);',
             '  nums.forEach(n => pm.expect(n).to.match(/^[2-9A-HJ-NP-Z]{8}$/));',
             '});',
             'pm.test("Confirmation numbers differ from AC-01\'s", () =>',
             "  o.attendees.forEach(a => pm.expect(a.confirmationNumber).to.not.eql(",
             "    pm.collectionVariables.get('ac01Confirmation'))));",
             'pm.test("The buyer is not listed as an attendee", () =>',
             "  o.attendees.forEach(a => pm.expect(a.email).to.not.eql(o.buyer.email)));",
             'pm.test("Attendee names are kept per ticket", () => {',
             '  pm.expect(o.attendees.map(a => a.firstName).sort()).to.eql(["Ann", "Bob", "Cy"]);',
             '});'],
            gwt("General is on sale",
                "a buyer who is not attending buys 3 General tickets for 3 different attendees",
                "3 tickets with distinct confirmation numbers exist and the buyer is not an attendee. "
                "(Order and ticket emails are v3.)"),
            order([attendee("general", "Ann", "Lee", "ann.lee@example.com"),
                   attendee("general", "Bob", "Ray", "bob.ray@example.com"),
                   attendee("general", "Cy", "Moss", "cy.moss@example.com")],
                  buyer={"name": "Dana Organizer", "email": "dana.organizer@example.com"}))])

    ac03 = folder("AC-03 / FR-2.4: Attendee emails must be unique within an order", [
        request(
            "AC-03: two tickets with the same attendee email are rejected", "POST", "/orders",
            [status(422, "Unprocessable Entity"),
             *is_problem("duplicate_attendee_email")],
            gwt("a cart with 2 tickets", "both attendees are given the same email",
                "the order is rejected with a duplicate-email error"),
            order([attendee("early", "Eve", "One", "same@example.com"),
                   attendee("early", "Eve", "Two", "same@example.com")])),
        request(
            "FR-2.4: the same email may hold a ticket in a different order", "POST", "/orders",
            [status(201, "Created"),
             'pm.test("Ticket issued to an email already used in AC-01", () =>',
             '  pm.expect(pm.response.json().order.attendees[0].email).to.eql("pat.buyer@example.com"));'],
            gwt("pat.buyer@example.com already holds a General ticket from AC-01",
                "another order buys an Early Bird ticket for the same email",
                "the order succeeds, because uniqueness is per order only"),
            order([attendee("early", "Pat", "Buyer", "pat.buyer@example.com")]))])

    ac04 = folder("AC-04: Declined card places no order", [
        request(
            "AC-04: card ending 0002 is declined", "POST", "/orders",
            [status(402, "Payment Required"),
             *is_problem("payment_declined")],
            gwt("a valid cart of 1 Student ticket", "the buyer pays with card 4000 0000 0000 0002",
                "no order or tickets are created. The Student count is verified later in AC-05, "
                "which only works out if this order left no ticket behind."),
            order([attendee("student", "Sam", "Student", "sam.student@example.com")], card=DECLINED_CARD)),
        request(
            "AC-04: the buyer retries the same cart with another card", "POST", "/orders",
            [status(201, "Created"),
             "const o = pm.response.json().order;",
             'pm.test("Order is paid at 99.00 with the second card", () => {',
             '  pm.expect(o.status).to.eql("paid");',
             '  pm.expect(o.total.amount).to.eql(9900);',
             '  pm.expect(o.payment.cardLast4).to.eql("4444");',
             '});'],
            gwt("the previous order was declined", "the buyer retries with card 5555 5555 5555 4444",
                "the order succeeds. This is the first Student ticket sold (1 of 55)."),
            order([attendee("student", "Sam", "Student", "sam.student@example.com")], card=SECOND_CARD))])

    validation = folder("Request validation (FR-2.1, FR-4.1)", [
        request(
            "FR-2.1: 11 tickets exceeds the order maximum of 10", "POST", "/orders",
            [status(422, "Unprocessable Entity"),
             *is_problem("order_too_large")],
            gwt("the order maximum is 10 tickets", "a buyer submits 11 Student tickets",
                "the order is rejected with order_too_large and nothing is sold"),
            order([attendee("student", "Over", f"Max{i}", f"overmax{i}@example.com") for i in range(1, 12)])),
        request(
            "FR-4.1: a card number that fails the Luhn check is rejected", "POST", "/orders",
            [status(422, "Unprocessable Entity"),
             *is_problem("validation_failed"),
             'pm.test("The error points at /payment/number", () =>',
             '  pm.expect(pm.response.json().errors.map(e => e.field)).to.include("/payment/number"));'],
            gwt("a valid cart of 1 Student ticket", "the card number 4242 4242 4242 4241 fails Luhn",
                "the order is rejected with validation_failed on /payment/number and nothing is sold"),
            order([attendee("student", "Lu", "Hn", "luhn@example.com")], card=BAD_LUHN_CARD))])

    capacity = folder("AC-05 / AC-07: Capacity and overbooking (Student: baseline 50, cap 55)", [
        sell_students(10, "Setup: sell Student tickets 2-11 (10 tickets)",
                      "Setup. The retry in AC-04 sold Student ticket 1."),
        sell_students(10, "Setup: sell Student tickets 12-21 (10 tickets)", "Setup."),
        sell_students(10, "Setup: sell Student tickets 22-31 (10 tickets)", "Setup."),
        sell_students(10, "Setup: sell Student tickets 32-41 (10 tickets)", "Setup."),
        sell_students(9, "Setup: sell Student tickets 42-50 (9 tickets) - baseline reached", "Setup. 50 sold."),
        request(
            "AC-07: Student is still Available at baseline (50 sold)", "GET", "/ticket-types",
            student_ticket_types_test("available"),
            gwt("50 Student tickets are sold (the baseline capacity)", "the public page is loaded",
                "Student shows Available and can be bought, because the cap is 55 (10% overbooking)")),
        sell_students(4, "Setup: sell Student tickets 51-54 (4 tickets)", "Setup. 54 sold, 1 left under the cap."),
        request(
            "AC-05: ordering 2 Student tickets with 1 left is rejected", "POST", "/orders",
            [status(409, "Conflict"),
             *is_problem("sold_out"),
             'pm.test("Problem names the ticket type and 1 remaining", () => {',
             "  const p = pm.response.json();",
             '  pm.expect(p.ticketTypeId).to.eql("student");',
             '  pm.expect(p.remaining).to.eql(1);',
             '});'],
            gwt("54 Student tickets are sold (cap 55)", "a buyer orders 2 Student tickets",
                "the order is rejected with sold_out and `remaining: 1` (FR-2.7). Nothing is partly sold."),
            order([attendee("student", "Two", "A", "two.a@example.com"),
                   attendee("student", "Two", "B", "two.b@example.com")])),
        request(
            "AC-05: ordering 1 Student ticket succeeds", "POST", "/orders",
            [status(201, "Created"),
             'pm.test("Order is paid for 1 Student ticket", () => {',
             "  const o = pm.response.json().order;",
             '  pm.expect(o.status).to.eql("paid");',
             '  pm.expect(o.attendees).to.have.lengthOf(1);',
             '});'],
            gwt("the 2-ticket order was rejected", "the buyer orders 1 Student ticket",
                "the order succeeds. This is Student ticket 55, the last one under the cap."),
            order([attendee("student", "Last", "One", "last.one@example.com")])),
        request(
            "AC-05: Student now shows Sold out, the others stay Available", "GET", "/ticket-types",
            [status(200, "OK"),
             'const byId = Object.fromEntries(pm.response.json().map(t => [t.id, t]));',
             'pm.test("Student is sold_out", () => pm.expect(byId.student.availability).to.eql("sold_out"));',
             'pm.test("Early Bird and General are still available", () => {',
             '  pm.expect(byId.early.availability).to.eql("available");',
             '  pm.expect(byId.general.availability).to.eql("available");',
             '});'],
            gwt("Student ticket 55 was just sold", "the public page is loaded", "Student shows Sold out")),
        request(
            "AC-05: any further Student order is rejected with 0 remaining", "POST", "/orders",
            [status(409, "Conflict"),
             *is_problem("sold_out"),
             'pm.test("Problem names student with 0 remaining", () => {',
             '  pm.expect(pm.response.json().ticketTypeId).to.eql("student");',
             '  pm.expect(pm.response.json().remaining).to.eql(0);',
             '});'],
            gwt("Student is sold out", "a buyer orders 1 more Student ticket",
                "the order is rejected with sold_out and `remaining: 0`"),
            order([attendee("student", "Too", "Late", "too.late@example.com")]))])

    reset_check = folder("NFR-8: Reset returns to the sample state", [
        request(
            "NFR-8: reset after a sold-out run", "POST", "/test/reset",
            [status(204, "No Content")],
            "One command returns the app to an empty database."),
        request(
            "NFR-8: Student is Available again after reset", "GET", "/ticket-types",
            student_ticket_types_test("available"),
            gwt("Student was sold out", "the test reset runs", "Student is Available again"))])

    return folder("v1 - Buy a ticket", [reset, public, ac01, ac02, ac03, ac04, validation, capacity, reset_check],
                  "Spec section 11, version v1: GET /event, GET /ticket-types, POST /orders, POST /test/reset. "
                  "Covers AC-01 and AC-02 (without email checks), AC-03 to AC-05, AC-07 and the API part of "
                  "AC-22. AC-06 (concurrent orders) is not included yet. "
                  "Requests depend on the ones before them, so run the folder in order.")


# ----------------------------------------------------------------------------- main

def main():
    collection = {
        "info": {
            "name": "Conference Registration API - Conformance Suite",
            "description": "Black-box tests for any implementation of the Conference Registration spec. "
                           "One top-level folder per version (v1-v4). Run a single version with "
                           "`newman run ... --folder \"v1 - Buy a ticket\"`. Generated by "
                           "postman/build_collection.py from openapi.yaml.",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [{"key": "baseUrl", "value": "http://localhost:8080/api"},
                     {"key": "cocVersion", "value": "1"},
                     {"key": "privacyVersion", "value": "1"},
                     {"key": "ac01Confirmation", "value": ""}]
                    + [{"key": k, "value": json.dumps(v)} for k, v in schema_vars().items()],
        "item": [build_v1()],
    }
    OUT.write_text(json.dumps(collection, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
