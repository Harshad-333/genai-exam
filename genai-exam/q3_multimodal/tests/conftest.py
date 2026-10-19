"""Shared pytest fixtures.

All external model calls are mocked: the suite never needs an API key, an
internet connection or paid credits. The tests are **software tests** - they
prove that the code behaves correctly; they do not prove that a description of
an image is factually true (that is the evaluation stage plus human review).
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import app as app_module          # noqa: E402  (path setup must come first)
import samples                    # noqa: E402
import validator                  # noqa: E402


def make_image_bytes(width: int = 320, height: int = 240, fmt: str = "JPEG", colour=(90, 130, 200)) -> bytes:
    """Create a real in-memory image for upload tests."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, fmt)
    return buffer.getvalue()


def make_oversized_jpeg(megabytes: int = 11) -> bytes:
    """A JPEG that is genuinely larger than the 10 MB upload limit."""
    size = 2400
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(0, size, 4):                       # noisy data compresses badly, so the file stays big
        for x in range(0, size, 4):
            value = (x * 7 + y * 13) % 256
            for dy in range(4):
                for dx in range(4):
                    pixels[x + dx, y + dy] = (value, (value * 3) % 256, (value * 5) % 256)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=100, subsampling=0)
    data = buffer.getvalue()
    target = megabytes * 1024 * 1024
    if len(data) < target:                            # pad with a JPEG comment marker so the size is guaranteed
        filler = b"\xff\xfe" + (target - len(data) - 2).to_bytes(2, "big")
        data = data[:2] + filler[2:len(filler)] + data[2:]
    return data


@pytest.fixture()
def flask_app(tmp_path):
    """A Flask app in Offline Demo Mode with a temporary review store."""
    application = app_module.create_app({
        "TESTING": True,
        "REVIEW_STORE_PATH": str(tmp_path / "reviews.json"),
        "MAX_CONTENT_LENGTH": app_module.MAX_REQUEST_BYTES,
    })
    app_module.ANALYSIS_STORE.clear()
    with application.app_context():
        yield application
    app_module.ANALYSIS_STORE.clear()


@pytest.fixture()
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture()
def clean_env(monkeypatch):
    """Environment with every provider credential removed (the offline case)."""
    for name in ("AI_MODE", "AI_PROVIDER", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY",
                 "GEMINI_MODEL", "ANTHROPIC_MODEL", "REQUEST_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    return os.environ


# ------------------------------------------------------------ sample data ----
@pytest.fixture(scope="session")
def sample_analysis() -> dict:
    return samples.SAMPLES["education"]["analysis"]


@pytest.fixture(scope="session")
def valid_analysis_json(sample_analysis) -> str:
    return json.dumps(sample_analysis)


@pytest.fixture(scope="session")
def cached_validator():
    return validator
