"""Multimodal AI-Based Image Understanding System — Flask backend (Q.3).

Routes
------
GET  /                main single-page interface (dashboard)
GET  /api/health      health check + which mode the server is in
GET  /api/samples     metadata of the three bundled example images
GET  /api/prompt      the exact prompts used, plus the basic/structured comparison
POST /api/analyze     validate an uploaded image and analyse it (offline or live)
POST /api/evaluate    evaluate an analysis and list errors/omissions/unsupported claims
POST /api/review      apply a manual review action (confirm / reject / edit / add)
POST /api/report      download the evaluation report (Markdown or JSON)
GET  /images/<name>   the bundled sample images (no arbitrary file access)

Design rules
------------
* Every response is JSON with the same envelope: {"ok": true, "data": ...}
  or {"ok": false, "error": {...}}, and a sensible HTTP status code.
* Uploaded file contents are validated by decoding them with Pillow, not by
  looking at the file name or the browser-supplied MIME type.
* User input is treated as data only. It is never executed, never used to build
  a shell command or a file path, and images are never written to disk.
* A live-model failure is reported as a failure. Sample data is never silently
  substituted for a live call.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import secrets
import sys
from collections import OrderedDict
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

import evaluator
import report_generator
import samples
import validator
import vision_service
from prompts import (ANALYSIS_FIELDS, BASE_PROMPT, BASIC_PROMPT, FIELD_RULES,
                     JSON_EXAMPLE, PROMPT_COMPARISON, PROMPT_NOTES, STRUCTURED_PROMPT)

APP_VERSION = "1.0.0"
MAX_IMAGE_BYTES = 10 * 1024 * 1024                      # 10 MB, as required
MAX_REQUEST_BYTES = MAX_IMAGE_BYTES + 256 * 1024        # multipart overhead
ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
MIN_DIMENSION = 16                                      # reject degenerate images
MAX_PIXELS = 40_000_000                                 # decompression-bomb guard

BASE_DIR = Path(__file__).parent
IMAGES_DIR = BASE_DIR / "images"

# analysis_id -> record. In memory only: uploads are never stored on disk.
ANALYSIS_STORE: "OrderedDict[str, dict]" = OrderedDict()
MAX_STORED_ANALYSES = 12


class ApiError(Exception):
    """Error that becomes a JSON response with a specific status code."""

    def __init__(self, code: str, message: str, status: int = 400, details=None, hint: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or []
        self.hint = hint

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "hint": self.hint,
        }


# ------------------------------------------------------------ image checks ---
def inspect_image(raw: bytes, filename: str = "") -> dict:
    """Validate an upload by decoding its actual image contents.

    Returns metadata (format, media type, dimensions, size, sha256) or raises
    ApiError with a clear message. Nothing here trusts the file name or the
    client-provided content type.
    """
    from PIL import Image, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS      # Pillow then rejects decompression bombs while opening

    if not raw:
        raise ApiError("empty_file", "The uploaded file is empty (0 bytes).", 400,
                       hint="Choose an image file and try again.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ApiError("file_too_large",
                       f"The file is {len(raw) / (1024 * 1024):.1f} MB, which is larger than the 10 MB limit.",
                       413, hint="Resize or compress the image and upload it again.")

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            image_format = (probe.format or "").upper()
            width, height = probe.size
            probe.verify()                      # structural check (CRC / truncation)
    except UnidentifiedImageError as exc:
        raise ApiError("not_an_image",
                       "The uploaded file is not a readable image. Its contents could not be decoded, "
                       "so a renamed .txt or other non-image file is rejected.",
                       400, hint="Upload a JPG, JPEG, PNG or WEBP image.") from exc
    except Image.DecompressionBombError as exc:
        raise ApiError("image_too_large_dimensions",
                       f"The image has more than {MAX_PIXELS:,} pixels, which is above the safety limit.",
                       413) from exc
    except Exception as exc:
        raise ApiError("corrupted_image",
                       "The image data is corrupted or truncated and could not be decoded.",
                       400, details=[str(exc)]) from exc

    if image_format not in ALLOWED_FORMATS:
        raise ApiError("unsupported_format",
                       f"'{image_format or 'unknown'}' images are not supported. Use JPG, JPEG, PNG or WEBP.",
                       415, hint="Convert the image with an image editor or Pillow and upload it again.")
    if width * height > MAX_PIXELS:
        raise ApiError("image_too_large_dimensions",
                       f"The image is {width}x{height} = {width * height:,} pixels, which is above the "
                       f"{MAX_PIXELS:,} pixel safety limit.", 413)
    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        raise ApiError("image_too_small",
                       f"The image is only {width}x{height} pixels, so there is nothing meaningful to analyse.",
                       400)

    # full decode: this is what catches truncated / half-corrupted files
    try:
        with Image.open(io.BytesIO(raw)) as full:
            full.load()
            width, height = full.size
    except Exception as exc:
        raise ApiError("corrupted_image",
                       "The image starts with a valid header but the pixel data could not be decoded, "
                       "so the file is corrupted.",
                       400, details=[str(exc)]) from exc

    extension_note = ""
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    if suffix and suffix not in ("jpg", "jpeg", "png", "webp"):
        extension_note = (f"The file name ends in '.{suffix}' but the contents are a real {image_format} image; "
                          "the detected content type was used.")

    return {
        "filename": Path(filename or "upload").name[:120] or "upload",
        "format": image_format,
        "media_type": ALLOWED_FORMATS[image_format],
        "width": width,
        "height": height,
        "bytes": len(raw),
        "digest": hashlib.sha256(raw).hexdigest(),
        "extension_note": extension_note,
    }


def validate_upload_request(upload) -> tuple[bytes, dict]:
    if upload is None or not getattr(upload, "filename", ""):
        raise ApiError("missing_input", "No image file was received in the field named 'image'.", 400,
                       hint="Pick a file with the file chooser or drop it on the drop zone.")
    raw = upload.read(MAX_IMAGE_BYTES + 1)
    meta = inspect_image(raw, upload.filename)
    return raw, meta


# ------------------------------------------------------------ app factory ---
def create_app(config: dict | None = None) -> Flask:
    try:                                   # optional convenience: load .env for local runs
        from dotenv import load_dotenv

        load_dotenv(BASE_DIR / ".env", override=False)
    except ImportError:                    # pragma: no cover - dotenv is optional
        pass

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.update(
        MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES,
        JSON_SORT_KEYS=False,
        REVIEW_STORE_PATH=os.environ.get("REVIEW_STORE_PATH", str(BASE_DIR / "instance" / "reviews.json")),
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(16),
    )
    if config:
        app.config.update(config)

    store = evaluator.ReviewStore(app.config["REVIEW_STORE_PATH"])
    app.config["REVIEW_STORE"] = store

    # ------------------------------------------------------------- helpers --
    def ok(data, message: str = "", status: int = 200):
        return jsonify({"ok": True, "data": data, "message": message}), status

    def fail(error: ApiError):
        return jsonify({"ok": False, "error": error.to_dict()}), error.status

    def remember(analysis_id: str, record: dict) -> None:
        ANALYSIS_STORE[analysis_id] = record
        ANALYSIS_STORE.move_to_end(analysis_id)
        while len(ANALYSIS_STORE) > MAX_STORED_ANALYSES:
            ANALYSIS_STORE.popitem(last=False)

    def current_mode_config(mode_override: str | None = None) -> dict:
        environment = dict(os.environ)
        if mode_override:
            environment["AI_MODE"] = mode_override
        return vision_service.resolve_config(environment)

    def run_evaluation(record: dict, use_second_opinion: bool = False) -> dict:
        analysis = record["analysis"]
        evaluation = evaluator.build_evaluation(
            analysis,
            sample_key=record.get("sample_key"),
            ground_truth=record.get("ground_truth"),
            mode=record["meta"]["mode"],
        )
        findings = evaluator.apply_actions(evaluation["findings"], store.actions_for(record["analysis_id"]))
        evaluation["findings"] = findings
        evaluation["counts"] = {key: 0 for key in evaluator.CATEGORIES}
        for finding in findings:
            evaluation["counts"][finding["category"]] = evaluation["counts"].get(finding["category"], 0) + 1
        evaluation["counts_labelled"] = {evaluator.CATEGORIES[k]: v for k, v in evaluation["counts"].items()}
        evaluation["total"] = len(findings)
        evaluation["confirmed"] = sum(1 for f in findings if f["verification_status"] == "confirmed")
        evaluation["rejected"] = sum(1 for f in findings if f["verification_status"] == "rejected")
        evaluation["edited"] = sum(1 for f in findings if f["verification_status"] == "edited")
        evaluation["pending"] = sum(1 for f in findings if f["verification_status"] == "pending")
        evaluation["categories"] = [
            {"key": key, "label": label} for key, label in evaluator.CATEGORIES.items()
        ]

        if use_second_opinion:
            raw = record.get("image_bytes")
            if raw is None and record.get("sample_key"):
                sample = samples.get_sample(record["sample_key"])
                raw = (IMAGES_DIR / sample["filename"]).read_bytes() if sample else None
            if raw is None:
                raise ApiError("no_image", "The original image is no longer available for a second-opinion "
                                           "request. Re-upload it and analyse it again.", 409)
            try:
                evaluation["second_opinion"] = vision_service.second_opinion(
                    raw, record["image_meta"]["media_type"], analysis
                )
            except vision_service.VisionError as exc:
                raise ApiError("second_opinion_failed", exc.message, exc.http_status,
                               details=[exc.detail] if exc.detail else []) from exc
        return evaluation

    # -------------------------------------------------------------- pages ---
    @app.get("/")
    def index():
        config = current_mode_config()
        return render_template(
            "index.html",
            app_version=APP_VERSION,
            python_version=sys.version.split()[0],
            mode_config=config,
            offline_banner=samples.OFFLINE_BANNER,
            sample_data_notice=samples.SAMPLE_DATA_NOTICE,
            unsupported_message=samples.OFFLINE_UNSUPPORTED_MESSAGE,
            sample_list=samples.metadata(),
            base_prompt=BASE_PROMPT,
            basic_prompt=BASIC_PROMPT,
            structured_prompt=STRUCTURED_PROMPT,
            field_rules=FIELD_RULES,
            json_example=json.dumps(JSON_EXAMPLE, indent=2),
            schema_rules=list(validator.SCHEMA_RULES),
            prompt_comparison=PROMPT_COMPARISON,
            prompt_notes=PROMPT_NOTES,
            categories=[{"key": k, "label": v} for k, v in evaluator.CATEGORIES.items()],
            statuses=[{"key": k, "label": v} for k, v in evaluator.VERIFICATION_STATUSES.items()],
            max_mb=MAX_IMAGE_BYTES // (1024 * 1024),
            student=report_generator.STUDENT,
        )

    @app.get("/images/<path:name>")
    def serve_image(name: str):
        # only the three documented sample files are served (no directory traversal)
        allowed = {sample["filename"] for sample in samples.SAMPLES.values()}
        if name not in allowed:
            raise ApiError("not_found", "Unknown sample image.", 404)
        return send_from_directory(IMAGES_DIR, name, max_age=3600)

    # --------------------------------------------------------------- api ----
    @app.get("/api/health")
    def health():
        config = current_mode_config()
        return ok({
            "status": "healthy",
            "app": "Multimodal AI-Based Image Understanding System",
            "version": APP_VERSION,
            "python": sys.version.split()[0],
            "platform": platform.system(),
            "mode": config["mode"],
            "mode_label": "Offline Demo Mode" if config["mode"] == "offline" else "Live AI Mode",
            "provider": config["provider"] or None,
            "model": config["model"],
            "live_ready": config["live_ready"],
            "credentials_present": config["credentials_present"],
            "reason": config["reason"],
            "sample_images": len(samples.SAMPLES),
            "max_upload_mb": MAX_IMAGE_BYTES // (1024 * 1024),
            "time": vision_service._now(),
        })

    @app.get("/api/samples")
    def sample_list():
        return ok({
            "samples": samples.metadata(),
            "banner": samples.OFFLINE_BANNER,
            "notice": samples.SAMPLE_DATA_NOTICE,
            "unsupported_message": samples.OFFLINE_UNSUPPORTED_MESSAGE,
        })

    @app.get("/api/prompt")
    def prompt_info():
        return ok({
            "base_prompt": BASE_PROMPT,
            "basic_prompt": BASIC_PROMPT,
            "structured_prompt": STRUCTURED_PROMPT,
            "field_rules": FIELD_RULES,
            "json_example": JSON_EXAMPLE,
            "comparison": PROMPT_COMPARISON,
            "notes": PROMPT_NOTES,
            "usage": "STRUCTURED_PROMPT is sent to the live model with BASE_PROMPT as the system instruction. "
                     "Its text is also stored with every analysis so a report always shows what was asked.",
        })

    @app.post("/api/analyze")
    def analyze():
        mode = sample_key = None
        raw = None
        image_meta = None

        try:
            if request.files or (request.content_type or "").startswith("multipart/form-data"):
                upload = request.files.get("image")
                raw, image_meta = validate_upload_request(upload)
                mode = (request.form.get("mode") or "").strip().lower() or None
                sample_key = (request.form.get("demo_key") or "").strip().lower() or None
            else:
                payload = request.get_json(silent=True) or {}
                mode = str(payload.get("mode") or "").strip().lower() or None
                sample_key = str(payload.get("demo_key") or "").strip().lower() or None
                if sample_key:
                    sample = samples.get_sample(sample_key)
                    if not sample:
                        raise ApiError("unknown_sample",
                                       f"'{sample_key}' is not one of the bundled example images.", 404,
                                       details=[f"Available: {', '.join(samples.SAMPLE_ORDER)}"])
                    path = IMAGES_DIR / sample["filename"]
                    raw = path.read_bytes()
                    image_meta = inspect_image(raw, sample["filename"])
                elif not raw:
                    raise ApiError("missing_input",
                                   "Provide an image file (multipart field 'image') or a bundled demo key "
                                   "('demo_key').", 400)
        except RequestEntityTooLarge as exc:
            return fail(ApiError("file_too_large",
                                 "The request body is larger than the 10 MB upload limit.", 413,
                                 details=[str(exc)]))
        except ApiError as error:
            return fail(error)

        if mode and mode not in ("offline", "live", "auto"):
            return fail(ApiError("bad_mode", "mode must be 'offline', 'live' or 'auto'.", 400))

        # ---------------------------------------------------- run analysis --
        try:
            result = vision_service.analyze_image(raw, image_meta["media_type"], image_meta["digest"],
                                                  mode=mode, sample_key=sample_key)
        except vision_service.VisionError as exc:
            return fail(ApiError(exc.code, exc.message, exc.http_status,
                                 details=[exc.detail] if exc.detail else []))

        mode_used = result.mode
        if mode_used == "offline" and sample_key is None:
            analysis_id = "demo:" + (result.sample["key"] if result.sample else "unknown")
        else:
            analysis_id = f"{mode_used}-{secrets.token_hex(6)}"

        record = {
            "analysis_id": analysis_id,
            "analysis": result.analysis,
            "meta": result.to_dict(),
            "image_meta": image_meta,
            "sample_key": result.sample["key"] if result.sample else None,
            "ground_truth": (result.sample or {}).get("ground_truth"),
            "image_bytes": None if result.sample else raw,     # samples are re-read from disk when needed
            "validation": result.validation,
        }
        remember(analysis_id, record)

        data = result.to_dict()
        data["analysis_id"] = analysis_id
        data["image"] = {
            "filename": image_meta["filename"],
            "width": image_meta["width"],
            "height": image_meta["height"],
            "bytes": image_meta["bytes"],
            "media_type": image_meta["media_type"],
            "digest": image_meta["digest"],
            "format": image_meta["format"],
            "preview_url": (result.sample or {}).get("url") if result.sample else None,
        }
        data["warnings"] = [image_meta["extension_note"]] if image_meta.get("extension_note") else []
        if result.sample:
            data["sample"] = {
                "key": result.sample["key"],
                "title": result.sample["title"],
                "category": result.sample["category"],
                "source": result.sample["source"],
                "licence": result.sample["licence"],
                "url": result.sample["url"],
                "ground_truth": result.sample["ground_truth"],
            }
        else:
            data["sample"] = None

        message = ("Analysis produced from illustrative offline sample data."
                   if result.mode == "offline" else
                   f"Analysis produced by the live model {result.model}.")
        return ok(data, message)

    @app.post("/api/evaluate")
    def evaluate():
        payload = request.get_json(silent=True) or {}
        analysis_id = str(payload.get("analysis_id") or "").strip()
        if not analysis_id:
            raise ApiError("missing_input", "analysis_id is required. Call /api/analyze first.", 400)

        record = ANALYSIS_STORE.get(analysis_id)
        if not record:
            raise ApiError("unknown_analysis",
                           "That analysis is no longer in memory. The server keeps the last "
                           f"{MAX_STORED_ANALYSES} analyses in RAM only (uploads are never written to disk), "
                           "so please analyse the image again.", 404)

        try:
            evaluation = run_evaluation(record, bool(payload.get("use_second_opinion")))
        except ApiError as error:
            return fail(error)

        return ok({
            "analysis_id": analysis_id,
            "mode": record["meta"]["mode"],
            "mode_label": record["meta"]["mode_label"],
            "illustrative": record["meta"]["illustrative"],
            "evaluation": evaluation,
            "statuses": [{"key": k, "label": v} for k, v in evaluator.VERIFICATION_STATUSES.items()],
        }, "Evaluation completed. Findings are hypotheses until a human reviews them.")

    @app.post("/api/review")
    def review():
        payload = request.get_json(silent=True) or {}
        analysis_id = str(payload.get("analysis_id") or "").strip()
        action = payload.get("action") or {}
        if not analysis_id:
            raise ApiError("missing_input", "analysis_id is required.", 400)
        if not isinstance(action, dict) or not str(action.get("type", "")).strip():
            raise ApiError("missing_input", "action with a 'type' is required (confirm, reject, edit, add, reset).",
                           400)
        record = ANALYSIS_STORE.get(analysis_id)
        if not record:
            raise ApiError("unknown_analysis", "That analysis is no longer in memory; analyse the image again.", 404)

        kind = str(action["type"]).lower()
        if kind not in ("confirm", "reject", "edit", "add", "reset"):
            raise ApiError("bad_action", "action.type must be confirm, reject, edit, add or reset.", 400)
        if kind in ("confirm", "reject", "edit", "reset") and not str(action.get("finding_id", "")).strip():
            raise ApiError("missing_input", f"action.type '{kind}' also needs finding_id.", 400)
        if kind == "add":
            try:
                evaluator.new_finding(action.get("finding") or {})
            except ValueError as exc:
                raise ApiError("bad_action", str(exc), 400) from exc
        if kind == "edit":
            for field in ("statement", "visible", "why", "suggested_correction"):
                if field in action and not str(action[field]).strip():
                    raise ApiError("bad_action", f"Edited field '{field}' must not be empty.", 400)
            if "category" in action and str(action["category"]).lower() not in evaluator.CATEGORIES:
                raise ApiError("bad_action", "Unknown category for the edited finding.", 400)

        if kind == "reset" and payload.get("clear_all"):
            store.clear(analysis_id)
        else:
            store.add_action(analysis_id, action)

        try:
            evaluation = run_evaluation(record)
        except ApiError as error:
            return fail(error)
        return ok({
            "analysis_id": analysis_id,
            "applied": kind,
            "evaluation": evaluation,
        }, f"Review action '{kind}' recorded.")

    @app.post("/api/report")
    def report():
        payload = request.get_json(silent=True) or {}
        analysis_id = str(payload.get("analysis_id") or "").strip()
        fmt = str(payload.get("format") or "md").strip().lower()
        if not analysis_id:
            raise ApiError("missing_input", "analysis_id is required.", 400)
        if fmt not in ("md", "json"):
            raise ApiError("bad_format", "format must be 'md' or 'json'.", 400)
        record = ANALYSIS_STORE.get(analysis_id)
        if not record:
            raise ApiError("unknown_analysis", "That analysis is no longer in memory; analyse the image again.", 404)

        try:
            evaluation = run_evaluation(record)
        except ApiError as error:
            return fail(error)

        document = {
            "image": record["image_meta"],
            "meta": record["meta"],
            "analysis": record["analysis"],
            "validation": record["validation"],
            "evaluation": evaluation,
            "second_opinion": evaluation.get("second_opinion"),
        }
        if fmt == "json":
            text = report_generator.build_json(document)
            mimetype, extension = "application/json", "json"
        else:
            text = report_generator.build_markdown(document)
            mimetype, extension = "text/markdown", "md"

        buffer = io.BytesIO(text.encode("utf-8"))
        buffer.seek(0)
        filename = f"image_understanding_report_{analysis_id.replace(':', '_')}.{extension}"
        return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=filename)

    # ------------------------------------------------------ error handlers --
    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return fail(error)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(error: RequestEntityTooLarge):
        return fail(ApiError("file_too_large",
                             "The upload is larger than the 10 MB limit, so it was rejected before analysis.",
                             413, details=[str(error)]))

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return fail(ApiError(error.name.lower().replace(" ", "_"), error.description or error.name, error.code or 500))

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):        # pragma: no cover - safety net
        app.logger.exception("Unhandled error")
        return fail(ApiError("internal_error",
                             "The server hit an unexpected error. No sample data was substituted for your request.",
                             500, details=[str(error)]))

    return app


app = create_app()


if __name__ == "__main__":
    config = vision_service.resolve_config()
    print("Multimodal AI-Based Image Understanding System")
    print(f"  mode      : {config['mode']}  ({config['reason']})")
    print(f"  provider  : {config['provider'] or 'none (offline demonstration)'}")
    print(f"  model     : {config['model']}")
    print("  URL       : http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
