"""Explicit online preparation step for the two pinned offline MT artifacts."""

from huggingface_hub import snapshot_download

from translation import MODEL_SPECS

for model_id, revision in MODEL_SPECS.values():
    snapshot_download(repo_id=model_id, revision=revision, cache_dir="/var/cache/huggingface")
