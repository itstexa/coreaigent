"""Jamba2-3B inference API for the CoreAIgent ``llm`` service.

The model loader is deliberately an injected boundary. Two real loaders exist
behind one HTTP contract:

* ``RealJambaLoader`` runs the pinned Hugging Face checkpoint in-process on
  CUDA. It stays the reference runtime.
* ``LlamaCppLoader`` forwards to a llama.cpp server that serves the pinned
  GGUF build of the same model. Docker Desktop cannot pass a Radeon GPU into a
  Linux container, so that server runs on the host with the Vulkan backend
  while this service keeps owning validation, readiness, and the deadline.

CPU tests inject a tiny/fake loader, so they never download or initialize a
real model.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

MODEL_ID = "ai21labs/AI21-Jamba2-3B"
MODEL_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MAX_PROMPT_TOKENS = 8192
BACKENDS = ("transformers", "llama_cpp")
DEADLINE_LIMIT = 120.0
# Readiness/identity probes against the llama.cpp server must never block a
# health check for long; generation gets the configured deadline plus enough
# slack for the upstream socket to return the deadline error itself.
UPSTREAM_PROBE_TIMEOUT = 5.0
UPSTREAM_DEADLINE_SLACK = 15.0
# The GGUF lane is a cheap HTTP hop, so an unreachable or restarted host
# server can be re-probed instead of pinning the container to a dead state.
UPSTREAM_RETRY_INTERVAL = 5.0
JAMBA_FALLBACK_CHAT_TEMPLATE = """{% if bos_token is defined and bos_token is not none %}{{ bos_token }}{% endif %}{% for message in messages %}{% if message.role in ['system', 'user', 'assistant'] %}{{ '<|im_start|>' + message.role + '\\n' + message.content + '<|im_end|>\\n' }}{% endif %}{% endfor %}{% if add_generation_prompt %}{{ '<|im_start|>assistant\\n' }}{% endif %}"""
JAMBA_SYSTEM_PROMPT = "Sen verilen talimata doğrudan ve güvenilir biçimde yanıt veren yardımcı bir Türkçe asistansın."
LOGGER = logging.getLogger("coreaigent.llm")


class ModelNotReadyError(RuntimeError):
    """The service cannot perform inference yet."""


class EmptyGenerationError(RuntimeError):
    """The model returned no usable completion."""


class GenerationDeadlineError(RuntimeError):
    """The configured server-side generation deadline elapsed."""


@dataclass(frozen=True)
class RuntimeConfig:
    model_id: str = MODEL_ID
    model_revision: str = ""
    hf_home: str = "/var/cache/huggingface"
    max_new_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 0.9
    deadline_seconds: float = 60.0
    backend: str = "transformers"
    llama_server_url: str = ""
    llama_api_key: str = ""
    gguf_file: str = ""

    @property
    def gguf_mode(self) -> bool:
        """Return True when the pinned GGUF build serves inference."""

        return self.backend == "llama_cpp"

    @property
    def upstream_url(self) -> str:
        """Return the llama.cpp base URL without a trailing slash."""

        return self.llama_server_url.rstrip("/")

    @property
    def hf_cache_dir(self) -> str:
        """Return the explicit Hub cache path used by the model artifact."""

        return os.environ.get("HUGGINGFACE_HUB_CACHE", os.path.join(self.hf_home, "hub"))

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        """Read deployment configuration without loading model weights."""

        def number(name: str, default: str, cast):
            value = os.environ.get(name, default)
            try:
                return cast(value)
            except (TypeError, ValueError):
                return cast(default)

        return cls(
            model_id=os.environ.get("MODEL_ID", MODEL_ID),
            model_revision=os.environ.get("MODEL_REVISION", ""),
            hf_home=os.environ.get("HF_HOME", "/var/cache/huggingface"),
            max_new_tokens=number("MAX_NEW_TOKENS", "256", int),
            temperature=number("TEMPERATURE", "0.7", float),
            top_p=number("TOP_P", "0.9", float),
            deadline_seconds=number("GENERATION_DEADLINE_SECONDS", "60", float),
            backend=os.environ.get("BACKEND", "transformers").strip().lower() or "transformers",
            llama_server_url=os.environ.get("LLAMA_SERVER_URL", "").strip(),
            llama_api_key=os.environ.get("LLAMA_API_KEY", "").strip(),
            gguf_file=os.environ.get("GGUF_FILE", "").strip(),
        )

    def validation_error(self) -> Optional[str]:
        if self.model_id != MODEL_ID:
            return "MODEL_ID must be " + MODEL_ID
        if not MODEL_REVISION_PATTERN.fullmatch(self.model_revision):
            return "MODEL_REVISION must be a 40-character lowercase commit SHA"
        if not self.hf_home or not self.hf_home.startswith("/"):
            return "HF_HOME must be an absolute path"
        if not 1 <= self.max_new_tokens <= 1800:
            return "MAX_NEW_TOKENS must be between 1 and 1800"
        if not 0.0 <= self.temperature <= 2.0:
            return "TEMPERATURE must be between 0.0 and 2.0"
        if not 0.0 < self.top_p <= 1.0:
            return "TOP_P must be greater than 0.0 and at most 1.0"
        if self.backend not in BACKENDS:
            return "BACKEND must be transformers or llama_cpp"
        if self.gguf_mode:
            if not self.upstream_url.startswith(("http://", "https://")):
                return "LLAMA_SERVER_URL must be an http(s) URL for the llama_cpp backend"
            if not self.gguf_file.endswith(".gguf"):
                return "GGUF_FILE must name the pinned .gguf artifact"
        if not 5.0 <= self.deadline_seconds <= DEADLINE_LIMIT:
            return (
                "GENERATION_DEADLINE_SECONDS must be between 5 and "
                + str(int(DEADLINE_LIMIT))
            )
        return None


class ModelLoader(Protocol):
    load_call_count: int

    def load(self, config: RuntimeConfig) -> Any:
        ...

    def token_count(self, prompt: str) -> int:
        ...

    def generate(self, prompt: str, config: RuntimeConfig) -> str:
        ...


class RealJambaLoader:
    """Loads and serves the pinned Hugging Face Jamba checkpoint once."""

    def __init__(self) -> None:
        self.load_call_count = 0
        self._model: Any = None
        self._tokenizer: Any = None
        self._torch: Any = None
        self._device: Any = None

    def load(self, config: RuntimeConfig) -> "RealJambaLoader":
        self.load_call_count += 1
        import torch
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable")
        device_map = {"": "cuda:0"}

        model_config = AutoConfig.from_pretrained(
            config.model_id,
            revision=config.model_revision,
            cache_dir=config.hf_cache_dir,
            trust_remote_code=True,
        )
        if hasattr(model_config, "use_mamba_kernels"):
            model_config.use_mamba_kernels = True
        if hasattr(model_config, "use_cache"):
            model_config.use_cache = True

        tokenizer = AutoTokenizer.from_pretrained(
            config.model_id,
            revision=config.model_revision,
            cache_dir=config.hf_cache_dir,
            trust_remote_code=True,
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        # The pinned checkpoint ships a ChatML template.  Derived checkpoints
        # sometimes drop it while keeping the Jamba chat tokens, so fall back to
        # the compatibility template and start generation in an assistant turn
        # instead of continuing/echoing the raw user prompt.
        if not getattr(tokenizer, "chat_template", None):
            vocab = tokenizer.get_vocab()
            if "<|im_start|>" in vocab and "<|im_end|>" in vocab:
                tokenizer.chat_template = JAMBA_FALLBACK_CHAT_TEMPLATE

        model = AutoModelForCausalLM.from_pretrained(
            config.model_id,
            revision=config.model_revision,
            cache_dir=config.hf_cache_dir,
            config=model_config,
            device_map=device_map,
            torch_dtype=torch.bfloat16,
            attn_implementation="sdpa",
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        model.eval()
        self._torch = torch
        self._tokenizer = tokenizer
        self._model = model
        self._device = next(model.parameters()).device
        return self

    def token_count(self, prompt: str) -> int:
        encoded = self._tokenizer(prompt, add_special_tokens=True, truncation=False)
        return len(encoded["input_ids"])

    def generate(self, prompt: str, config: RuntimeConfig) -> str:
        messages = [
            {"role": "system", "content": JAMBA_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        if getattr(self._tokenizer, "chat_template", None):
            inputs = self._tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt",
            )
            inputs = {"input_ids": inputs}
        else:
            inputs = self._tokenizer(prompt, return_tensors="pt")
        inputs = {key: value.to(self._device) for key, value in inputs.items()}
        kwargs = {
            **inputs,
            "max_new_tokens": config.max_new_tokens,
            "use_cache": True,
            "pad_token_id": self._tokenizer.pad_token_id,
            "eos_token_id": self._tokenizer.eos_token_id,
            "do_sample": config.temperature > 0.0,
        }
        if config.temperature > 0.0:
            kwargs.update({"temperature": config.temperature, "top_p": config.top_p})
        with self._torch.no_grad():
            output = self._model.generate(**kwargs)
        prompt_length = inputs["input_ids"].shape[1]
        completion = output[0][prompt_length:]
        return self._tokenizer.decode(completion, skip_special_tokens=True).strip()


class LlamaCppLoader:
    """Serves the pinned GGUF build through an external llama.cpp server.

    Docker Desktop cannot expose a Radeon GPU to a Linux container, so the
    accelerated lane runs ``llama-server`` on the host with the Vulkan backend.
    This loader keeps the weights out of the container while still refusing to
    serve anything other than the pinned GGUF artifact.
    """

    def __init__(self) -> None:
        self.load_call_count = 0
        self._url = ""
        self._api_key = ""
        self._model_path = ""

    def load(self, config: RuntimeConfig) -> "LlamaCppLoader":
        self.load_call_count += 1
        self._url = config.upstream_url
        self._api_key = config.llama_api_key
        health = self._call("GET", "/health", None, UPSTREAM_PROBE_TIMEOUT)
        if health.get("status") != "ok":
            raise RuntimeError("llama.cpp server is not serving a model yet")
        served = self._served_file(self._call("GET", "/props", None, UPSTREAM_PROBE_TIMEOUT))
        if config.gguf_file and served != config.gguf_file:
            raise RuntimeError(
                "llama.cpp server serves " + (served or "an unknown file")
                + " instead of the pinned " + config.gguf_file
            )
        return self

    @property
    def model_path(self) -> str:
        """Return the artifact path reported by the llama.cpp server."""

        return self._model_path

    def healthy(self) -> bool:
        """Report whether the upstream server still serves the model."""

        try:
            return self._call("GET", "/health", None, UPSTREAM_PROBE_TIMEOUT).get("status") == "ok"
        except Exception:
            return False

    def token_count(self, prompt: str) -> int:
        payload = self._call("POST", "/tokenize", {"content": prompt}, UPSTREAM_PROBE_TIMEOUT * 4)
        tokens = payload.get("tokens")
        if not isinstance(tokens, list):
            raise RuntimeError("llama.cpp server returned no tokenization")
        return len(tokens)

    def generate(self, prompt: str, config: RuntimeConfig) -> str:
        body = {
            "messages": [
                {"role": "system", "content": JAMBA_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": config.max_new_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "stream": False,
        }
        payload = self._call(
            "POST",
            "/v1/chat/completions",
            body,
            config.deadline_seconds + UPSTREAM_DEADLINE_SLACK,
        )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        return content.strip() if isinstance(content, str) else ""

    def _served_file(self, props: dict) -> str:
        self._model_path = str(props.get("model_path") or "")
        return self._model_path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]

    def _call(self, method: str, path: str, body: Optional[dict], timeout: float) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        if self._api_key:
            headers["Authorization"] = "Bearer " + self._api_key
        request = urllib.request.Request(self._url + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read() or b"{}")
        return payload if isinstance(payload, dict) else {}


class JambaService:
    """Runtime state, lifecycle, validation, and serialized generation."""

    def __init__(
        self,
        loader: ModelLoader,
        config: RuntimeConfig,
        gpu_available: bool,
        device_probe: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.loader = loader
        self.config = config
        self.gpu_available = gpu_available
        self.model_loaded = False
        self.accepting_inference = False
        self.readiness_code: Optional[str] = None
        self._backend: Any = None
        self._device_probe = device_probe
        self._last_probe = 0.0
        self._generation_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jamba-generation")
        self._initialize()

    @property
    def _reattachable(self) -> bool:
        """Only the cheap HTTP backend may be probed again after a failure.

        Reloading the in-process CUDA checkpoint costs minutes, so a failed
        CUDA start stays failed until the container restarts.
        """

        return self.config.gguf_mode and self._device_probe is not None

    def _device_unavailable_code(self) -> str:
        return "model_not_ready" if self.config.gguf_mode else "gpu_unavailable"

    def _initialize(self) -> None:
        if not self.gpu_available:
            self.readiness_code = self._device_unavailable_code()
            return
        if (error := self.config.validation_error()) is not None:
            self.readiness_code = "model_not_ready"
            return
        try:
            self._backend = self.loader.load(self.config)
            self.model_loaded = True
            self.accepting_inference = True
            self.readiness_code = None
        except Exception:
            LOGGER.exception("Jamba model initialization failed")
            self.readiness_code = "model_not_ready"

    def _refresh_upstream(self) -> None:
        """Re-attach to, or detach from, a restarted llama.cpp server."""

        now = time.monotonic()
        with self._lifecycle_lock:
            if now - self._last_probe < UPSTREAM_RETRY_INTERVAL:
                return
            self._last_probe = now
            if self.model_loaded:
                healthy = getattr(self._backend, "healthy", lambda: True)()
                if healthy:
                    return
                LOGGER.warning("llama.cpp server stopped serving the pinned model")
                self.model_loaded = False
                self.accepting_inference = False
                self._backend = None
            self.gpu_available = bool(self._device_probe and self._device_probe())
            self._initialize()

    @property
    def ready(self) -> bool:
        if self._reattachable:
            self._refresh_upstream()
        return self.gpu_available and self.model_loaded and self.accepting_inference

    def readiness_error(self) -> JSONResponse:
        code = self.readiness_code or "model_not_ready"
        return error_response(503, code, "Jamba model is not ready for inference")

    def token_count(self, prompt: str) -> int:
        return int(self._backend.token_count(prompt))

    def generate(self, prompt: str) -> str:
        if not self.ready:
            raise ModelNotReadyError()
        with self._generation_lock:
            future = self._executor.submit(self._backend.generate, prompt, self.config)
            try:
                result = future.result(timeout=self.config.deadline_seconds)
            except FutureTimeoutError as exc:
                raise GenerationDeadlineError() from exc
        if not isinstance(result, str) or not result:
            raise EmptyGenerationError()
        return result


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def contract_error_response(
    body: Any,
    status: int,
    category: str,
    message: str,
    *,
    retryable: bool = False,
) -> JSONResponse:
    """Return the repository-wide error envelope for the /v1 contract."""

    payload = body if isinstance(body, dict) else {}
    request_id = payload.get("requestId")
    workflow_id = payload.get("workflowId") if isinstance(payload.get("workflowId"), str) else None
    document_id = payload.get("documentId") if isinstance(payload.get("documentId"), str) else None
    return JSONResponse(
        status_code=status,
        content={
            "schemaVersion": "2.0",
            "requestId": request_id if isinstance(request_id, str) and request_id else "unknown-request",
            "workflowId": workflow_id,
            "documentId": document_id,
            "service": "llm",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "category": category,
            "message": message,
            "retryable": retryable,
        },
    )


def valid_contract_request(body: Any) -> bool:
    """Keep the small adapter aligned with contracts/schemas/llm-request."""

    if not isinstance(body, dict):
        return False
    required = {"schemaVersion", "requestId", "documentId", "workflowId", "task", "prompt"}
    allowed = required | {"context"}
    if set(body) - allowed or not required <= set(body):
        return False
    if body["schemaVersion"] != "2.0" or body["task"] not in {"draft_reply", "route_document", "summarize"}:
        return False
    if any(not isinstance(body[key], str) or not body[key] for key in ("requestId", "documentId", "workflowId", "prompt")):
        return False
    return "context" not in body or (
        isinstance(body["context"], list)
        and all(isinstance(item, str) for item in body["context"])
    )


def _gpu_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _llama_server_reachable(config: RuntimeConfig) -> bool:
    try:
        headers = {"Authorization": "Bearer " + config.llama_api_key} if config.llama_api_key else {}
        request = urllib.request.Request(config.upstream_url + "/health", headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=UPSTREAM_PROBE_TIMEOUT) as response:
            payload = json.loads(response.read() or b"{}")
        return isinstance(payload, dict) and payload.get("status") == "ok"
    except Exception:
        return False


def _device_available(config: RuntimeConfig) -> bool:
    """Report whether the configured inference device can be used."""

    return _llama_server_reachable(config) if config.gguf_mode else _gpu_available()


def _default_loader(config: RuntimeConfig) -> ModelLoader:
    return LlamaCppLoader() if config.gguf_mode else RealJambaLoader()


def create_app(
    *,
    loader: Optional[ModelLoader] = None,
    config: Optional[RuntimeConfig] = None,
    gpu_available: Optional[bool] = None,
) -> FastAPI:
    runtime_config = config or RuntimeConfig.from_env()
    service = JambaService(
        loader or _default_loader(runtime_config),
        runtime_config,
        _device_available(runtime_config) if gpu_available is None else gpu_available,
        device_probe=(lambda: _device_available(runtime_config)) if gpu_available is None else None,
    )
    app = FastAPI(title="CoreAIgent LLM", docs_url=None, redoc_url=None)
    app.state.jamba_service = service

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "model": runtime_config.model_id,
            "model_loaded": service.model_loaded,
            "backend": runtime_config.backend,
        }

    @app.get("/ready")
    async def ready() -> JSONResponse:
        if not service.ready:
            return service.readiness_error()
        return JSONResponse(
            status_code=200,
            content={
                "status": "ready",
                "model": runtime_config.model_id,
                "model_loaded": True,
                "backend": runtime_config.backend,
            },
        )

    @app.post("/generate")
    async def generate(request: Request) -> JSONResponse:
        try:
            body = json.loads(await request.body())
        except (UnicodeDecodeError, json.JSONDecodeError):
            return error_response(400, "malformed_json", "Request body must be valid JSON")
        if not isinstance(body, dict):
            return error_response(422, "invalid_prompt_type", "Request body must be a JSON object")
        if "prompt" not in body:
            return error_response(422, "empty_prompt", "prompt must not be empty")
        if set(body) != {"prompt"}:
            return error_response(422, "invalid_prompt", "Request body must contain only prompt")
        prompt = body.get("prompt")
        if not isinstance(prompt, str):
            return error_response(422, "invalid_prompt_type", "prompt must be a string")
        if not prompt.strip():
            return error_response(422, "empty_prompt", "prompt must not be empty")
        if not service.ready:
            return service.readiness_error()
        try:
            if service.token_count(prompt) > MAX_PROMPT_TOKENS:
                return error_response(422, "prompt_too_long", "prompt exceeds 8192 input tokens")
            response = service.generate(prompt)
        except GenerationDeadlineError:
            return error_response(504, "deadline_exceeded", "generation deadline exceeded")
        except EmptyGenerationError:
            return error_response(500, "empty_generation", "model returned an empty response")
        except ModelNotReadyError:
            return service.readiness_error()
        except Exception:
            LOGGER.exception("Jamba generation failed")
            return error_response(500, "generation_failed", "model generation failed")
        return JSONResponse(status_code=200, content={"model": runtime_config.model_id, "modelRevision": runtime_config.model_revision, "response": response})

    @app.post("/v1/generate")
    async def contract_generate(request: Request) -> JSONResponse:
        """Adapt the model API to the fixed CoreAIgent generation contract."""

        try:
            body = json.loads(await request.body())
        except (UnicodeDecodeError, json.JSONDecodeError):
            return contract_error_response({}, 400, "validation", "Request body must be valid JSON")
        if not valid_contract_request(body):
            return contract_error_response(body, 400, "validation", "Invalid llm-request payload")
        if not service.ready:
            return contract_error_response(body, 503, "dependency", "Jamba model is not ready", retryable=True)

        context = body.get("context", [])
        prompt = body["prompt"]
        if context:
            prompt = prompt + "\n\nBağlam:\n" + "\n".join(context)
        try:
            if service.token_count(prompt) > MAX_PROMPT_TOKENS:
                return contract_error_response(body, 400, "validation", "prompt exceeds 8192 input tokens")
            response = service.generate(prompt)
        except GenerationDeadlineError:
            return contract_error_response(body, 504, "timeout", "generation deadline exceeded", retryable=True)
        except EmptyGenerationError:
            return contract_error_response(body, 502, "dependency", "model returned an empty response", retryable=True)
        except ModelNotReadyError:
            return contract_error_response(body, 503, "dependency", "Jamba model is not ready", retryable=True)
        except Exception:
            LOGGER.exception("Contract generation failed")
            return contract_error_response(body, 502, "dependency", "model generation failed", retryable=True)
        return JSONResponse(
            status_code=200,
            content={
                "schemaVersion": "2.0",
                "requestId": body["requestId"],
                "documentId": body["documentId"],
                "workflowId": body["workflowId"],
                "output": {"draft": response, "department": "manual_review", "confidence": 0.0},
                "model": runtime_config.model_id,
            },
        )

    return app


app = create_app()
