"""Jamba2-3B-Turkish inference API for the CoreAIgent ``llm`` service.

The model loader is deliberately an injected boundary. Production uses
``RealJambaLoader``; CPU tests inject a tiny/fake loader so they never download
or initialize the real CUDA model.
"""

from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

MODEL_ID = "serda-dev/Jamba2-3B-Turkish"
MODEL_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MAX_PROMPT_TOKENS = 1024


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
        )

    def validation_error(self) -> Optional[str]:
        if self.model_id != MODEL_ID:
            return "MODEL_ID must be serda-dev/Jamba2-3B-Turkish"
        if not MODEL_REVISION_PATTERN.fullmatch(self.model_revision):
            return "MODEL_REVISION must be a 40-character lowercase commit SHA"
        if not self.hf_home or not self.hf_home.startswith("/"):
            return "HF_HOME must be an absolute path"
        if not 1 <= self.max_new_tokens <= 512:
            return "MAX_NEW_TOKENS must be between 1 and 512"
        if not 0.0 <= self.temperature <= 2.0:
            return "TEMPERATURE must be between 0.0 and 2.0"
        if not 0.0 < self.top_p <= 1.0:
            return "TOP_P must be greater than 0.0 and at most 1.0"
        if not 5.0 <= self.deadline_seconds <= 120.0:
            return "GENERATION_DEADLINE_SECONDS must be between 5 and 120"
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

        model_config = AutoConfig.from_pretrained(
            config.model_id,
            revision=config.model_revision,
            cache_dir=config.hf_home,
            trust_remote_code=True,
        )
        if hasattr(model_config, "use_mamba_kernels"):
            model_config.use_mamba_kernels = True
        if hasattr(model_config, "use_cache"):
            model_config.use_cache = True

        tokenizer = AutoTokenizer.from_pretrained(
            config.model_id,
            revision=config.model_revision,
            cache_dir=config.hf_home,
            trust_remote_code=True,
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            config.model_id,
            revision=config.model_revision,
            cache_dir=config.hf_home,
            config=model_config,
            device_map="auto",
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
        messages = [{"role": "user", "content": prompt}]
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


class JambaService:
    """Runtime state, lifecycle, validation, and serialized generation."""

    def __init__(self, loader: ModelLoader, config: RuntimeConfig, gpu_available: bool) -> None:
        self.loader = loader
        self.config = config
        self.gpu_available = gpu_available
        self.model_loaded = False
        self.accepting_inference = False
        self.readiness_code: Optional[str] = None
        self._backend: Any = None
        self._generation_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jamba-generation")
        self._initialize()

    def _initialize(self) -> None:
        if not self.gpu_available:
            self.readiness_code = "gpu_unavailable"
            return
        if (error := self.config.validation_error()) is not None:
            self.readiness_code = "model_not_ready"
            return
        try:
            self._backend = self.loader.load(self.config)
            self.model_loaded = True
            self.accepting_inference = True
        except Exception:
            self.readiness_code = "model_not_ready"

    @property
    def ready(self) -> bool:
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


def _gpu_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def create_app(
    *,
    loader: Optional[ModelLoader] = None,
    config: Optional[RuntimeConfig] = None,
    gpu_available: Optional[bool] = None,
) -> FastAPI:
    runtime_config = config or RuntimeConfig.from_env()
    service = JambaService(
        loader or RealJambaLoader(),
        runtime_config,
        _gpu_available() if gpu_available is None else gpu_available,
    )
    app = FastAPI(title="CoreAIgent LLM", docs_url=None, redoc_url=None)
    app.state.jamba_service = service

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "model": runtime_config.model_id, "model_loaded": service.model_loaded}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        if not service.ready:
            return service.readiness_error()
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "model": runtime_config.model_id, "model_loaded": True},
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
                return error_response(422, "prompt_too_long", "prompt exceeds 1024 input tokens")
            response = service.generate(prompt)
        except GenerationDeadlineError:
            return error_response(504, "deadline_exceeded", "generation deadline exceeded")
        except EmptyGenerationError:
            return error_response(500, "empty_generation", "model returned an empty response")
        except ModelNotReadyError:
            return service.readiness_error()
        except Exception:
            return error_response(500, "generation_failed", "model generation failed")
        return JSONResponse(status_code=200, content={"model": runtime_config.model_id, "response": response})

    return app


app = create_app()
