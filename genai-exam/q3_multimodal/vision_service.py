"""Provider layer: Offline Demo Mode and the optional live vision-language models.

Kept completely separate from the Flask routes so that:

* ``app.py`` only worries about HTTP, validation and JSON envelopes;
* the offline demonstration can never be confused with a live model call;
* a live provider failure is reported as a failure and **never** silently
  replaced with sample data.

Live providers are imported lazily inside the call, so the application still
starts (in Offline Demo Mode) when no SDK and no API key are present.
"""

from __future__ import annotations

import base64
import datetime as dt
import os
import time
from dataclasses import dataclass, field

from prompts import (BASE_PROMPT, GEMINI_RESPONSE_SCHEMA, SECOND_OPINION_PROMPT,
                     STRUCTURED_PROMPT)
from samples import (OFFLINE_BANNER, OFFLINE_UNSUPPORTED_MESSAGE, SAMPLE_DATA_NOTICE,
                     get_sample, match_by_digest)
import validator

MODE_OFFLINE = "offline"
MODE_LIVE = "live"

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"        # stable Flash model with a free tier (see docs)
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"    # current Claude API model id, vision capable
DEFAULT_TIMEOUT = 45                              # seconds per request

# provider-error code -> (HTTP status, plain-language message)
ERROR_HTTP = {
    "auth": 401,
    "billing": 402,
    "rate_limit": 429,
    "timeout": 504,
    "network": 502,
    "model": 400,
    "provider_error": 502,
    "invalid_output": 422,
    "unavailable": 503,
    "config": 503,
}


class VisionError(Exception):
    """A failure that must be shown to the user instead of sample data."""

    def __init__(self, code: str, message: str, detail: str = "", provider: str = ""):
        super().__init__(message)
        self.code = code if code in ERROR_HTTP else "provider_error"
        self.message = message
        self.detail = detail
        self.provider = provider

    @property
    def http_status(self) -> int:
        return ERROR_HTTP[self.code]

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
            "provider": self.provider,
            "http_status": self.http_status,
            "sample_data_substituted": False,
        }


@dataclass
class AnalyzeResult:
    mode: str
    provider: str
    model: str
    analysis: dict
    raw_text: str
    validation: dict
    prompt: str
    latency_ms: int
    started_at: str
    finished_at: str
    usage: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    sample: dict | None = None
    illustrative: bool = False

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "mode_label": "Offline Demo Mode" if self.mode == MODE_OFFLINE else "Live AI Mode",
            "provider": self.provider,
            "model": self.model,
            "analysis": self.analysis,
            "raw_model_text": self.raw_text,
            "validation": self.validation,
            "prompt_used": self.prompt,
            "latency_ms": self.latency_ms,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "usage": self.usage,
            "notes": self.notes,
            "illustrative": self.illustrative,
            "banner": OFFLINE_BANNER if self.mode == MODE_OFFLINE else "",
            "sample_key": self.sample["key"] if self.sample else None,
            "sample_title": self.sample["title"] if self.sample else None,
        }


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- config ----
def resolve_config(env: dict | None = None) -> dict:
    """Work out which mode/provider is usable, without calling anything."""
    env = os.environ if env is None else env
    requested = (env.get("AI_MODE") or MODE_OFFLINE).strip().lower()
    if requested not in (MODE_OFFLINE, MODE_LIVE, "auto"):
        requested = MODE_OFFLINE

    gemini_key = bool((env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY") or "").strip())
    anthropic_key = bool((env.get("ANTHROPIC_API_KEY") or "").strip())

    provider = (env.get("AI_PROVIDER") or "").strip().lower()
    if provider not in ("gemini", "anthropic"):
        provider = "gemini" if gemini_key else ("anthropic" if anthropic_key else "")

    models = {
        "gemini": (env.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip(),
        "anthropic": (env.get("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL).strip(),
    }
    key_present = {"gemini": gemini_key, "anthropic": anthropic_key}

    if requested == MODE_OFFLINE:
        mode = MODE_OFFLINE
        reason = "AI_MODE=offline (default): no live model is called."
    elif provider and key_present[provider]:
        mode = MODE_LIVE
        reason = f"AI_MODE={requested} and a credential for provider '{provider}' is present."
    elif requested == "auto":
        mode = MODE_OFFLINE
        reason = ("AI_MODE=auto but no GEMINI_API_KEY / ANTHROPIC_API_KEY is set, "
                  "so the application stays in Offline Demo Mode.")
    else:
        mode = MODE_LIVE  # requested live; provider builder raises a clear 503 instead of faking output
        reason = "AI_MODE=live was requested but no API credential is configured."

    if mode == MODE_LIVE and not provider:
        provider = "gemini"

    return {
        "requested_mode": requested,
        "mode": mode,
        "provider": provider if mode == MODE_LIVE else "",
        "model": models.get(provider, "") if mode == MODE_LIVE else "illustrative sample data (no model)",
        "model_defaults": models,
        "credentials_present": {"gemini": gemini_key, "anthropic": anthropic_key},
        "timeout_seconds": _timeout(env),
        "reason": reason,
        "live_ready": mode == MODE_LIVE,
    }


def _timeout(env: dict | None = None) -> int:
    env = os.environ if env is None else env
    try:
        value = int(float(env.get("REQUEST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT)))
    except (TypeError, ValueError):
        value = DEFAULT_TIMEOUT
    return max(5, min(value, 180))


# ------------------------------------------------------- offline provider ----
class OfflineDemoProvider:
    """Serves hand-written sample data for the three bundled example images only."""

    name = "Offline Demo Mode"
    label = "illustrative sample data (no model was called)"

    def analyze(self, image_bytes: bytes, media_type: str, digest: str,
                sample_key: str | None = None) -> AnalyzeResult:
        started = _now()
        begin = time.perf_counter()

        sample = get_sample(sample_key) if sample_key else None
        matched_by = "sample requested by the user interface"
        if sample is None:
            sample = match_by_digest(digest)
            matched_by = "exact file match (SHA-256) with a bundled sample image"

        if sample is None:
            raise VisionError("unavailable", OFFLINE_UNSUPPORTED_MESSAGE,
                              provider=self.name)

        validation = validator.validate_analysis(sample["analysis"])
        result = AnalyzeResult(
            mode=MODE_OFFLINE,
            provider=self.name,
            model=self.label,
            analysis=validation.normalized if validation.valid else sample["analysis"],
            raw_text="(offline demonstration: no model request was made, no raw model text exists)",
            validation=validation.to_dict(),
            prompt=STRUCTURED_PROMPT,
            latency_ms=int((time.perf_counter() - begin) * 1000),
            started_at=started,
            finished_at=_now(),
            usage={},
            notes=[
                OFFLINE_BANNER,
                SAMPLE_DATA_NOTICE,
                f"Sample selected by: {matched_by}.",
                "The four pixel checks (file type, size, dimensions, digest) were performed for real; the analysis text was not produced by a model.",
            ],
            sample=sample,
            illustrative=True,
        )
        return result


# ----------------------------------------------- live provider: Anthropic ----
class AnthropicVisionProvider:
    """Claude vision model through the official ``anthropic`` SDK."""

    name = "Anthropic Claude API"

    def __init__(self, api_key: str, model: str, timeout: int = DEFAULT_TIMEOUT):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    # -- low level call -----------------------------------------------------
    def _call(self, prompt: str, image_bytes: bytes, media_type: str) -> tuple[str, dict]:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise VisionError("config", "The 'anthropic' package is not installed. Run: pip install anthropic",
                              detail=str(exc), provider=self.name) from exc

        client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout, max_retries=1)
        payload = base64.standard_b64encode(image_bytes).decode("ascii")
        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=1600,
                system=BASE_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image",
                         "source": {"type": "base64", "media_type": media_type, "data": payload}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
        except anthropic.AuthenticationError as exc:
            raise VisionError("auth", "The Anthropic API rejected the API key.",
                              detail=str(exc), provider=self.name) from exc
        except anthropic.PermissionDeniedError as exc:
            raise VisionError("auth", "The Anthropic API key does not have permission for this model.",
                              detail=str(exc), provider=self.name) from exc
        except anthropic.RateLimitError as exc:
            raise VisionError("rate_limit", "The Anthropic API rate limit or quota was reached. Try again later.",
                              detail=str(exc), provider=self.name) from exc
        except anthropic.APIStatusError as exc:
            text = str(exc)
            if "credit balance" in text.lower() or "billing" in text.lower():
                raise VisionError("billing",
                                  "The Anthropic account has insufficient credits, so live analysis is unavailable. "
                                  "Use Offline Demo Mode or top up the account.",
                                  detail=text, provider=self.name) from exc
            if exc.status_code == 400:
                raise VisionError("model", "The Anthropic API rejected the request (check the model id in ANTHROPIC_MODEL).",
                                  detail=text, provider=self.name) from exc
            raise VisionError("provider_error", f"Anthropic API error (HTTP {exc.status_code}).",
                              detail=text, provider=self.name) from exc
        except (anthropic.APITimeoutError, TimeoutError) as exc:
            raise VisionError("timeout", f"The Anthropic request exceeded {self.timeout} seconds.",
                              detail=str(exc), provider=self.name) from exc
        except anthropic.APIConnectionError as exc:
            raise VisionError("network", "Could not reach the Anthropic API. Check the internet connection.",
                              detail=str(exc), provider=self.name) from exc

        text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
        usage = {
            "input_tokens": getattr(message.usage, "input_tokens", None),
            "output_tokens": getattr(message.usage, "output_tokens", None),
            "stop_reason": getattr(message, "stop_reason", None),
        }
        return text, usage

    def analyze(self, image_bytes: bytes, media_type: str, digest: str,
                sample_key: str | None = None) -> AnalyzeResult:
        return _live_result(self, image_bytes, media_type, STRUCTURED_PROMPT, self.name, self.model)


# -------------------------------------------------- live provider: Gemini ----
class GeminiVisionProvider:
    """Google Gemini vision model through the official ``google-genai`` SDK."""

    name = "Google Gemini API"

    def __init__(self, api_key: str, model: str, timeout: int = DEFAULT_TIMEOUT):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _client(self):
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise VisionError("config", "The 'google-genai' package is not installed. Run: pip install google-genai",
                              detail=str(exc), provider=self.name) from exc
        try:
            from google.genai import types as genai_types
            http_options = genai_types.HttpOptions(timeout=self.timeout * 1000)
            return genai.Client(api_key=self.api_key, http_options=http_options)
        except Exception:  # pragma: no cover - older SDK signatures
            return genai.Client(api_key=self.api_key)

    def _call(self, prompt: str, image_bytes: bytes, media_type: str) -> tuple[str, dict]:
        client = self._client()
        payload = base64.standard_b64encode(image_bytes).decode("ascii")

        # Newer SDKs expose the Interactions API (current documented call).
        if hasattr(client, "interactions"):
            try:
                interaction = client.interactions.create(
                    model=self.model,
                    input=[
                        {"type": "text", "text": prompt},
                        {"type": "image", "data": payload, "mime_type": media_type},
                    ],
                    response_format={"type": "text", "mime_type": "application/json",
                                     "schema": GEMINI_RESPONSE_SCHEMA},
                )
                return self._text(interaction), {"api": "interactions"}
            except Exception as exc:  # fall through to generate_content on API differences
                fallback_error = exc

        # Fallback: classic generate_content with a JSON response schema.
        try:
            from google.genai import types as genai_types

            response = client.models.generate_content(
                model=self.model,
                contents=[genai_types.Part.from_bytes(data=image_bytes, mime_type=media_type), prompt],
                config=genai_types.GenerateContentConfig(
                    system_instruction=BASE_PROMPT,
                    response_mime_type="application/json",
                    response_schema=GEMINI_RESPONSE_SCHEMA,
                    temperature=0.2,
                ),
            )
            return self._text(response), {"api": "generate_content"}
        except Exception as exc:
            raise _gemini_error(exc, self.name, self.timeout, locals().get("fallback_error")) from exc

    @staticmethod
    def _text(response) -> str:
        for attribute in ("output_text", "text"):
            value = getattr(response, attribute, None)
            if isinstance(value, str) and value.strip():
                return value
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                text = getattr(part, "text", None)
                if text:
                    return text
        raise VisionError("invalid_output", "The Gemini response contained no text.")

    def analyze(self, image_bytes: bytes, media_type: str, digest: str,
                sample_key: str | None = None) -> AnalyzeResult:
        return _live_result(self, image_bytes, media_type, STRUCTURED_PROMPT, self.name, self.model)


def _gemini_error(exc: Exception, provider_name: str, timeout: int, fallback_error: Exception | None = None) -> VisionError:
    text = f"{exc}" + (f" | earlier attempt: {fallback_error}" if fallback_error else "")
    lowered = text.lower()
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if "api key" in lowered or "unauthenticated" in lowered or status in (401, 403):
        return VisionError("auth", "The Gemini API rejected the API key.", detail=text, provider=provider_name)
    if "quota" in lowered or "rate limit" in lowered or "resource_exhausted" in lowered or status == 429:
        return VisionError("rate_limit", "The Gemini API free-tier quota or rate limit was reached. Try again later "
                                         "or check the limits in Google AI Studio.", detail=text, provider=provider_name)
    if "billing" in lowered or "payment" in lowered:
        return VisionError("billing", "The Google Cloud project for this key has a billing problem.", detail=text,
                           provider=provider_name)
    if "timeout" in lowered or "deadline" in lowered or isinstance(exc, TimeoutError):
        return VisionError("timeout", f"The Gemini request exceeded {timeout} seconds.", detail=text, provider=provider_name)
    if "not found" in lowered or "invalid model" in lowered or "unsupported" in lowered or status == 404:
        return VisionError("model", "The Gemini model id was rejected. Check GEMINI_MODEL.", detail=text,
                           provider=provider_name)
    if "connect" in lowered or "network" in lowered or "dns" in lowered:
        return VisionError("network", "Could not reach the Gemini API. Check the internet connection.", detail=text,
                           provider=provider_name)
    return VisionError("provider_error", "The Gemini API request failed.", detail=text, provider=provider_name)


# ------------------------------------------------------- shared plumbing ----
def _live_result(provider, image_bytes: bytes, media_type: str, prompt: str,
                 provider_name: str, model: str) -> AnalyzeResult:
    """Call a live provider, then extract and validate the JSON. Nothing is faked."""
    started = _now()
    begin = time.perf_counter()
    raw_text, usage = provider._call(prompt, image_bytes, media_type)
    latency = int((time.perf_counter() - begin) * 1000)

    try:
        parsed = validator.extract_json(raw_text)
    except validator.JSONExtractionError as exc:
        raise VisionError("invalid_output",
                          "The model did not return valid JSON, so the result was discarded and no sample data "
                          "was substituted.",
                          detail=str(exc), provider=provider_name) from exc

    validation = validator.validate_analysis(parsed)
    if not validation.valid:
        messages = "; ".join(f"{e['field']}: {e['message']}" for e in validation.errors)
        raise VisionError("invalid_output",
                          "The model returned JSON that does not match the required schema, so the result was "
                          "discarded and no sample data was substituted.",
                          detail=messages, provider=provider_name)

    return AnalyzeResult(
        mode=MODE_LIVE,
        provider=provider_name,
        model=model,
        analysis=validation.normalized,
        raw_text=raw_text,
        validation=validation.to_dict(),
        prompt=prompt,
        latency_ms=latency,
        started_at=started,
        finished_at=_now(),
        usage=usage,
        notes=["Live model output. Schema validation passed - that proves the structure, not the factual accuracy. "
               "Use the evaluation stage to check the content against the image."],
    )


def build_live_provider(config: dict):
    provider_name = config.get("provider")
    env = os.environ
    timeout = config.get("timeout_seconds", DEFAULT_TIMEOUT)

    if provider_name == "gemini":
        key = (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY") or "").strip()
        if not key:
            raise VisionError("config",
                              "Live AI mode with Gemini needs GEMINI_API_KEY (or GOOGLE_API_KEY). "
                              "Add it to your .env file or switch to Offline Demo Mode.",
                              provider="Google Gemini API")
        return GeminiVisionProvider(key, config["model_defaults"]["gemini"], timeout)

    if provider_name == "anthropic":
        key = (env.get("ANTHROPIC_API_KEY") or "").strip()
        if not key:
            raise VisionError("config",
                              "Live AI mode with Anthropic needs ANTHROPIC_API_KEY. "
                              "Add it to your .env file or switch to Offline Demo Mode.",
                              provider="Anthropic Claude API")
        return AnthropicVisionProvider(key, config["model_defaults"]["anthropic"], timeout)

    raise VisionError("config", "No live provider is configured.", provider="")


def analyze_image(image_bytes: bytes, media_type: str, digest: str,
                  mode: str | None = None, sample_key: str | None = None,
                  env: dict | None = None) -> AnalyzeResult:
    """Main entry point used by the Flask route.

    ``mode`` overrides AI_MODE for a single request ("offline" / "live" / "auto").
    """
    environment = dict(os.environ if env is None else env)
    if mode:
        environment["AI_MODE"] = mode
    config = resolve_config(environment)

    if config["mode"] == MODE_OFFLINE:
        return OfflineDemoProvider().analyze(image_bytes, media_type, digest, sample_key)

    provider = build_live_provider(config)
    return provider.analyze(image_bytes, media_type, digest, sample_key)


def second_opinion(image_bytes: bytes, media_type: str, analysis: dict,
                   env: dict | None = None) -> dict:
    """Optional: ask a live model to review an analysis. Never ground truth."""
    config = resolve_config(env)
    if config["mode"] != MODE_LIVE:
        raise VisionError("config",
                          "A second-opinion review needs a live model. Offline Demo Mode has no model to call.",
                          provider="")
    provider = build_live_provider(config)
    prompt = (SECOND_OPINION_PROMPT + "\n\nAnalysis under review (JSON):\n"
              + str(analysis).replace("'", '"'))
    raw_text, usage = provider._call(prompt, image_bytes, media_type)
    try:
        parsed = validator.extract_json(raw_text)
    except validator.JSONExtractionError as exc:
        raise VisionError("invalid_output", "The reviewing model did not return valid JSON.",
                          detail=str(exc), provider=provider.name) from exc

    concerns = parsed.get("concerns") if isinstance(parsed, dict) else None
    cleaned = []
    for item in concerns or []:
        if not isinstance(item, dict):
            continue
        cleaned.append({
            "statement": str(item.get("statement", "")).strip(),
            "category": str(item.get("category", "uncertain_detail")).strip(),
            "explanation": str(item.get("explanation", "")).strip(),
            "suggested_correction": str(item.get("suggested_correction", "")).strip(),
        })
    return {
        "provider": provider.name,
        "model": config["model_defaults"][config["provider"]],
        "usage": usage,
        "concerns": cleaned,
        "verified_ok": [str(v) for v in (parsed.get("verified_ok") or [])][:20],
        "label": (
            "Second-opinion review by another AI model. It is not independent ground truth and can repeat the "
            "same mistakes; every point still needs human verification."
        ) if cleaned else (
            "The reviewing model reported no concerns. That is not proof of correctness - it only means this "
            "model did not flag anything."
        ),
        "requires_verification": True,
    }
