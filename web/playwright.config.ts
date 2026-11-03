import { defineConfig } from "@playwright/test";

const env = {
  DATABASE_URL: "postgresql+psycopg://postgres:postgres@localhost:5433/shop_test",
  CHECKPOINT_URL: "postgresql://postgres:postgres@localhost:5433/shop_test",
  FAKE_LLM: "1",
  AUTO_SYNC: "0",
  EMBED_MODE: "hash",
  SYNC_MODE: "inprocess",
  REDIS_URL: "",
  SPA_DIST: "web/dist",
};

export default defineConfig({
  testDir: "../e2e",
  timeout: 30000,
  use: { baseURL: "http://127.0.0.1:8765" },
  webServer: {
    command: ".venv/bin/uvicorn api.main:app --port 8765",
    cwd: "..",
    url: "http://127.0.0.1:8765/api/health",
    reuseExistingServer: false,
    env,
  },
});
