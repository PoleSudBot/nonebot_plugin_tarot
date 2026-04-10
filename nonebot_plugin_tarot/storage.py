import re
from datetime import datetime
from pathlib import Path

from .config import PLUGIN_AI_RESULT_DIR, ensure_plugin_data_layout, tarot_config

_SAFE_PATH_PART_RE = re.compile(r"[^0-9A-Za-z_.-]+")


def _sanitize_path_part(value: str) -> str:
    sanitized = _SAFE_PATH_PART_RE.sub("-", value.strip()).strip("-")
    return sanitized or "unknown"


def save_tarot_resource(
    image_bytes: bytes,
    *,
    theme: str,
    card_type: str,
    image_name: str,
    extension: str,
) -> Path:
    ensure_plugin_data_layout()
    save_dir = tarot_config.tarot_path / theme / card_type
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{image_name}.{extension.lower()}"
    save_path.write_bytes(image_bytes)
    return save_path


def save_ai_result_image(
    image_bytes: bytes,
    *,
    user_id: str,
    platform: str,
) -> Path:
    ensure_plugin_data_layout()
    now = datetime.now()
    save_dir = PLUGIN_AI_RESULT_DIR / now.strftime("%Y-%m-%d")
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / (
        f"{now.strftime('%Y%m%d-%H%M%S-%f')}_"
        f"{_sanitize_path_part(platform)}_"
        f"{_sanitize_path_part(user_id)}.png"
    )
    save_path.write_bytes(image_bytes)
    return save_path
