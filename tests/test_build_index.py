"""The index builder, and the installer reading what it writes."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_index = _load("build_index")
changed = _load("changed_packages")


def _entry(version: str, url: str = "x.whl") -> dict:
    return {"version": version, "url": url, "sha256": "a" * 64}


class TestMerge:
    def test_an_older_version_is_kept_and_the_new_one_added(self):
        previous = {"index_version": 1, "extensions": {"a": [_entry("0.1.0", "old.whl")]}}
        merged = build_index.merge(previous, {"a": _entry("0.2.0", "new.whl")})
        assert [e["version"] for e in merged["extensions"]["a"]] == ["0.1.0", "0.2.0"]
        assert merged["extensions"]["a"][0]["url"] == "old.whl"

    def test_the_same_version_is_replaced_by_this_run(self):
        previous = {"index_version": 1, "extensions": {"a": [_entry("0.1.0", "old.whl")]}}
        merged = build_index.merge(previous, {"a": _entry("0.1.0", "new.whl")})
        assert [e["url"] for e in merged["extensions"]["a"]] == ["new.whl"]

    def test_versions_sort_as_numbers(self):
        previous = {"index_version": 1, "extensions": {"a": [_entry("0.9.0"), _entry("0.10.0")]}}
        merged = build_index.merge(previous, {"a": _entry("0.2.0")})
        assert [e["version"] for e in merged["extensions"]["a"]] == ["0.2.0", "0.9.0", "0.10.0"]

    def test_an_extension_not_rebuilt_stays(self):
        previous = {"index_version": 1, "extensions": {"gone": [_entry("1.0.0")]}}
        merged = build_index.merge(previous, {"a": _entry("0.1.0")})
        assert sorted(merged["extensions"]) == ["a", "gone"]

    def test_with_no_previous_index(self):
        merged = build_index.merge(None, {"a": _entry("0.1.0")})
        assert merged["index_version"] == 1 and list(merged["extensions"]) == ["a"]


class TestSelect:
    ids = ["alpha", "beta", "gamma"]

    def test_a_package_change_selects_that_package(self):
        assert changed.select(["packages/beta/auth.py"], self.ids) == ["beta"]

    def test_two_packages(self):
        got = changed.select(["packages/gamma/x.py", "packages/alpha/y.py"], self.ids)
        assert got == ["alpha", "gamma"]

    def test_a_change_outside_packages_selects_all(self):
        assert changed.select(["scripts/build_index.py"], self.ids) == self.ids
        assert changed.select([".github/workflows/ci.yml"], self.ids) == self.ids

    def test_documentation_only_selects_nothing(self):
        assert changed.select(["README.md", "docs/free-tier.md", "skills/x/SKILL.md"], self.ids) == []

    def test_an_unknown_folder_is_ignored(self):
        assert changed.select(["packages/zzz/x.py"], self.ids) == []


class TestDerived:
    """Every field of an entry comes from a source file, none is written by hand."""

    def test_the_vendor_logo_is_read_from_the_wheels_provider_yaml(self, tmp_path):
        import zipfile

        wheel = tmp_path / "w.whl"
        with zipfile.ZipFile(wheel, "w") as z:
            z.writestr(
                "llm_rosetta_ext/x/provider.yaml",
                "connection:\n  base_url: https://x\nlogo: 'https://h.example/x.svg'  # mark\n"
                "lane:\n  logo: https://h.example/lane.svg\n",
            )
        assert build_index.vendor_logo(wheel, "x") == "https://h.example/x.svg"

    def test_no_logo_line_means_no_logo(self, tmp_path):
        import zipfile

        wheel = tmp_path / "w.whl"
        with zipfile.ZipFile(wheel, "w") as z:
            z.writestr("llm_rosetta_ext/x/provider.yaml", "connection:\n  base_url: https://x\n")
        assert build_index.vendor_logo(wheel, "x") is None
        with zipfile.ZipFile(tmp_path / "e.whl", "w") as z:
            z.writestr("llm_rosetta_ext/x/other.txt", "")
        assert build_index.vendor_logo(tmp_path / "e.whl", "x") is None

    @pytest.mark.parametrize(
        ("repository", "expected"),
        [
            ("Oaklight/llm-rosetta-ext-contrib", "contrib"),
            ("Oaklight/llm-rosetta-shim-argonne", "argonne"),
            ("Oaklight/Some Repo", ""),
        ],
    )
    def test_the_source_comes_from_the_repository_name(
        self, monkeypatch, repository, expected
    ):
        monkeypatch.setenv("GITHUB_REPOSITORY", repository)
        assert build_index.default_source() == expected

    def test_source_date_epoch_fixes_the_timestamp(self, monkeypatch):
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "86400")
        assert build_index.timestamp() == "1970-01-02T00:00:00Z"

    def test_the_timestamp_is_rfc3339_utc(self, monkeypatch):
        monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
        assert re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", build_index.timestamp())

    def test_the_last_commit_of_a_folder_is_a_git_sha(self):
        sha = build_index.last_commit(Path(__file__).resolve().parents[1] / "packages" / "llm7")
        assert sha is None or re.match(r"^[0-9a-f]{40}$", sha)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    assert build_index.main(["--relative", "--out", str(out), "llm7", "moonshot"]) == 0
    return out


class TestBuilt:
    def test_the_index_lists_each_wheel_with_its_digest(self, built):
        document = json.loads((built / "index.json").read_text())
        assert sorted(document["extensions"]) == ["llm7", "moonshot"]
        for entries in document["extensions"].values():
            (entry,) = entries
            wheel = built / entry["url"]
            assert hashlib.sha256(wheel.read_bytes()).hexdigest() == entry["sha256"]
            assert entry["requires_python"] == ">=3.10"

    def test_the_installer_reads_the_index_and_installs_from_it(self, built, tmp_path):
        from llm_rosetta.extensions import install_from_index, load_index

        index = load_index(str(built / "index.json"))
        done = install_from_index("llm7", index, dest=tmp_path)
        assert [item.id for item in done] == ["llm7"]
        assert (tmp_path / "llm_rosetta_ext" / "llm7" / "plugin.yaml").is_file()

    def test_a_base_url_makes_absolute_urls(self, tmp_path):
        out = tmp_path / "dist"
        code = build_index.main(
            ["--base-url", "https://h.example/r/t1/", "--out", str(out), "llm7"]
        )
        assert code == 0
        url = json.loads((out / "index.json").read_text())["extensions"]["llm7"][0]["url"]
        assert url.startswith("https://h.example/r/t1/llm_rosetta_ext_llm7-")

    def test_previous_versions_are_carried_forward(self, built, tmp_path):
        out = tmp_path / "dist"
        code = build_index.main(
            ["--relative", "--out", str(out), "--previous", str(built / "index.json"), "llm7"]
        )
        assert code == 0
        document = json.loads((out / "index.json").read_text())
        assert sorted(document["extensions"]) == ["llm7", "moonshot"]


class TestListingFields:
    def test_an_entry_carries_what_a_listing_shows(self, built):
        """Compare with the source files, read here by a different route."""
        from llm_rosetta._vendor.yaml import load
        from llm_rosetta.contracts.extension import parse_extension_manifest

        document = json.loads((built / "index.json").read_text())
        for ext_id in ("moonshot", "llm7"):
            folder = Path(__file__).resolve().parents[1] / "packages" / ext_id
            manifest = parse_extension_manifest(
                load((folder / "plugin.yaml").read_text(encoding="utf-8"))
            )
            (entry,) = document["extensions"][ext_id]
            assert entry["name"] == manifest.name
            assert entry["maturity"] == manifest.maturity
            assert entry["tags"] == list(manifest.tags) and entry["tags"]
            assert entry["shims"] == list(manifest.shims)
            vendor = load((folder / "provider.yaml").read_text(encoding="utf-8")) or {}
            assert entry.get("logo") == vendor.get("logo")
            assert re.match(r"^[0-9a-f]{40}$", entry.get("commit", "0" * 40))

    def test_a_vendor_with_a_logo_gets_one(self, built):
        document = json.loads((built / "index.json").read_text())
        assert document["extensions"]["moonshot"][0]["logo"].startswith("https://")

    def test_the_header_names_the_source_and_the_time(self, built):
        document = json.loads((built / "index.json").read_text())
        assert document["source"] and re.match(r"^\d{4}-", document["generated_at"])

    def test_the_core_parser_reads_every_field(self, built):
        from llm_rosetta.extensions import load_index

        index = load_index(str(built / "index.json"))
        entry = index["moonshot"][0]
        assert entry.name and entry.shims == ("moonshot",) and entry.maturity
        assert index.generated_at.endswith("Z") and index.source

    def test_the_dropped_fields_are_not_written(self, built):
        document = json.loads((built / "index.json").read_text())
        dropped = {"archive", "repo", "conformance", "promoted_to", "since"}
        assert not dropped & set(document)
        for entries in document["extensions"].values():
            assert not dropped & set(entries[0])

    def test_merge_writes_the_header_when_given(self):
        merged = build_index.merge(
            None, {"a": _entry("0.1.0")}, source="contrib", generated_at="2026-11-26T00:00:00Z"
        )
        assert (merged["source"], merged["generated_at"]) == ("contrib", "2026-11-26T00:00:00Z")
        assert "source" not in build_index.merge(None, {"a": _entry("0.1.0")})
