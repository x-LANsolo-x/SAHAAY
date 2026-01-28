Local dev (Docker-free)

1) Create and activate a venv
   python3 -m venv .venv
   source .venv/bin/activate

2) Install deps
   pip install -r services/api/requirements.txt

3) Run API
   uvicorn services.api.main:app --reload --port 8000

4) Smoke test
   curl http://127.0.0.1:8000/health
   curl http://127.0.0.1:8000/version

5) Run tests
   pytest -q
