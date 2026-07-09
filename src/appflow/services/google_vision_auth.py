import base64
import os
import tempfile


def configure_google_vision_credentials() -> str | None:
    """Configure Google Vision credentials from env or the bundled local file."""
    if os.getenv("GOOGLE_VISION_USE_ADC", "").strip().lower() in ("1", "true", "yes"):
        return None

    existing_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if existing_path:
        return existing_path

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

    default_path = os.path.join(
        os.path.dirname(__file__),
        "google_credentials",
        "vision-service-account.json",
    )
    if os.path.exists(default_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = default_path
        return default_path

    return None
