## MODIFIED Requirements

### Requirement: Client selection
The app SHALL use the `HttpClient` against `/api/v1` when it is built or served with `VITE_HORIZON_CLIENT=http`, and the MockClient otherwise. A build without that variable (the Vercel build) SHALL make no backend requests. Mock-only dev controls SHALL be absent under the `HttpClient`.

The repository's one-command dev (`npm run dev` at the root) SHALL serve the app on the `HttpClient`. A separate root command (`npm run dev:mock`) SHALL serve it on the MockClient with no backend.

Any value of `VITE_HORIZON_CLIENT` other than unset, `mock` or `http` SHALL fail the build or dev server with an error naming the variable. A production build SHALL resolve to the `HttpClient` only when it is explicitly built in the `http` mode (the local `npm run demo`). A build on Vercel SHALL never resolve to the `HttpClient`.

#### Scenario: Default stays mock
- **WHEN** the frontend is built with no `VITE_HORIZON_CLIENT`
- **THEN** `client.kind` is `"mock"`, and no request to `/api/` is made while the seed worlds are browsed

#### Scenario: HTTP selected
- **WHEN** the dev server runs with `VITE_HORIZON_CLIENT=http`
- **THEN** `client.kind` is `"http"`, and the world list comes from `GET /api/v1/worlds`

#### Scenario: Root dev commands
- **WHEN** `npm run dev` is run at the repository root, and separately `npm run dev:mock`
- **THEN** the first serves the app on the `HttpClient` next to the backend, and the second serves it on the MockClient without starting a backend

#### Scenario: Misspelt client value
- **WHEN** the frontend is built with `VITE_HORIZON_CLIENT=HTTP`
- **THEN** the build fails with an error naming `VITE_HORIZON_CLIENT` and its allowed values, and produces no bundle

#### Scenario: HTTP leaked into a production build
- **WHEN** a production build runs with `VITE_HORIZON_CLIENT=http` set in the environment but without the `http` mode
- **THEN** the build fails, and produces no bundle

#### Scenario: Vercel never ships the HttpClient
- **WHEN** a build runs with `VERCEL=1` and resolves `VITE_HORIZON_CLIENT` to `http`, in any mode
- **THEN** the build fails

#### Scenario: Local demo build
- **WHEN** `npm run demo` builds the frontend in the `http` mode, without `VERCEL`
- **THEN** the build succeeds, and the served app uses the `HttpClient`
