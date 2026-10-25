# Horizon frontend

The React 19 + TypeScript + Vite app for Horizon. For the project overview see the [root README](../README.md); for
the commands, tests and the repository layout see [CONTRIBUTING.md](../CONTRIBUTING.md).

```bash
npm install
npm run dev        # http://localhost:5173, on the in-browser mock client
```

On its own the app needs only Node.js 20.19+ or 22.12+ (the repository pins 24 in `.nvmrc`). `src/client/index.ts`
picks the `MockClient` by default, which serves the demo data in `../seed/` with no backend; the live demo on Vercel
runs the same way. Built with `VITE_HORIZON_CLIENT=http`, it uses the `HttpClient` against the local backend instead:
`npm run dev` at the repository root starts both. Press <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>D</kbd> in the app to
switch mock scenarios.

Before a pull request, run the frontend part of
[Before you open a pull request](../CONTRIBUTING.md#before-you-open-a-pull-request).
