.PHONY: setup ingest ask eval test verify-env serve

VENV := .venv
PY := $(VENV)/bin/python

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt
	@test -f .env || cp .env.example .env
	@echo "setup tamam — .env dosyasını doldurun (DEEPSEEK_API_KEY), sonra 'make verify-env' çalıştırın"

verify-env:
	$(PY) scripts/verify_env.py

ingest:
	$(PY) -m mevzuat_rag.ingest_pipeline

# make serve QUERY="Dilekçede hangi bilgiler zorunludur?"
serve:
ifdef QUERY
	$(PY) -m mevzuat_rag.ask "$(QUERY)"
else
	$(PY) -m mevzuat_rag.repl
endif

ask:
	$(PY) -m mevzuat_rag.ask "$(QUERY)"

eval:
	$(PY) -m mevzuat_rag.eval.run_retrieval_eval

test:
	$(PY) -m pytest tests/ -v
