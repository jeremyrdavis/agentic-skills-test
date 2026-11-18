# Conformance suite (Postman / Newman)

Black-box tests for any implementation of `conference-registration-spec.md` and `openapi.yaml`. The collection has one top-level folder per version. Only **v1** exists so far.

## Run

```bash
npm install                                   # installs newman
npm run test:v1                               # against http://localhost:8080/api

# another implementation, or another port
npx newman run postman/conference-registration.postman_collection.json \
  -e postman/local.postman_environment.json \
  --env-var baseUrl=http://localhost:9090/api \
  --folder "v1 - Buy a ticket"
```

For a demo, import `conference-registration.postman_collection.json` and `local.postman_environment.json` into Postman and run the **v1** folder with the Collection Runner. Each request's description gives the Given / When / Then from the spec.

The implementation under test must have **test support switched on** (`POST /test/reset` must return 204, not 404).

## Things to know

- **Run a folder in order, against a fresh server.** Requests depend on earlier ones (for example, AC-05 relies on exactly 54 Student tickets having been sold). The first request resets the app, so you don't need to restart it between runs.
- **Responses are validated against `openapi.yaml`.** The schemas are copied into collection variables (`schema_*`) when the collection is built. v1 deliberately drops `buyerAccessUrl` from the required fields, because magic links arrive in v2.
- **AC-22 is only half-covered.** The suite checks that responses never echo the full card number or CVC. Searching the database and logs for the test card numbers has to be done by hand.
- **Not in v1 yet:** AC-06 (concurrent orders) and the email checks of AC-01 and AC-02 (v3).

## The collection is generated

`conference-registration.postman_collection.json` is built by `build_collection.py`. Edit the script, not the JSON, then regenerate:

```bash
uv run --with pyyaml postman/build_collection.py
```

Regenerate after any change to `openapi.yaml` so the embedded schemas stay current. To add v2, write a `build_v2()` folder in the script and add it to `collection["item"]` in `main()`.
