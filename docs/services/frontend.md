# frontend

Read this when you touch the browser UI, the API client, or the reverse proxy.
For what each screen is allowed to show see `docs/ui-feature-matrix.md`; for
endpoint-by-endpoint call rules see `docs/ui-api-guide.md` — this file does not
repeat either.

## Responsibility

A single React + Vite single-page app serving three surfaces, plus the nginx
container that fronts it and reaches the services.

| Surface | Path | Entry component |
| --- | --- | --- |
| Public landing | `/` | `frontend/src/Landing.tsx` |
| Dilekçe analiz ekranı | `/dilekce`, `/dilekce/tesekkurler/:ref` | `PetitionForm.tsx`, `PetitionThanks.tsx` |
| Operator panel | `/panel`, `/panel/yeni`, `/panel/dosya/:caseId` | `App.tsx` |

Routes are derived from the URL in `frontend/src/router.ts`; there is no second
view state in React, so back/refresh/shared links behave normally.

## Does not own

- Any business decision: classification, validation eligibility, drafting and
  routing are all server-side. The UI renders stored results.
- Authentication. See the token note below.
- Contract shapes: `frontend/src/types.ts` mirrors the schemas; the schemas win.

## Location

| What | Path |
| --- | --- |
| App root / bootstrap | `frontend/src/main.tsx`, `frontend/src/Root.tsx` |
| Single API client | `frontend/src/api.ts` |
| Routing | `frontend/src/router.ts` |
| Types | `frontend/src/types.ts` |
| Petition logic | `frontend/src/petition.ts`, `petition-receipt.ts`, `petition-content.json` |
| Local queue / storage | `frontend/src/queue.ts`, `frontend/src/storage.ts` |
| Demo samples | `frontend/src/samples.ts` |
| Styles | `frontend/src/styles.css` |
| Build config | `frontend/vite.config.ts`, `frontend/package.json` |
| Proxy | `frontend/nginx.conf` |
| Container | `frontend/Dockerfile` |

## Proxy and token model

Every request goes through nginx, never straight to a service. `BASES` in
`frontend/src/api.ts` maps to the `location` blocks in `frontend/nginx.conf`:
`/api/real`, `/api/ocr`, `/api/classification`, `/api/validation`,
`/api/validation-user`, `/api/workflow-user`, `/api/workflow-admin`.

Two points that matter when changing anything here:

- Upstreams are resolved **per request** (`resolver 127.0.0.11`, hostname in a
  variable). A literal hostname in `proxy_pass` would be resolved once at
  startup and would pin the container to whichever lane was up first.
- nginx injects the demo `Authorization: Bearer ...` headers for the
  user and admin lanes. The credentials therefore never reach the browser
  bundle. They are fixed demo tokens, **not** production authentication —
  anyone who can reach the proxy has the corresponding role.

## Mock vs real labelling

`api.ts` reads the `X-CoreAIgent-Implementation` response header
(`implementationOf`, line 100) and carries an `ImplementationMode`
(`mock` | `real` | `unknown`) through results and errors, so the UI can state
which implementation answered. Keep that plumbing intact: presenting a mock
answer as a real one is the one thing the project rules forbid outright.

## Processing flow (citizen path)

1. The portal collects the petition text and posts it into the intake chain.
2. The reference shown on the thanks page comes from
   `frontend/src/petition-receipt.ts`.
3. The panel polls case reads (`/cases`, `/cases/{id}` and the sub-resources)
   and renders derived state, missing-information prompts, the draft and the
   routing result.
4. Write actions (supplemental information, correspondence start, review
   completion) send `Idempotency-Key` and `If-Match`; the client surfaces
   `412`/`428`/`409` rather than retrying blindly.

## Product language and visual boundary

The public entry point is **CoreAIgent Dilekçe Analiz Sistemi**, not an
e-Devlet or municipal-login imitation. Its primary action is writing a
petition as free text; it does not promise binary upload, an OCR scan, account
login, e-mail delivery, or a final administrative decision. The operator panel
uses the same CoreAIgent visual system and shows F2's ADMIN-only local first
assignment when a routed case has an active unit staff member. Ordinary cases
are load-balanced; repeated or bounded behavior-signal cases also show the
topic-resolution policy and its counters. This is a demo workload registry,
not production identity/authentication.

## Failure behaviour

Errors are normalized into `ApiError` with status, body and implementation mode,
so a `503` from a service and a proxy failure are distinguishable in the UI.

## Configuration

Names only: the `upstream_*` variables and demo token names in
`frontend/nginx.conf`, and the compose environment that sets them
(`compose.integration.yaml`). No secret values belong in `frontend/src/`.

## Tests

`npm test` (Vitest) in `frontend/`: `frontend/src/api.test.ts`,
`frontend/src/petition.test.ts`, `frontend/src/queue.test.ts`. Server-side
counterparts: `tests/test_citizen_portal_samples.py`, `tests/test_mock_case_ui.py`.

## Related docs

- `docs/ui-api-guide.md` — endpoint call rules
- `docs/ui-feature-matrix.md` — surface-by-surface scope
- [`../development.md`](../development.md) — which lane the UI is pointed at
