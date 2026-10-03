// `npm run test:http`: the portable HorizonClient contract over HTTP against a test-mode backend that the global setup
// starts (uv run horizon serve, HORIZON_TEST=1, temporary data dir). One file, run serially. Owner: SWE.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/client/clientContract.http.test.ts"],
    globalSetup: ["scripts/http-contract/globalSetup.ts"],
    fileParallelism: false,
    testTimeout: 30_000,
    hookTimeout: 180_000,
  },
});
