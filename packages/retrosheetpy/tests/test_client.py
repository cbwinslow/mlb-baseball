import io
import zipfile
from datetime import UTC

import pytest
from retrosheetpy import (
    Client,
    IntegrityError,
    InvalidArchiveError,
    Product,
    UnsafeArchiveMemberError,
    iter_zip_members,
    resolve,
)


def make_zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


class FakeFetch:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        return self.payload


RES = resolve(Product.YEARLY_CSV, season=1950)


def test_download_returns_artifact_metadata(tmp_path):
    payload = make_zip({"1950plays.csv": b"a,b\n"})
    client = Client(tmp_path, fetch=FakeFetch(payload))
    art = client.download(RES)
    assert art.source_url == RES.url
    assert art.product is Product.YEARLY_CSV and art.season == 1950
    assert art.size == len(payload) and len(art.sha256) == 64
    assert art.local_path.read_bytes() == payload
    assert art.retrieved_at.tzinfo is UTC


def test_cached_source_is_reused_without_second_fetch(tmp_path):
    fetch = FakeFetch(make_zip({"x.csv": b"1"}))
    client = Client(tmp_path, fetch=fetch)
    first = client.download(RES)
    second = Client(tmp_path, fetch=fetch).download(RES)
    assert len(fetch.calls) == 1
    assert second == first


def test_modified_cache_is_refetched_with_new_metadata(tmp_path):
    fetch = FakeFetch(make_zip({"x.csv": b"1"}))
    client = Client(tmp_path, fetch=fetch)
    first = client.download(RES)
    first.local_path.write_bytes(b"tampered")
    second = client.download(RES)
    assert len(fetch.calls) == 2
    assert second.sha256 == first.sha256
    assert second.local_path.read_bytes() == fetch.payload


def test_modified_cache_fails_when_refetch_disabled(tmp_path):
    fetch = FakeFetch(make_zip({"x.csv": b"1"}))
    client = Client(tmp_path, fetch=fetch)
    art = client.download(RES)
    art.local_path.write_bytes(b"tampered")
    with pytest.raises(IntegrityError):
        client.download(RES, refetch_on_mismatch=False)


def test_changed_upstream_bytes_return_new_metadata_not_silent_overwrite(tmp_path):
    fetch = FakeFetch(make_zip({"x.csv": b"1"}))
    client = Client(tmp_path, fetch=fetch)
    first = client.download(RES)
    fetch.payload = make_zip({"x.csv": b"2"})
    second = client.download(RES, force=True)
    assert second.sha256 != first.sha256


def test_non_zip_response_rejected_and_not_cached(tmp_path):
    client = Client(tmp_path, fetch=FakeFetch(b"<html>404</html>"))
    with pytest.raises(InvalidArchiveError):
        client.download(RES)
    assert not list(tmp_path.rglob("*.zip"))


def test_plain_text_product_is_not_zip_checked(tmp_path):
    client = Client(tmp_path, fetch=FakeFetch(b"ATL,NL\n"))
    art = client.download(resolve(Product.TEAM_ABBREVIATIONS))
    assert art.local_path.read_bytes() == b"ATL,NL\n"


def test_iter_zip_members(tmp_path):
    client = Client(tmp_path, fetch=FakeFetch(make_zip({"a.csv": b"1", "b.csv": b"22"})))
    art = client.download(RES)
    got = {name: f.read() for name, f in iter_zip_members(art.local_path)}
    assert got == {"a.csv": b"1", "b.csv": b"22"}


@pytest.mark.parametrize("bad", ["../evil.csv", "/abs.csv", "a/../../b.csv", "a\\..\\b.csv"])
def test_zip_path_traversal_rejected(tmp_path, bad):
    p = tmp_path / "t.zip"
    p.write_bytes(make_zip({bad: b"x"}))
    with pytest.raises(UnsafeArchiveMemberError):
        list(iter_zip_members(p))


def test_corrupt_zip_rejected(tmp_path):
    p = tmp_path / "t.zip"
    p.write_bytes(b"PK\x03\x04garbage")
    with pytest.raises(InvalidArchiveError):
        list(iter_zip_members(p))


def test_unreadable_cache_metadata_is_not_trusted(tmp_path):
    fetch = FakeFetch(make_zip({"x.csv": b"1"}))
    client = Client(tmp_path, fetch=fetch)
    art = client.download(RES)
    art.local_path.with_name(art.local_path.name + ".json").write_text("{not json")
    client.download(RES)
    assert len(fetch.calls) == 2
    with pytest.raises(IntegrityError):
        art.local_path.with_name(art.local_path.name + ".json").write_text("{}")
        client.download(RES, refetch_on_mismatch=False)


def test_cache_for_different_seasons_does_not_collide(tmp_path):
    fetch = FakeFetch(make_zip({"x.csv": b"1"}))
    client = Client(tmp_path, fetch=fetch)
    a = client.download(resolve(Product.YEARLY_CSV, season=1950))
    b = client.download(resolve(Product.YEARLY_CSV, season=1951))
    assert a.local_path != b.local_path and len(fetch.calls) == 2
