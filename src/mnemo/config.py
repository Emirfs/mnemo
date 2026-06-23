"""Configuration — vault location + derived index path."""

from __future__ import annotations

import os
from pathlib import Path

INDEX_REL = Path(".mnemo") / "index.sqlite"


class Config:
    """Resolves where the vault lives and where the derived index goes.

    Vault resolution order: explicit arg → $MNEMO_VAULT → current directory.
    The index always lives at ``<vault>/.mnemo/index.sqlite`` (gitignored).
    """

    def __init__(self, vault: str | Path | None = None):
        self.vault = self._resolve_vault(vault)
        self.index_path = self.vault / INDEX_REL

    @staticmethod
    def _resolve_vault(vault: str | Path | None) -> Path:
        if vault:
            return Path(vault).expanduser().resolve()
        env = os.environ.get("MNEMO_VAULT")
        if env:
            return Path(env).expanduser().resolve()
        return Path.cwd().resolve()

    def ensure_dirs(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
