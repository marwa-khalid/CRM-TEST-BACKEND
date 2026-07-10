import base64
import json
import os
import tempfile
import urllib.error
import urllib.request


def configure_google_vision_credentials() -> str | None:
    """Configure Google Vision credentials from env or the bundled local file."""
    if os.getenv("GOOGLE_VISION_USE_ADC", "").strip().lower() in ("1", "true", "yes"):
        return None

    # Explicit secrets win first (this is how Railway should carry the key: you
    # can't drop a JSON file into the container, so set GOOGLE_VISION_CREDENTIALS_B64).
    credentials_b64 = os.getenv("GOOGLE_VISION_CREDENTIALS_B64", "").strip()
    if credentials_b64:
        credentials_json = base64.b64decode(credentials_b64).decode("utf-8")
        fd, path = tempfile.mkstemp(prefix="google-vision-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(credentials_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        return path

    credentials_json = os.getenv("GOOGLE_VISION_CREDENTIALS_JSON", "").strip()
    if credentials_json:
        fd, path = tempfile.mkstemp(prefix="google-vision-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(credentials_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        return path

    # Only honour an existing GOOGLE_APPLICATION_CREDENTIALS if the file actually
    # exists — a stale path must not short-circuit past the bundled key.
    existing_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if existing_path and os.path.exists(existing_path):
        return existing_path

    default_path = os.path.join(
        os.path.dirname(__file__),
        "google_credentials",
        "vision-service-account.json",
    )
    if os.path.exists(default_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = default_path
        return default_path

    return None


def ocr_image_with_api_key(image_path: str) -> str | None:
    """OCR a single image via the Vision REST API using a plain API key.

    Reads GOOGLE_VISION_API_KEY. An API key is a *different* resource from a
    service-account key, so it works even when the org policy
    `iam.disableServiceAccountKeyCreation` blocks SA-key creation.

    Returns the extracted text on success, or None when the key isn't set or the
    call fails — callers then fall back to the client library / local OCR, so
    OCR never hard-breaks.
    """
    api_key = os.getenv("GOOGLE_VISION_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        with open(image_path, "rb") as handle:
            content_b64 = base64.b64encode(handle.read()).decode("ascii")
        body = json.dumps(
            {
                "requests": [
                    {
                        "image": {"content": content_b64},
                        # DOCUMENT_TEXT_DETECTION reads dense forms (like the V5C)
                        # better than plain TEXT_DETECTION.
                        "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                    }
                ]
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"https://vision.googleapis.com/v1/images:annotate?key={api_key}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = (data.get("responses") or [{}])[0]
        err = result.get("error") or {}
        if err.get("message"):
            raise RuntimeError(err["message"])
        full = (result.get("fullTextAnnotation") or {}).get("text")
        if full:
            return full
        annotations = result.get("textAnnotations") or []
        if annotations:
            return annotations[0].get("description", "")
        return ""
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Surface the API's own error body when available (helps diagnose a bad key).
        detail = str(exc)
        if isinstance(exc, urllib.error.HTTPError):
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        print(f"Warning: Vision API-key OCR failed for {image_path}: {detail}")
        return None
