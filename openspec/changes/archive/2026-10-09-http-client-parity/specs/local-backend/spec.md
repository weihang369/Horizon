## MODIFIED Requirements

### Requirement: One-command local development
At the repository root:
- `npm run setup` SHALL install the backend core and the frontend in one step. Document conversion is a separate, optional second step.
- `npm run dev` SHALL start the backend and the frontend together, with the frontend using the backend.
- `npm run dev:mock` SHALL start the frontend alone, on the MockClient.
- Stopping `npm run dev` SHALL stop both processes.
- `npm run demo` SHALL serve the built frontend and the API from one port.

On a fresh clone, with Node and uv installed and no package cache, `npm run setup` followed by `npm run dev` SHALL reach demo mode within 5 minutes (NFR-10). Demo mode means the app loads the two seed worlds through the backend. Document conversion is not part of that budget. The README SHALL give these steps for Windows first, then Unix, and SHALL report the document-conversion step separately.

#### Scenario: Dev session
- **WHEN** `npm run setup` (step 1) and then `npm run dev` are run on a fresh clone
- **THEN** the app on `http://localhost:5173` loads the seed worlds through `/api/v1`, served by the backend on port 8000

#### Scenario: Ctrl-C stops everything
- **WHEN** `npm run dev` is interrupted
- **THEN** neither the backend nor Vite keeps running

#### Scenario: Mock-only loop
- **WHEN** `npm run dev:mock` is run with no backend running
- **THEN** the app loads the seed worlds from the MockClient, and no request to `/api/` is made

#### Scenario: Fresh clone within five minutes
- **WHEN** the repository is cloned into an empty directory with empty npm and uv caches, `npm run setup` is run, and `npm run dev` is started
- **THEN** `GET /api/v1/worlds` through the app's dev server returns the two seed worlds within 300 seconds of the start of setup, on Windows and on Linux

#### Scenario: README matches the steps
- **WHEN** the README's run section is followed on Windows, as written
- **THEN** it names the prerequisites (Node and uv), the setup and dev commands, the optional `.env` copy, and the optional document-conversion step as a separate step, and it contains no statement about features the backend lacks

### Requirement: Committed environment template
The repository SHALL include `.env.example` at the root. It SHALL list `OPENROUTER_API_KEY` and every other variable the backend configuration reads, including each AI port override, with blank or default values; advanced variables MAY appear as commented-out lines. It SHALL never contain a real key. `.env` SHALL stay git-ignored. A test SHALL fail when the configuration reads a variable that the template does not list.

#### Scenario: Template has no key
- **WHEN** `.env.example` is read
- **THEN** `OPENROUTER_API_KEY=` has an empty value, and `.env` is matched by `.gitignore`

#### Scenario: Every variable is documented
- **WHEN** a new variable is added to the backend configuration without a line in `.env.example`
- **THEN** the backend test suite fails and names the missing variable

#### Scenario: No key-shaped text
- **WHEN** `.env.example` contains a token starting with `sk-or-` followed by key characters, on any line
- **THEN** the backend test suite fails

## ADDED Requirements

### Requirement: Secret hygiene guidance
The README SHALL include a secret-hygiene section. It SHALL recommend a pre-commit secret scan (gitleaks) as optional, with install and hook instructions for Windows and Unix. The repository SHALL NOT install a hook or add a dependency for it, so setup stays Node and uv only.

#### Scenario: Recommendation without a hook
- **WHEN** the repository is freshly cloned and set up
- **THEN** the README describes the optional gitleaks pre-commit hook, and no hook is installed in `.git/hooks` and no package for it is added
