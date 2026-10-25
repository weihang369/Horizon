// Ports and URLs of the E2E servers, shared by playwright.config.ts and the fixtures (http-client-parity D7, D13).
// None of them is a dev port (8000 / 5173), so a running `npm run dev` never collides with an E2E run.
export const MOCK_WEB_PORT = 5186;
export const HTTP_WEB_PORT = 5187;
export const BACKEND_PORT = 8786;
/** The test backend's API, reached directly (fixtures) or through the HTTP project's Vite proxy (the app). */
export const BACKEND_API = `http://127.0.0.1:${BACKEND_PORT}/api/v1`;

export type ClientKind = "mock" | "http";
