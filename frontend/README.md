# Horizon frontend

The React 19 + TypeScript + Vite app for Horizon. For the project overview, the guided tour and the keyboard shortcuts, see the [root README](../README.md).

```bash
npm install
npm run dev        # http://localhost:5173
```

You need Node.js 20.19+ or 22.12+. There is no backend yet: `src/client/index.ts` exports the in-browser `MockClient`, which serves the demo data in `../seed/`. Press <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>D</kbd> in the app to switch mock scenarios.

Before you commit, run:

```bash
npm run typecheck && npm run lint && npm test && npm run seed:check && npm run build && npm run budget
```
