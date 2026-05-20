"""Runtime configuration for the changjuan pipeline.

Single source of truth for paths, batch sizes, and tunable constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    repo_root: Path = field(default_factory=_default_repo_root)
    chunk_target_chars: int = 1800
    chunk_overlap_chars: int = 200

    @property
    def data_dir(self) -> Path:
        return self.repo_root / "data"

    @property
    def corpus_db(self) -> Path:
        return self.data_dir / "corpus.sqlite"

    @property
    def canonical_db(self) -> Path:
        return self.data_dir / "changjuan.sqlite"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def corpora_dir(self) -> Path:
        return self.repo_root / "corpora"
