import hashlib

import pytest

from app.spec_sync import (
    DEFAULT_SPEC_ALLOWLIST,
    RawSpec,
    SpecRef,
    SpecSyncError,
    SpecSyncService,
)


class FakeResponse:
    def __init__(self, json_data=None, text="", status_code=200):
        self._json_data = json_data or {}
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self):
        self.urls = []

    def get(self, url, timeout):
        self.urls.append((url, timeout))
        if "/commits/master" in url:
            return FakeResponse({"sha": "abc123"})
        if "/git/trees/master" in url:
            return FakeResponse(
                {
                    "tree": [
                        {"path": "01-messaging.md"},
                        {"path": "11-payment-encoding.md"},
                        {"path": "12-offer-encoding.md"},
                    ]
                }
            )
        if "raw.githubusercontent.com" in url:
            return FakeResponse(text="Specification body")
        raise AssertionError(f"Unexpected URL: {url}")


def test_default_allowlist_contains_initial_mvp_specs():
    assert [spec.spec_id for spec in DEFAULT_SPEC_ALLOWLIST] == [
        "BIP-32",
        "BIP-174",
        "BIP-340",
        "BIP-341",
        "BIP-342",
        "BOLT-11",
        "BOLT-12",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("BIP-341", SpecRef("bip", 341)),
        ("bip0340", SpecRef("bip", 340)),
        ("bip-0174.mediawiki", SpecRef("bip", 174)),
        ("BOLT 12", SpecRef("bolt", 12)),
        ("11-payment-encoding.md", SpecRef("bolt", 11)),
    ],
)
def test_parse_spec_ref(value, expected):
    assert SpecSyncService.parse_spec_ref(value) == expected


def test_sync_spec_fetches_and_normalizes_bip():
    service = SpecSyncService(session=FakeSession())

    spec = service.sync_spec("BIP-341")

    assert isinstance(spec, RawSpec)
    assert spec.spec_id == "BIP-341"
    assert spec.spec_type == "bip"
    assert spec.number == 341
    assert spec.raw_text == "Specification body"
    assert spec.source_path == "bip-0341.mediawiki"
    assert spec.source_repository == "bitcoin/bips"
    assert spec.commit_hash == "abc123"
    assert spec.content_hash == hashlib.sha256(
        b"Specification body"
    ).hexdigest()
    assert spec.source_url == (
        "https://github.com/bitcoin/bips/blob/abc123/bip-0341.mediawiki"
    )


def test_sync_spec_discovers_bolt_path_from_repo_tree():
    service = SpecSyncService(session=FakeSession())

    spec = service.sync_spec("BOLT-11")

    assert spec.spec_id == "BOLT-11"
    assert spec.source_path == "11-payment-encoding.md"
    assert spec.source_repository == "lightning/bolts"
    assert spec.source_url == (
        "https://github.com/lightning/bolts/blob/abc123/"
        "11-payment-encoding.md"
    )


def test_sync_spec_rejects_unknown_spec_id():
    service = SpecSyncService(session=FakeSession())

    with pytest.raises(SpecSyncError):
        service.sync_spec("not-a-spec")


def test_sync_local_directory_discovers_supported_specs(tmp_path):
    (tmp_path / "bip-0340.mediawiki").write_text(
        "BIP 340 body", encoding="utf-8"
    )
    (tmp_path / "12-offer-encoding.md").write_text(
        "BOLT 12 body", encoding="utf-8"
    )
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

    specs = SpecSyncService().sync_local_directory(tmp_path)

    assert [spec.spec_id for spec in specs] == ["BOLT-12", "BIP-340"]
    assert {spec.source_repository for spec in specs} == {"local"}
    assert all(spec.commit_hash is None for spec in specs)
    assert all(spec.source_url.startswith("file:///") for spec in specs)


def test_sync_local_directory_rejects_missing_path(tmp_path):
    missing = tmp_path / "missing"

    with pytest.raises(SpecSyncError):
        SpecSyncService().sync_local_directory(missing)
