"""Import generated main visuals into a request queue with hashes and dimensions."""

from __future__ import annotations

import hashlib
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class VisualImportError(ValueError):
    """Raised when a generated visual cannot be safely bound to a request."""


SENSITIVE_PATTERN = re.compile(
    r"(?i)(authorization|bearer|api[_ -]?key|token|cookie|session|password|secret)"
)
SUPPORTED_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def _relative(path: Path) -> str:
    root = Path(__file__).resolve().parents[1]
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _find_result(
    result_dir: Path,
    *,
    request_id: str,
    item_id: str,
    attempt: int,
) -> Path | None:
    stems = [request_id]
    if attempt == 1:
        stems.append(item_id)
    for stem in stems:
        for suffix in SUPPORTED_SUFFIXES:
            candidate = result_dir / f"{stem}{suffix}"
            if candidate.is_file():
                return candidate
    return None


def _image_metadata(path: Path) -> tuple[int, int, str]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise VisualImportError("缺少Pillow，无法核验主视觉尺寸") from exc

    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            image_format = str(image.format or "").upper()
    except Exception as exc:
        raise VisualImportError(f"主视觉无法读取：{path}：{exc}") from exc

    mime = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "WEBP": "image/webp",
    }.get(image_format)
    if mime is None:
        guessed, _ = mimetypes.guess_type(path.name)
        if guessed not in {"image/png", "image/jpeg", "image/webp"}:
            raise VisualImportError(f"不支持的主视觉格式：{path}")
        mime = guessed
    return width, height, mime


def import_visual_results(
    *,
    request_queue: Mapping[str, Any],
    result_dir: Path,
    generator_reference: str,
    imported_at: str | None = None,
    require_all: bool = True,
    replace_existing: bool = False,
) -> dict[str, Any]:
    """Return a copied request queue with matched result files attached."""
    reference = str(generator_reference).strip()
    if not reference:
        raise VisualImportError("generator_reference不能为空")
    if SENSITIVE_PATTERN.search(reference):
        raise VisualImportError("generator_reference疑似包含凭据或私密信息")
    if len(reference) > 300:
        raise VisualImportError("generator_reference过长")

    result_dir = result_dir.resolve()
    if not result_dir.is_dir():
        raise VisualImportError(f"结果目录不存在：{result_dir}")
    imported_at = imported_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    output: dict[str, Any] = {
        key: value for key, value in request_queue.items() if key != "requests"
    }
    requests: list[dict[str, Any]] = []
    missing: list[str] = []

    for original in request_queue.get("requests", []):
        request = dict(original)
        existing = request.get("result")
        if existing is not None and not replace_existing:
            requests.append(request)
            continue

        path = _find_result(
            result_dir,
            request_id=str(request["request_id"]),
            item_id=str(request["item_id"]),
            attempt=int(request["attempt"]),
        )
        if path is None:
            missing.append(str(request["request_id"]))
            requests.append(request)
            continue

        width, height, mime = _image_metadata(path)
        target = request["target"]
        if width != int(target["width"]) or height != int(target["height"]):
            raise VisualImportError(
                f"主视觉尺寸不一致：{path.name} 实际{width}×{height}，"
                f"要求{target['width']}×{target['height']}"
            )
        expected_mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "webp": "image/webp",
        }[str(target["format"])]
        if mime != expected_mime:
            raise VisualImportError(
                f"主视觉格式不一致：{path.name} 实际{mime}，要求{expected_mime}"
            )

        body = path.read_bytes()
        request["result"] = {
            "path": _relative(path),
            "sha256": hashlib.sha256(body).hexdigest(),
            "byte_size": len(body),
            "width": width,
            "height": height,
            "mime_type": mime,
            "imported_at": imported_at,
            "generator_reference": reference,
        }
        request["status"] = "imported"
        requests.append(request)

    if require_all and missing:
        raise VisualImportError("缺少主视觉结果：" + ", ".join(sorted(missing)))
    if not any(request.get("result") is not None for request in requests):
        raise VisualImportError("没有导入任何主视觉结果")

    output["requests"] = requests
    return output
