import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import requests


SUPPORTED_SPEC_EXTENSIONS = {".md", ".mediawiki", ".rst"}


@dataclass(frozen=True)
class SpecSource:
    """Canonical source repository for BIP/BOLT specification files."""

    spec_type: str
    owner: str
    repo: str
    branch: str
    path_template: str
    source_base_url: str

    @property
    def repository(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass(frozen=True)
class RawSpec:
    """Normalized raw spec record produced by source sync."""

    spec_id: str
    spec_type: str
    number: int
    raw_text: str
    source_url: str
    source_path: str
    source_repository: str
    commit_hash: Optional[str]
    content_hash: str
    fetched_at: str

    def to_dict(self) -> dict:
        return {
            "spec_id": self.spec_id,
            "spec_type": self.spec_type,
            "number": self.number,
            "raw_text": self.raw_text,
            "source_url": self.source_url,
            "source_path": self.source_path,
            "source_repository": self.source_repository,
            "commit_hash": self.commit_hash,
            "content_hash": self.content_hash,
            "fetched_at": self.fetched_at,
        }


@dataclass(frozen=True)
class SpecRef:
    """A requested specification identifier."""

    spec_type: str
    number: int

    @property
    def spec_id(self) -> str:
        return f"{self.spec_type.upper()}-{self.number}"


BIP_SOURCE = SpecSource(
    spec_type="bip",
    owner="bitcoin",
    repo="bips",
    branch="master",
    path_template="bip-{number:04d}.mediawiki",
    source_base_url="https://github.com/bitcoin/bips/blob/{commit}/{path}",
)

BOLT_SOURCE = SpecSource(
    spec_type="bolt",
    owner="lightning",
    repo="bolts",
    branch="master",
    path_template="{number:02d}-{name}.md",
    source_base_url="https://github.com/lightning/bolts/blob/{commit}/{path}",
)


DEFAULT_SPEC_SOURCES = {
    "bip": BIP_SOURCE,
    "bolt": BOLT_SOURCE,
}


DEFAULT_SPEC_ALLOWLIST = (
    SpecRef("bip", 32),
    SpecRef("bip", 174),
    SpecRef("bip", 340),
    SpecRef("bip", 341),
    SpecRef("bip", 342),
    SpecRef("bolt", 11),
    SpecRef("bolt", 12),
)


class SpecSyncError(Exception):
    """Raised when a specification cannot be synced."""


class SpecSyncService:
    """Fetch BIP/BOLT specification files into normalized raw records."""

    def __init__(
        self,
        sources: Optional[dict[str, SpecSource]] = None,
        session: Optional[requests.Session] = None,
    ):
        self.sources = sources or DEFAULT_SPEC_SOURCES
        self.session = session or requests.Session()

    def sync_allowlist(
        self, specs: Iterable[SpecRef] = DEFAULT_SPEC_ALLOWLIST
    ) -> list[RawSpec]:
        return [self.sync_spec(spec) for spec in specs]

    def sync_spec(self, spec: SpecRef | str) -> RawSpec:
        spec_ref = self.parse_spec_ref(spec) if isinstance(spec, str) else spec
        if spec_ref is None:
            raise SpecSyncError(f"Could not parse spec id: {spec}")
        source = self._get_source(spec_ref.spec_type)
        commit_hash = self.get_branch_commit(source)
        source_path = self.resolve_source_path(source, spec_ref.number)
        raw_text = self.fetch_raw_text(source, source_path, commit_hash)

        return self._build_raw_spec(
            spec_ref=spec_ref,
            source=source,
            raw_text=raw_text,
            source_path=source_path,
            commit_hash=commit_hash,
        )

    def sync_local_directory(self, directory: str | Path) -> list[RawSpec]:
        root = Path(directory)
        if not root.exists():
            raise SpecSyncError(f"Spec directory does not exist: {root}")

        specs = []
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in SUPPORTED_SPEC_EXTENSIONS:
                continue
            spec_ref = self.parse_spec_ref(path.name)
            if spec_ref is None:
                continue
            raw_text = path.read_text(encoding="utf-8")
            specs.append(self._build_local_raw_spec(spec_ref, path, raw_text))
        return specs

    def get_branch_commit(self, source: SpecSource) -> str:
        url = (
            f"https://api.github.com/repos/{source.owner}/{source.repo}"
            f"/commits/{source.branch}"
        )
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()["sha"]

    def resolve_source_path(self, source: SpecSource, number: int) -> str:
        if source.spec_type == "bolt":
            return self._resolve_bolt_path(source, number)
        return source.path_template.format(number=number)

    def fetch_raw_text(
        self, source: SpecSource, source_path: str, commit_hash: str
    ) -> str:
        url = (
            f"https://raw.githubusercontent.com/{source.owner}/{source.repo}"
            f"/{commit_hash}/{source_path}"
        )
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    @staticmethod
    def parse_spec_ref(value: str) -> Optional[SpecRef]:
        normalized = value.lower()

        bip_match = re.search(r"\bbip[-_\s]?0*(\d{1,4})\b", normalized)
        if bip_match:
            return SpecRef("bip", int(bip_match.group(1)))

        bolt_match = re.search(r"\bbolt[-_\s]?0*(\d{1,3})\b", normalized)
        if bolt_match:
            return SpecRef("bolt", int(bolt_match.group(1)))

        bip_file_match = re.search(r"\bbip-0*(\d{1,4})\.", normalized)
        if bip_file_match:
            return SpecRef("bip", int(bip_file_match.group(1)))

        bolt_file_match = re.search(r"\b0*(\d{1,3})-[a-z0-9_-]+\.", normalized)
        if bolt_file_match:
            return SpecRef("bolt", int(bolt_file_match.group(1)))

        return None

    def _resolve_bolt_path(self, source: SpecSource, number: int) -> str:
        tree_url = (
            f"https://api.github.com/repos/{source.owner}/{source.repo}"
            f"/git/trees/{source.branch}"
        )
        response = self.session.get(tree_url, timeout=30)
        response.raise_for_status()

        prefix = f"{number:02d}-"
        for item in response.json().get("tree", []):
            path = item.get("path", "")
            if path.startswith(prefix) and path.endswith(".md"):
                return path

        raise SpecSyncError(
            f"Could not find BOLT-{number} in {source.repository}"
        )

    def _build_raw_spec(
        self,
        spec_ref: SpecRef,
        source: SpecSource,
        raw_text: str,
        source_path: str,
        commit_hash: Optional[str],
    ) -> RawSpec:
        resolved_commit = commit_hash or "local"
        source_url = source.source_base_url.format(
            commit=resolved_commit,
            path=source_path,
        )
        return RawSpec(
            spec_id=spec_ref.spec_id,
            spec_type=spec_ref.spec_type,
            number=spec_ref.number,
            raw_text=raw_text,
            source_url=source_url,
            source_path=source_path,
            source_repository=source.repository,
            commit_hash=commit_hash,
            content_hash=self._content_hash(raw_text),
            fetched_at=self._utc_now(),
        )

    def _build_local_raw_spec(
        self, spec_ref: SpecRef, path: Path, raw_text: str
    ) -> RawSpec:
        return RawSpec(
            spec_id=spec_ref.spec_id,
            spec_type=spec_ref.spec_type,
            number=spec_ref.number,
            raw_text=raw_text,
            source_url=path.resolve().as_uri(),
            source_path=str(path),
            source_repository="local",
            commit_hash=None,
            content_hash=self._content_hash(raw_text),
            fetched_at=self._utc_now(),
        )

    def _get_source(self, spec_type: str) -> SpecSource:
        try:
            return self.sources[spec_type]
        except KeyError:
            raise SpecSyncError(f"Unsupported spec type: {spec_type}")

    @staticmethod
    def _content_hash(raw_text: str) -> str:
        return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()
