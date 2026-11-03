.PHONY: test

test:
	.venv/bin/pytest -q
	cd web && npm test
	cd web && npm run build
	ln -sfn ../web/node_modules e2e/node_modules
	DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/shop_test CHECKPOINT_URL=postgresql://postgres:postgres@localhost:5433/shop_test FAKE_LLM=1 EMBED_MODE=hash SYNC_MODE=inprocess REDIS_URL= .venv/bin/python scripts/seed_fixture.py
	cd web && npx playwright test
