import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

RAG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "mevzuat-rag"))
PYTHON_BIN = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".venv", "bin", "python3"))


def _rag_subprocess_env() -> dict:
    env = dict(os.environ)
    env_path = os.path.join(RAG_DIR, ".env")
    if os.path.isfile(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key:
                    env[key] = value
    return env

_RETRIEVE_SCRIPT = """
import json, sys
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine

query = sys.argv[1]
top_k = int(sys.argv[2])
actor = sys.argv[3] if len(sys.argv) > 3 else None

engine = RAGEngine(RAGConfig.from_env())
results = engine.retrieve(query, top_k=top_k, actor=actor)

out = []
for r in results:
    out.append({
        "id": r.chunk.id,
        "title": r.chunk.citation,
        "excerpt": r.chunk.text,
        "score": float(r.score),
    })
print(json.dumps({"results": out}))
"""


def get_rag_context(query: str, top_k: int = 5, actor: str = "anonymous") -> dict:
    if not query or not query.strip():
        return {"results": [], "context_snippets": []}

    try:
        proc = subprocess.run(
            [PYTHON_BIN, "-c", _RETRIEVE_SCRIPT, query, str(top_k), actor],
            cwd=RAG_DIR,
            capture_output=True,
            text=True,
            timeout=90,
            env=_rag_subprocess_env(),
        )
    except Exception as exc:
        logger.error("RAG subprocess başlatılamadı: %s", exc)
        return {"results": [], "context_snippets": []}

    if proc.returncode != 0:
        logger.error("RAG subprocess hata verdi (rc=%s): %s", proc.returncode, proc.stderr[-2000:])
        return {"results": [], "context_snippets": []}

    try:
        last_line = proc.stdout.strip().splitlines()[-1]
        payload = json.loads(last_line)
        results = payload.get("results", [])
    except Exception as exc:
        logger.error("RAG subprocess çıktısı parse edilemedi: %s | stdout=%s", exc, proc.stdout[-500:])
        return {"results": [], "context_snippets": []}

    context_snippets = [r["excerpt"] for r in results if r.get("excerpt")]
    return {"results": results, "context_snippets": context_snippets}
