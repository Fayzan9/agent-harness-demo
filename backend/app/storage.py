"""Where files live. One small interface, so the rest of the app never knows if it is a folder or a bucket.

A key is a string like "users/alice/workspace/notes.txt". The "/" only looks like folders (S3 calls it a prefix).
Values are bytes: storage does not care whether a file is text.
"""
import os
from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def list(self, prefix: str) -> list[str]:
        """Every key that starts with prefix, sorted."""

    def read(self, key: str) -> bytes:
        """The bytes stored under key. Raises FileNotFoundError when there is nothing."""

    def write(self, key: str, data: bytes) -> None:
        """Store data under key, replacing what was there. All of it is stored, or none."""

    def delete(self, key: str) -> None:
        """Remove key. Removing something that is not there is fine."""


def check_key(key: str) -> str:
    """Refuse keys that could point outside where they belong. Every backend calls this first."""
    parts = key.split("/")
    if not key or key.startswith("/") or "\\" in key or "\x00" in key or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"Not a valid storage key: {key!r}")
    return key


class LocalStorage:
    """Keys are paths under one root folder. For a laptop and for tests."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / check_key(key)).resolve()
        if not path.is_relative_to(self.root):  # a second lock: even a tricky key cannot leave the root
            raise ValueError(f"Not a valid storage key: {key!r}")
        return path

    def list(self, prefix: str) -> list[str]:
        keys = (p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file() and not p.name.endswith(".tmp"))
        return sorted(k for k in keys if k.startswith(prefix))

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)  # all or nothing, like an object upload

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
