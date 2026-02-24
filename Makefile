.PHONY: backend-seed backend-run backend-test

backend-seed:
	cd backend && python -m app.db.seed

backend-run:
	cd backend && uvicorn app.main:app --reload --port 8000

backend-test:
	cd backend && pytest
