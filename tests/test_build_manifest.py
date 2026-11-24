"""The manifest producer: archives, records, append-only history, validation.

``scripts/build_shim_archive.py`` and ``scripts/build_manifest.py`` are the
same builder the argonne repository publishes with (only the package, source
and repository constants differ), so both repositories write one format.
"""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
import textwrap
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
_COMMIT = "0" * 40
_STAMP = "2026-11-21T00:00:00Z"


def _module(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


archives = _module("build_shim_archive")
builder = _module("build_manifest")
collisions = _module("check_core_collisions")

needs_tomllib = pytest.mark.skipif(
    sys.version_info < (3, 11), reason="the builder reads vendors.toml with tomllib"
)

VENDORS = archives.vendors(_ROOT)
FREE = ["kilo_free", "llm7", "opencode_zen_free", "ovhcloud"]


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    """A copy of the package tree and vendors.toml, safe to edit."""
    root = tmp_path / "repo"
    shutil.copytree(
        _ROOT / "src",
        root / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
    )
    shutil.copy(_ROOT / "vendors.toml", root / "vendors.toml")
    return root


def _build(root: Path = _ROOT, previous=None):
    return builder.build_manifest(
        root, previous=previous, commit=_COMMIT, generated_at=_STAMP
    )


@needs_tomllib
def test_the_repository_builds_a_valid_manifest():
    manifest, added = _build()
    assert builder.validate_manifest(manifest) == []
    assert manifest["source"] == "contrib"
    assert manifest["repo"] == "https://github.com/Oaklight/llm-rosetta-shim-contrib"
    assert sorted(manifest["vendors"]) == VENDORS
    for vendor, entry in manifest["vendors"].items():
        (record,) = entry["versions"]
        assert record["requires"] == {"surface": 1, "ir": 1}
        assert record["archive"] == f"{record['version']}/{vendor}.tar.gz"
        assert record["sha256"] == archives.sha256_hex(added[record["archive"]])
        assert record["shims"] == [n for n, _ in archives.declared_shims(vendor, _ROOT)]
        assert record["conformance"] == {"date": None, "result": "none"}
        assert record["promoted_to"] is None


@needs_tomllib
def test_tags_and_maturity_come_from_vendors_toml():
    vendors = _build()[0]["vendors"]
    for free in FREE:
        assert vendors[free]["versions"][0]["tags"] == ["tier:free"]
    assert vendors["opendesign"]["versions"][0]["tags"] == [
        "tier:subscription",
        "auth:device",
    ]
    # The model makers' own APIs moved from core are the promotion candidates
    # (Oaklight/llm-rosetta#1660, "Placement"); everything else is beta.
    stable = {v for v, e in vendors.items() if e["versions"][0]["maturity"] == "stable"}
    assert stable == {
        "moonshot",
        "qwen",
        "volcengine",
        "xai",
        "zai",
        "zhipu",
    }
    # Experimental is a real state, not a synonym for beta: name the vendors
    # on it, so a silent downgrade or a promotion fails here.
    experimental = {
        v for v, e in vendors.items() if e["versions"][0]["maturity"] == "experimental"
    }
    assert experimental == {"claude"}
    assert {
        e["versions"][0]["maturity"] for v, e in vendors.items() if v not in stable
    } == {"beta", "experimental"}
    assert vendors["openai_chatgpt"]["versions"][0]["tags"] == [
        "tier:subscription",
        "auth:oauth",
    ]


@needs_tomllib
def test_the_installed_core_satisfies_every_requires():
    """The gateway's rule: surface equal, ir not above the running core's."""
    from llm_rosetta.contracts import IR_VERSION, SURFACE_VERSION

    for entry in _build()[0]["vendors"].values():
        requires = entry["versions"][0]["requires"]
        assert requires["surface"] == SURFACE_VERSION
        assert requires["ir"] <= IR_VERSION


@needs_tomllib
def test_vendors_toml_must_name_every_vendor(tree: Path):
    text = (tree / "vendors.toml").read_text()
    (tree / "vendors.toml").write_text(
        text.replace("[vendors.llm7]", "[vendors.seven]")
    )
    with pytest.raises(builder.ManifestError, match="disagree"):
        _build(tree)


def test_the_build_is_byte_reproducible():
    for vendor in VENDORS:
        assert archives.build_archive(vendor, _ROOT) == archives.build_archive(
            vendor, _ROOT
        )


def test_an_archive_holds_one_vendor_under_providers():
    data = archives.build_archive("opendesign", _ROOT)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        names = sorted(m.name for m in tar.getmembers() if m.isfile())
        shims_yaml = tar.extractfile("providers/shims.yaml").read().decode()
    assert all(
        n == "providers/shims.yaml" or n.startswith("providers/opendesign/")
        for n in names
    )
    assert "providers/opendesign/auth.py" in names
    assert 'core: ">=0.14.0"' in shims_yaml
    assert "opendesign--messages" in shims_yaml
    assert "llm7" not in shims_yaml


def test_bytecode_caches_stay_out(tree: Path):
    cache = archives.providers_dir(tree) / "llm7" / "llm" / "__pycache__"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "transforms.cpython-312.pyc").write_bytes(b"\0")
    assert archives.build_archive("llm7", tree) == archives.build_archive("llm7", _ROOT)


def test_a_leaf_missing_from_the_package_shims_yaml_fails_the_build(tree: Path):
    shims = archives.providers_dir(tree) / "shims.yaml"
    shims.write_text(
        shims.read_text().replace(
            "  - name: llm7--chat_completions\n    path: llm7/llm\n", ""
        )
    )
    with pytest.raises(archives.ArchiveError, match="does not match the llm7 leaves"):
        archives.build_archive("llm7", tree)


@needs_tomllib
def test_an_unchanged_vendor_keeps_its_published_record(tree: Path):
    first, _ = _build(tree)
    old = copy.deepcopy(first)
    for entry in old["vendors"].values():
        entry["versions"][0]["commit"] = "1" * 40
    second, added = _build(tree, previous=old)
    assert added == {}
    assert second["vendors"] == old["vendors"]


@needs_tomllib
def test_a_changed_vendor_without_a_bump_is_refused(tree: Path):
    previous, _ = _build(tree)
    leaf = archives.providers_dir(tree) / "llm7" / "llm" / "provider.yaml"
    leaf.write_text(leaf.read_text() + "\n# changed\n")
    with pytest.raises(builder.ManifestError, match="Bump vendors.llm7.version"):
        _build(tree, previous=previous)


@needs_tomllib
def test_a_bumped_vendor_is_prepended(tree: Path):
    previous, _ = _build(tree)
    toml = tree / "vendors.toml"
    toml.write_text(
        toml.read_text().replace(
            '[vendors.llm7]\nversion = "0.4.1"', '[vendors.llm7]\nversion = "0.4.2"'
        )
    )
    leaf = archives.providers_dir(tree) / "llm7" / "llm" / "provider.yaml"
    leaf.write_text(leaf.read_text() + "\n# changed\n")
    manifest, added = _build(tree, previous=previous)
    versions = [r["version"] for r in manifest["vendors"]["llm7"]["versions"]]
    assert versions == ["0.4.2", "0.4.1"]
    assert list(added) == ["0.4.2/llm7.tar.gz"]
    assert (
        manifest["vendors"]["llm7"]["versions"][1]
        == previous["vendors"]["llm7"]["versions"][0]
    )


@needs_tomllib
def test_a_vendor_that_left_the_tree_keeps_its_history(tree: Path):
    previous, _ = _build(tree)
    shutil.rmtree(archives.providers_dir(tree) / "ovhcloud")
    shims = archives.providers_dir(tree) / "shims.yaml"
    shims.write_text(
        shims.read_text().replace(
            "  - name: ovhcloud--chat_completions\n    path: ovhcloud/llm\n", ""
        )
    )
    toml = tree / "vendors.toml"
    text = toml.read_text()
    toml.write_text(
        text[: text.index("[vendors.ovhcloud]")] + text[text.index("# Open Design") :]
    )
    manifest, _ = _build(tree, previous=previous)
    assert manifest["vendors"]["ovhcloud"] == previous["vendors"]["ovhcloud"]


@needs_tomllib
def test_write_outputs_lays_out_the_dist_tree(tree: Path, tmp_path: Path):
    out = tmp_path / "out"
    manifest, added = _build(tree)
    builder.write_outputs(out, manifest, added, "0.4.0")
    assert json.loads((out / "manifest.json").read_text()) == manifest
    assert (out / "0.4.0" / "manifest.json").read_text() == (
        out / "manifest.json"
    ).read_text()
    for rel in added:
        line = (out / f"{rel}.sha256").read_text()
        assert line.split()[0] == archives.sha256_hex((out / rel).read_bytes())
    changed = copy.deepcopy(manifest)
    changed["generated_at"] = "2026-11-22T00:00:00Z"
    with pytest.raises(builder.ManifestError, match="already published"):
        builder.write_outputs(out, changed, {}, "0.4.0")


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("vendors", "llm7", "versions", 0, "maturity"), "gold", "maturity"),
        (("vendors", "llm7", "versions", 0, "requires"), {"surface": 1}, "requires"),
        (("vendors", "llm7", "versions", 0, "sha256"), "abc", "sha256"),
        (
            ("vendors", "llm7", "versions", 0, "shims"),
            ["ovhcloud--chat_completions"],
            "must be 'llm7', 'llm7--<name>' or 'llm7_<lane>--<name>'",
        ),
        (
            # A shared prefix is not the vendor: ``llm7x`` is neither the key
            # nor ``llm7--...``.
            ("vendors", "llm7", "versions", 0, "shims"),
            ["llm7x--chat_completions"],
            "must be 'llm7', 'llm7--<name>' or 'llm7_<lane>--<name>'",
        ),
        (
            ("vendors", "llm7", "versions", 0, "shims"),
            ["ovhcloud"],
            "must be 'llm7', 'llm7--<name>' or 'llm7_<lane>--<name>'",
        ),
        (
            ("vendors", "llm7", "versions", 0, "conformance"),
            {"date": None, "result": "pass"},
            "needs a date",
        ),
        (("vendors", "llm7", "versions", 0, "archive"), "0.4.0/x.tar.gz", "archive"),
        (("vendors", "llm7", "versions", 0, "promoted_to"), "core", "promoted_to"),
        (("manifest_version",), 2, "manifest_version"),
        (("generated_at",), "yesterday", "generated_at"),
    ],
)
@needs_tomllib
def test_the_validator_rejects_a_broken_field(path, value, message):
    doc = copy.deepcopy(_build()[0])
    target = doc
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    errors = builder.validate_manifest(doc)
    assert any(message in e for e in errors), errors


@needs_tomllib
def test_the_cli_dry_run_validates_and_check_accepts_it(tmp_path: Path):
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS / "build_manifest.py"),
            "--dry-run",
            "--commit",
            _COMMIT,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "dry-run: ok" in proc.stderr
    path = tmp_path / "manifest.json"
    path.write_text(proc.stdout)
    check = subprocess.run(
        [sys.executable, str(_SCRIPTS / "build_manifest.py"), "--check", str(path)],
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stderr


@needs_tomllib
def test_the_cli_refuses_a_tag_that_is_not_the_package_version(tmp_path: Path):
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS / "build_manifest.py"),
            "--out",
            str(tmp_path),
            "--expect-version",
            "9.9.9",
            "--commit",
            _COMMIT,
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "tag says 9.9.9" in proc.stderr


_LOAD_ARCHIVE = textwrap.dedent(
    """
    import importlib.abc
    import importlib.util
    import sys
    from pathlib import Path

    class _BlockDistribution(importlib.abc.MetaPathFinder):
        # CI installs the wheel, so block the name outright: the archive's
        # fallback must run even when site-packages could answer.
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] == "llm_rosetta_shim_contrib":
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None

    sys.meta_path.insert(0, _BlockDistribution())
    try:
        importlib.util.find_spec("llm_rosetta_shim_contrib")
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError("the load must not resolve the installed distribution")
    from llm_rosetta.api import list_shims, staging_registry
    from llm_rosetta.contracts.shim import load_providers_from_dir
    with staging_registry():
        load_providers_from_dir(Path(sys.argv[1]), on_error="raise")
    print(" ".join(sorted(s.name for s in list_shims())))
    """
)


@pytest.mark.parametrize("vendor", VENDORS)
def test_each_archive_loads_with_core_in_a_fresh_interpreter(vendor, tmp_path: Path):
    """What a gateway does with a downloaded archive: extract, then load providers/."""
    data = archives.build_archive(vendor, _ROOT)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        safe = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        tar.extractall(tmp_path, **safe)
    proc = subprocess.run(
        [sys.executable, "-c", _LOAD_ARCHIVE, str(tmp_path / "providers")],
        capture_output=True,
        text=True,
        check=True,
    )
    expected = sorted(n for n, _ in archives.declared_shims(vendor, _ROOT))
    assert proc.stdout.split() == expected


def test_a_vendor_that_imports_a_package_helper_ships_it():
    """An archive stands alone, so the helper its auth.py names must travel."""
    helper = (archives.package_dir(_ROOT) / "_vendor_cli.py").read_bytes()
    for vendor in ("antigravity", "claude"):
        data = archives.build_archive(vendor, _ROOT)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            names = [m.name for m in tar.getmembers() if m.isfile()]
            assert "providers/_vendor_cli.py" in names
            assert tar.extractfile("providers/_vendor_cli.py").read() == helper
    assert "providers/_vendor_cli.py" not in archives.archive_members(
        archives.build_archive("llm7", _ROOT)
    )


def test_the_helper_is_found_by_import_not_by_text(tree: Path):
    """A comment must not ship the helper; either import spelling must."""
    note = archives.providers_dir(tree) / "llm7" / "notes.py"
    note.write_text("# llm_rosetta_shim_contrib._vendor_cli\n", encoding="utf-8")
    assert archives.shared_helpers("llm7", tree) == {}
    note.write_text(
        "from llm_rosetta_shim_contrib import _vendor_cli\n", encoding="utf-8"
    )
    assert list(archives.shared_helpers("llm7", tree)) == ["_vendor_cli.py"]


_EXEC_AUTH = textwrap.dedent(
    """
    import importlib.abc
    import importlib.util
    import sys

    class _BlockDistribution(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] == "llm_rosetta_shim_contrib":
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None

    sys.meta_path.insert(0, _BlockDistribution())
    spec = importlib.util.spec_from_file_location("auth_under_test", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print("loaded")
    """
)


def _extracted(tmp_path: Path, vendor: str = "antigravity") -> Path:
    data = archives.build_archive(vendor, _ROOT)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        safe = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        tar.extractall(tmp_path, **safe)
    return tmp_path / "providers"


def test_a_lane_sidecar_finds_the_archive_helper(tmp_path: Path):
    """A lane-level exchange sits deeper than the vendor's auth.py."""
    providers = _extracted(tmp_path)
    deep = providers / "antigravity" / "llm" / "acp" / "auth.py"
    deep.parent.mkdir(parents=True, exist_ok=True)
    (providers / "antigravity" / "auth.py").replace(deep)

    proc = subprocess.run(
        [sys.executable, "-c", _EXEC_AUTH, str(deep)],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr


def test_the_helper_search_stops_at_the_archive_root(tmp_path: Path):
    """A copy above the extraction root must not stand in for the archive's."""
    stray = tmp_path / "outer" / "_vendor_cli.py"
    stray.parent.mkdir(parents=True)
    stray.write_bytes((archives.package_dir(_ROOT) / "_vendor_cli.py").read_bytes())
    auth = (
        tmp_path
        / "outer"
        / "archive"
        / "providers"
        / "antigravity"
        / "llm"
        / "acp"
        / "auth.py"
    )
    auth.parent.mkdir(parents=True)
    auth.write_bytes(
        (archives.providers_dir(_ROOT) / "antigravity" / "auth.py").read_bytes()
    )

    proc = subprocess.run(
        [sys.executable, "-c", _EXEC_AUTH, str(auth)],
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert "providers/_vendor_cli.py is missing from this archive" in proc.stderr


def test_contrib_shares_no_shim_name_with_the_installed_core(capsys):
    """CI's call: no allowances."""
    assert collisions.main([]) == 0
    assert "no collisions" in capsys.readouterr().out


def test_an_allow_file_is_read_one_vendor_per_line(tmp_path, monkeypatch, capsys):
    allow = tmp_path / "moves.txt"
    allow.write_text("# a planned move\nllm7\n\n", encoding="utf-8")
    assert collisions.read_allow_file(allow) == ["llm7"]
    monkeypatch.setattr(
        collisions,
        "core_shim_names",
        lambda: ("0.0.0", {"llm7--chat_completions", "x--y"}, {"x"}),
    )
    assert collisions.main([]) == 1
    assert collisions.main(["--allow-file", str(allow)]) == 0


def test_an_allowed_vendor_that_no_longer_overlaps_is_reported(monkeypatch, capsys):
    """Once core drops a vendor, the check says its allow entry can go."""
    monkeypatch.setattr(
        collisions, "core_shim_names", lambda: ("0.0.0", {"x--y"}, {"x"})
    )
    assert collisions.main(["--allow", "llm7"]) == 0
    assert "allowed vendor 'llm7' no longer overlaps core" in capsys.readouterr().err


def test_a_collision_with_core_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        collisions,
        "core_shim_names",
        lambda: ("0.0.0", {"llm7--chat_completions", "x--y"}, {"x"}),
    )
    assert collisions.main([]) == 1
    assert (
        "shim 'llm7--chat_completions' (llm7) is a core built-in"
        in capsys.readouterr().err
    )
    assert collisions.main(["--allow", "llm7"]) == 0


def test_a_vendor_directory_shared_with_core_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        collisions, "core_shim_names", lambda: ("0.0.0", {"x--y"}, {"opendesign"})
    )
    assert collisions.main([]) == 1
    assert (
        "vendor directory 'opendesign' is also a core vendor" in capsys.readouterr().err
    )


@needs_tomllib
def test_a_bare_vendor_key_is_a_shim_name():
    """Vendors moved from core keep bare chat shim names (``zhipu``); the rule
    is the one core's manifest check adopts: the vendor key, or ``<vendor>--``.
    """
    manifest = _build()[0]
    record = manifest["vendors"]["llm7"]["versions"][0]
    record["shims"] = ["llm7", "llm7--chat_completions"]
    assert builder.validate_manifest(manifest) == []
    assert "zhipu" in manifest["vendors"]["zhipu"]["versions"][0]["shims"]


@needs_tomllib
def test_a_lane_qualified_name_belongs_to_its_vendor():
    """``<vendor>_<lane>--<name>`` is the vendor's (core's rule: alcf_sophia)."""
    manifest = _build()[0]
    manifest["vendors"]["llm7"]["versions"][0]["shims"] = ["llm7_eu--chat_completions"]
    assert builder.validate_manifest(manifest) == []


@needs_tomllib
def test_the_longest_vendor_key_of_the_manifest_owns_a_name():
    """kilo and kilo_free are both vendors: kilo may not publish kilo_free's."""
    manifest = _build()[0]
    kilo = manifest["vendors"]["kilo"]["versions"][0]
    kilo["shims"] = ["kilo--chat_completions", "kilo_free--chat_completions"]
    problems = builder.validate_manifest(manifest)
    assert problems == [
        "vendors.kilo.versions[0].shims: 'kilo_free--chat_completions' "
        "belongs to vendor 'kilo_free' of this manifest"
    ]


@pytest.mark.parametrize(
    ("name", "owner"),
    [
        ("kilo--chat_completions", "kilo"),
        ("kilo_free--chat_completions", "kilo_free"),
        ("opencode--messages", "opencode"),
        ("opencode_zen_free--chat_completions", "opencode_zen_free"),
        ("zhipu", "zhipu"),
        ("zhipu--rerank", "zhipu"),
        ("kilox--chat_completions", None),
    ],
)
def test_shim_owner(name, owner):
    keys = ["kilo", "kilo_free", "opencode", "opencode_zen_free", "zhipu"]
    assert builder.shim_owner(name, keys) == owner


#: The display fields a few vendors publish (every vendor is checked by the
#: release rule below).
EXPECTED_DISPLAY = {
    "kilo": {"label": "Kilo", "logo": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.104.0/icons/kilocode.svg"},
    "kilo_free": {"label": "Kilo (Free)", "logo": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.104.0/icons/kilocode.svg"},
    "antigravity": {"label": "Google (Antigravity)", "logo": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.104.0/icons/antigravity.svg"},
    "claude": {"label": "Anthropic (Claude)", "logo": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.104.0/icons/claude.svg"},
    "zai": {"label": "Z.ai", "logo": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.104.0/icons/zhipu.svg"},
    "groq": {"label": "Groq", "logo": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.104.0/icons/groq.svg"},
    "ovhcloud": {"label": "OVHcloud", "logo": "https://cdn.jsdelivr.net/npm/simple-icons@16.38.0/icons/ovh.svg"},
    "opendesign": {"label": "OpenDesign", "logo": "https://cdn.jsdelivr.net/gh/Oaklight/llm-rosetta-shim-contrib@main/assets/opendesign.svg"},
    "llm7": {"label": "LLM7.io", "logo": None},
}
#: Per-vendor repositories that are archived; no mark may point at them.
ARCHIVED = ("llm-rosetta-shim-opendesign", "llm-rosetta-shim-free")


# -- Display fields (Oaklight/llm-rosetta#1671) ------------------------------


def _vendor_root(root: Path, vendor: str) -> Path:
    return archives.vendor_dir(vendor, root) / "provider.yaml"


@needs_tomllib
def test_every_vendor_record_carries_its_label_and_logo_from_provider_yaml():
    manifest, _ = _build()
    for vendor, expected in EXPECTED_DISPLAY.items():
        record = manifest["vendors"][vendor]["versions"][0]
        assert {k: record.get(k) for k in ("label", "logo")} == expected, vendor
    for entry in manifest["vendors"].values():
        logo = entry["versions"][0].get("logo")
        if logo:
            # A mark follows this repository's main branch or a third-party
            # package pinned to a version; ``@latest`` floats with no owner.
            assert "@latest" not in logo, logo
            assert not any(old in logo for old in ARCHIVED), logo


def test_the_vendor_root_is_read_with_a_yaml_parser(tmp_path: Path):
    """Quoting, a folded line and a comment the old regex reader missed."""
    vendor_root = _vendor_root(_ROOT, "groq")
    text = vendor_root.read_text()
    folded = (
        'group_label: >-\n  Folded\n  Name\nlogo: "https://a.example/x.svg"  # pinned\n'
    )
    work = tmp_path / "repo"
    shutil.copytree(_ROOT, work, ignore=shutil.ignore_patterns(".git", "dist", "__pycache__"))
    target = _vendor_root(work, "groq")
    target.write_text(folded + "\n".join(
        line for line in text.splitlines() if not line.startswith(("group_label:", "logo:"))
    ) + "\n")
    assert builder.vendor_display("groq", work) == {
        "label": "Folded Name",
        "logo": "https://a.example/x.svg",
    }


@needs_tomllib
def test_a_vendor_without_a_label_or_logo_fails_the_release(tmp_path: Path):
    work = tmp_path / "repo"
    shutil.copytree(_ROOT, work, ignore=shutil.ignore_patterns(".git", "dist", "__pycache__"))
    target = _vendor_root(work, "groq")
    target.write_text("\n".join(
        line for line in target.read_text().splitlines()
        if not line.startswith(("group_label:", "logo:"))
    ) + "\n")
    with pytest.raises(builder.ManifestError) as caught:
        builder.build_manifest(work, commit="c" * 40, generated_at="2026-11-21T00:00:00Z")
    message = str(caught.value)
    assert "groq: no group_label" in message
    assert "groq: no logo" in message


def test_the_no_logo_list_is_checked_both_ways(monkeypatch):
    records = {"acme": {"label": "Acme", "logo": "https://a.example/a.svg"}, "bare": {"label": "Bare"}}
    monkeypatch.setattr(builder, "NO_LOGO", frozenset({"bare"}))
    assert builder.display_problems(records) == []
    monkeypatch.setattr(builder, "NO_LOGO", frozenset({"acme", "ghost"}))
    problems = builder.display_problems(records)
    assert "acme: has a logo; drop it from NO_LOGO" in problems
    assert any("bare: no logo" in p for p in problems)
    assert any("'ghost'" in p for p in problems)


def test_the_display_rule_is_cores_not_a_copy():
    """A bad value is refused by core's schema; the builder keeps no copy."""
    contract = pytest.importorskip("llm_rosetta.contracts.shim_manifest")
    if "label" not in contract.load_manifest_schema()["$defs"]["release"]["properties"]:
        pytest.skip("this core predates the display fields")
    assert not any(hasattr(builder, n) for n in ("_LABEL", "_LOGO", "_LABEL_MAX", "_LOGO_MAX"))
    record = {
        "version": "0.1.0",
        "commit": "c" * 40,
        "archive": "0.1.0/acme.tar.gz",
        "sha256": "0" * 64,
        "requires": {"surface": 1, "ir": 1},
        "shims": ["acme--chat_completions"],
        "tags": [],
        "maturity": "beta",
        "since": "2026-11-21",
        "conformance": {"date": None, "result": "none"},
        "promoted_to": None,
    }
    doc = {
        "manifest_version": 1,
        "source": builder.SOURCE,
        "repo": builder.REPO,
        "generated_at": "2026-11-21T00:00:00Z",
        "vendors": {"acme": {"versions": [record]}},
    }
    assert builder.validate_manifest(doc) == []
    for field, value in (("logo", "http://insecure.example/x.svg"), ("label", "x" * 81)):
        bad = copy.deepcopy(doc)
        bad["vendors"]["acme"]["versions"][0][field] = value
        problems = builder.validate_manifest(bad)
        assert any(p.startswith("core schema:") and field in p for p in problems), problems
