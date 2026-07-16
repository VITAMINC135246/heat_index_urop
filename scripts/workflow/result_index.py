"""Lightweight compatibility index for canonical per-image results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .models import CANONICAL_SCHEMA_VERSION, PROCESSING_VERSION, CanonicalManifest, QAStatus, ProcessingStatus


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def configuration_hash(configuration: dict[str, Any]) -> str:
    payload = json.dumps(configuration, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class CacheCheck:
    compatible: bool
    reason: str
    manifest_path: str = ""


class ResultIndex:
    def __init__(self, path: Path):
        self.path = path
        self.payload: dict[str, Any] = {"index_version": 1, "results": {}}
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("results"), dict):
                self.payload = loaded

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)

    def register(self, manifest_path: Path, manifest: CanonicalManifest) -> None:
        self.payload["results"][manifest.image_id] = {
            "manifest_path": manifest_path.resolve().as_posix(),
            "schema_version": manifest.schema_version,
            "processing_version": manifest.processing_version,
            "configuration_hash": manifest.configuration_hash,
            "source_file_hashes": manifest.source_file_hashes,
            "qa_status": manifest.qa_status.value,
            "processing_status": manifest.processing_status.value,
        }

    def check(
        self,
        image_id: str,
        *,
        source_file_hashes: dict[str, str],
        configuration_hash_value: str,
        schema_version: str = CANONICAL_SCHEMA_VERSION,
        processing_version: str = PROCESSING_VERSION,
    ) -> CacheCheck:
        entry = self.payload["results"].get(image_id)
        if not entry:
            return CacheCheck(False, "not_indexed")
        if entry.get("schema_version") != schema_version:
            return CacheCheck(False, "schema_version_mismatch")
        if entry.get("processing_version") != processing_version:
            return CacheCheck(False, "processing_version_mismatch")
        if entry.get("configuration_hash") != configuration_hash_value:
            return CacheCheck(False, "configuration_hash_mismatch")
        if entry.get("source_file_hashes") != source_file_hashes:
            return CacheCheck(False, "source_file_hash_mismatch")
        if entry.get("qa_status") == QAStatus.FAIL.value:
            return CacheCheck(False, "qa_failed")
        if entry.get("processing_status") != ProcessingStatus.SUCCESS.value:
            return CacheCheck(False, "result_not_successful")
        manifest_path = Path(str(entry.get("manifest_path", "")))
        if not manifest_path.is_file():
            return CacheCheck(False, "manifest_missing")
        try:
            manifest = CanonicalManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
            manifest.validate()
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            return CacheCheck(False, f"manifest_invalid:{type(exc).__name__}")
        for artifact in manifest.artifacts.values():
            artifact_path = Path(artifact.path)
            if not artifact_path.is_absolute():
                artifact_path = manifest_path.parent / artifact_path
            if not artifact_path.is_file():
                return CacheCheck(False, f"artifact_missing:{artifact.path}")
        return CacheCheck(True, "compatible", manifest_path.resolve().as_posix())


def source_hashes(paths: Iterable[Path]) -> dict[str, str]:
    return {path.resolve().as_posix(): sha256_file(path) for path in paths if path.is_file()}
