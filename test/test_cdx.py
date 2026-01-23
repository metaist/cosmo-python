"""Tests for ci/cdx.py."""

import json
import re
import tempfile
from pathlib import Path

from ci import cdx


def test_component_properties() -> None:
    """Test Component dataclass properties."""
    c = cdx.Component(
        name="python",
        version="3.13.11",
        url="https://www.python.org/ftp/python/3.13.11/Python-3.13.11.tgz",
        sha256="abc123",
        license="PSF-2.0",
        license_url="https://docs.python.org/3/license.html",
        sigstore_identity="test@example.com",
        sigstore_issuer="https://accounts.google.com",
    )
    assert c.bom_ref == "python@3.13.11"
    assert c.display_name == "Python"
    assert c.source_domain == "python.org"
    assert c.license_link == "[PSF-2.0](https://docs.python.org/3/license.html)"
    assert c.has_sigstore is True
    assert c.has_gpg is False
    assert c.signature_type == "Sigstore"


def test_component_display_name_default() -> None:
    """Test Component display_name falls back to name."""
    c = cdx.Component(name="sqlite", version="1.0", url="https://x", sha256="a", license="MIT")
    assert c.display_name == "sqlite"


def test_component_source_domain_strips_prefix() -> None:
    """Test source_domain strips www/ftp prefixes."""
    c1 = cdx.Component(name="a", version="1", url="https://ftp.gnu.org/test.tar.gz", sha256="a", license="MIT")
    assert c1.source_domain == "gnu.org"

    c2 = cdx.Component(name="b", version="1", url="https://www.example.com/file.tar.gz", sha256="a", license="MIT")
    assert c2.source_domain == "example.com"

    # Domain without www/ftp prefix - should not be modified
    c3 = cdx.Component(name="c", version="1", url="https://github.com/file.tar.gz", sha256="a", license="MIT")
    assert c3.source_domain == "github.com"


def test_component_license_link_no_url() -> None:
    """Test license_link without URL returns just the license."""
    c = cdx.Component(name="test", version="1.0", url="https://x", sha256="a", license="MIT")
    assert c.license_link == "MIT"


def test_component_gpg() -> None:
    """Test Component with GPG verification."""
    c = cdx.Component(
        name="openssl",
        version="3.0.0",
        url="https://example.com",
        sha256="abc",
        license="Apache-2.0",
        gpg="ABCD1234",
    )
    assert c.has_gpg is True
    assert c.has_sigstore is False
    assert c.signature_type == "GPG"


def test_component_no_signature() -> None:
    """Test Component without any signature."""
    c = cdx.Component(
        name="test",
        version="1.0",
        url="https://example.com",
        sha256="abc",
        license="MIT",
    )
    assert c.has_gpg is False
    assert c.has_sigstore is False
    assert c.signature_type == "—"


def test_bom_add_and_get() -> None:
    """Test adding and retrieving components from Bom."""
    bom = cdx.Bom()
    c1 = cdx.Component(name="test", version="1.0", url="http://x", sha256="a", license="MIT")
    c2 = cdx.Component(name="test", version="2.0", url="http://y", sha256="b", license="MIT")

    bom.add_component(c1)
    bom.add_component(c2)

    assert bom.get_component("test", "1.0") == c1
    assert bom.get_component("test", "2.0") == c2
    assert bom.get_component("test", "3.0") is None
    assert bom.get_component("other", "1.0") is None


def test_bom_get_components() -> None:
    """Test getting all versions of a component."""
    bom = cdx.Bom()
    c1 = cdx.Component(name="test", version="1.0", url="http://x", sha256="a", license="MIT")
    c2 = cdx.Component(name="test", version="2.0", url="http://y", sha256="b", license="MIT")
    c3 = cdx.Component(name="other", version="1.0", url="http://z", sha256="c", license="MIT")

    bom.add_component(c1)
    bom.add_component(c2)
    bom.add_component(c3)

    test_comps = bom.get_components("test")
    assert len(test_comps) == 2
    assert c1 in test_comps
    assert c2 in test_comps

    assert bom.get_components("missing") == []


def test_bom_get_component_by_ref() -> None:
    """Test getting component by bom-ref."""
    bom = cdx.Bom()
    c = cdx.Component(name="test", version="1.0", url="http://x", sha256="a", license="MIT")
    bom.add_component(c)

    assert bom.get_component_by_ref("test@1.0") == c
    assert bom.get_component_by_ref("test@2.0") is None
    assert bom.get_component_by_ref("invalid") is None


def test_bom_all_components() -> None:
    """Test getting all components."""
    bom = cdx.Bom()
    c1 = cdx.Component(name="a", version="1.0", url="http://x", sha256="a", license="MIT")
    c2 = cdx.Component(name="b", version="1.0", url="http://y", sha256="b", license="MIT")

    bom.add_component(c1)
    bom.add_component(c2)

    all_comps = bom.all_components()
    assert len(all_comps) == 2
    assert c1 in all_comps
    assert c2 in all_comps


def test_bom_all_components_sorted() -> None:
    """Test all_components sorts: cosmo-python first, python second, then alpha."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="zlib", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="python", version="3.13.1", url="x", sha256="a", license="PSF"))
    bom.add_component(cdx.Component(name="cosmo-python", version="3.13.1", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="openssl", version="3.0.0", url="x", sha256="a", license="Apache"))

    all_comps = bom.all_components()
    names = [c.name for c in all_comps]
    # cosmo-python first, python second, then alphabetical (openssl, zlib)
    assert names[0] == "cosmo-python"
    assert names[1] == "python"
    assert names[2] == "openssl"
    assert names[3] == "zlib"


def test_bom_component_names() -> None:
    """Test getting component names."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="a", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="b", version="1.0", url="y", sha256="b", license="MIT"))
    bom.add_component(cdx.Component(name="a", version="2.0", url="z", sha256="c", license="MIT"))

    names = bom.component_names()
    assert sorted(names) == ["a", "b"]


def test_bom_defaults() -> None:
    """Test default version management."""
    bom = cdx.Bom()
    c = cdx.Component(name="test", version="1.0", url="x", sha256="a", license="MIT")
    bom.add_component(c)
    bom.set_default("test", "1.0")

    assert bom.get_default_version("test") == "1.0"
    assert bom.get_default_version("missing") is None
    assert bom.get_default_component("test") == c
    assert bom.get_default_component("missing") is None


def test_bom_default_component() -> None:
    """Test get_default_component returns the default version."""
    bom = cdx.Bom()
    c = cdx.Component(name="python", version="3.13.11", url="x", sha256="a", license="PSF-2.0")
    bom.add_component(c)
    bom.set_default("python", "3.13.11")

    assert bom.get_default_component("python") == c


def test_bom_latest() -> None:
    """Test latest version management."""
    bom = cdx.Bom()
    bom.set_latest("python", "3.13", "3.13.11")

    assert bom.get_latest_version("python", "3.13") == "3.13.11"
    assert bom.get_latest_version("python", "3.12") is None


def test_bom_dependencies() -> None:
    """Test dependency management."""
    bom = cdx.Bom()
    bom.set_dependencies("python@3.13.11", ["openssl@3.5.4", "sqlite@3.51.2"])

    assert bom.get_dependencies("python@3.13.11") == ["openssl@3.5.4", "sqlite@3.51.2"]
    assert bom.get_dependencies("missing@1.0") == []


def test_bom_update_dependency_refs() -> None:
    """Test updating dependency references."""
    bom = cdx.Bom()
    bom.set_dependencies("python@3.13", ["openssl@3.5.4", "sqlite@3.51.2"])
    bom.set_dependencies("python@3.14", ["openssl@3.5.4", "xz@5.8.2"])
    bom.set_dependencies("openssl@3.5.4", ["cosmocc@4.0.2"])  # Doesn't contain openssl

    # Update openssl refs
    count = bom.update_dependency_refs("openssl@3.5.4", "openssl@3.6.0")

    assert count == 2  # python@3.13 and python@3.14
    assert bom.get_dependencies("python@3.13") == ["openssl@3.6.0", "sqlite@3.51.2"]
    assert bom.get_dependencies("python@3.14") == ["openssl@3.6.0", "xz@5.8.2"]
    assert bom.get_dependencies("openssl@3.5.4") == ["cosmocc@4.0.2"]  # Unchanged


def test_bom_update_dependency_refs_no_matches() -> None:
    """Test updating dependency refs when none match."""
    bom = cdx.Bom()
    bom.set_dependencies("python@3.13", ["openssl@3.5.4"])

    count = bom.update_dependency_refs("xz@5.8.1", "xz@5.8.2")

    assert count == 0
    assert bom.get_dependencies("python@3.13") == ["openssl@3.5.4"]  # Unchanged


def test_bom_is_disabled() -> None:
    """Test is_disabled checks version prefix."""
    bom = cdx.Bom()
    bom.set_disabled("python", ["3.9"])

    # Version starting with disabled prefix
    assert bom.is_disabled("python", "3.9.1") is True
    assert bom.is_disabled("python", "3.9.18") is True
    # Version not matching prefix
    assert bom.is_disabled("python", "3.10.1") is False
    # Package with no disabled prefixes
    assert bom.is_disabled("openssl", "3.0.0") is False


def test_bom_python_versions() -> None:
    """Test Python version helpers."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="python", version="3.12.1", url="x", sha256="a", license="PSF"))
    bom.add_component(cdx.Component(name="python", version="3.13.1", url="y", sha256="b", license="PSF"))
    bom.add_component(cdx.Component(name="python", version="3.13.2", url="z", sha256="c", license="PSF"))
    bom.add_component(cdx.Component(name="openssl", version="3.0.0", url="w", sha256="d", license="Apache"))

    assert bom.python_versions() == ["3.12.1", "3.13.1", "3.13.2"]
    assert bom.python_minors() == ["3.12", "3.13"]


def test_bom_merge() -> None:
    """Test merging two BOMs."""
    bom1 = cdx.Bom(timestamp="2024-01-01T00:00:00Z")
    bom1.add_component(cdx.Component(name="a", version="1.0", url="x", sha256="old", license="MIT"))
    bom1.add_component(cdx.Component(name="b", version="1.0", url="y", sha256="b", license="MIT"))
    bom1.set_default("a", "1.0")
    bom1.set_dependencies("a@1.0", ["b@1.0"])

    bom2 = cdx.Bom(timestamp="2024-02-01T00:00:00Z")
    bom2.add_component(cdx.Component(name="a", version="1.0", url="x", sha256="new", license="MIT"))
    bom2.add_component(cdx.Component(name="c", version="1.0", url="z", sha256="c", license="MIT"))
    bom2.set_default("a", "2.0")

    merged = bom1.merge(bom2)

    # bom2's component overrides bom1's
    assert merged.get_component("a", "1.0") is not None
    assert merged.get_component("a", "1.0").sha256 == "new"  # type: ignore[union-attr]

    # Both BOMs' unique components are present
    assert merged.get_component("b", "1.0") is not None
    assert merged.get_component("c", "1.0") is not None

    # bom2's defaults override
    assert merged.get_default_version("a") == "2.0"

    # bom2's timestamp wins
    assert merged.timestamp == "2024-02-01T00:00:00Z"

    # Dependencies from bom1 are preserved
    assert merged.get_dependencies("a@1.0") == ["b@1.0"]


def test_load_file() -> None:
    """Test loading a CycloneDX file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "version": 1,
                "metadata": {
                    "timestamp": "2024-01-01T00:00:00Z",
                    "properties": [
                        {"name": "cosmo:default:test", "value": "1.0"},
                        {"name": "cosmo:latest:python:3.13", "value": "3.13.11"},
                    ],
                },
                "components": [
                    {
                        "type": "library",
                        "name": "test",
                        "version": "1.0",
                        "hashes": [{"alg": "SHA-256", "content": "abc123"}],
                        "licenses": [{"license": {"id": "MIT", "url": "https://mit.edu"}}],
                        "externalReferences": [{"type": "distribution", "url": "https://example.com/test.tar.gz"}],
                        "properties": [{"name": "cosmo:gpg", "value": "DEADBEEF"}],
                    }
                ],
                "dependencies": [{"ref": "test@1.0", "dependsOn": ["other@2.0"]}],
            },
            f,
        )
        f.flush()
        bom = cdx.load(f.name)

    assert bom.timestamp == "2024-01-01T00:00:00Z"
    assert bom.get_default_version("test") == "1.0"
    assert bom.get_latest_version("python", "3.13") == "3.13.11"

    comp = bom.get_component("test", "1.0")
    assert comp is not None
    assert comp.sha256 == "abc123"
    assert comp.license == "MIT"
    assert comp.license_url == "https://mit.edu"
    assert comp.url == "https://example.com/test.tar.gz"
    assert comp.gpg == "DEADBEEF"

    assert bom.get_dependencies("test@1.0") == ["other@2.0"]

    Path(f.name).unlink()


def test_load_path_object() -> None:
    """Test loading with a Path object."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1}, f)
        f.flush()
        bom = cdx.load(Path(f.name))
    assert bom.all_components() == []
    Path(f.name).unlink()


def test_dump_without_meta_component() -> None:
    """Test dump creates default meta_component when not loaded from file."""
    bom = cdx.Bom(timestamp="2024-01-01T00:00:00Z")
    # Don't load from file - _meta_component is empty dict
    bom.add_component(cdx.Component(name="test", version="1.0", url="x", sha256="a", license="MIT"))

    result = cdx.dump(bom)

    # Should have default metadata component
    meta_comp = result["metadata"]["component"]
    assert meta_comp["type"] == "application"
    assert meta_comp["name"] == "cosmo-python"
    assert "publisher" not in meta_comp  # Not set when empty


def test_dump() -> None:
    """Test converting Bom to CycloneDX format."""
    bom = cdx.Bom(timestamp="2024-01-01T00:00:00Z")
    bom.add_component(
        cdx.Component(
            name="test",
            version="1.0",
            url="https://example.com/test.tar.gz",
            sha256="abc123",
            license="MIT",
            license_url="https://mit.edu",
            gpg="DEADBEEF",
            description="A test component",
        )
    )
    bom.set_default("test", "1.0")
    bom.set_dependencies("test@1.0", ["other@2.0"])

    result = cdx.dump(bom)

    assert result["bomFormat"] == "CycloneDX"
    assert result["specVersion"] == "1.5"
    assert result["metadata"]["timestamp"] == "2024-01-01T00:00:00Z"

    # Check metadata properties
    props = {p["name"]: p["value"] for p in result["metadata"]["properties"]}
    assert props["cosmo:default:test"] == "1.0"

    # Check component
    assert len(result["components"]) == 1
    comp = result["components"][0]
    assert comp["name"] == "test"
    assert comp["version"] == "1.0"
    assert comp["description"] == "A test component"
    assert comp["hashes"][0]["content"] == "abc123"
    assert comp["licenses"][0]["license"]["id"] == "MIT"
    assert comp["externalReferences"][0]["url"] == "https://example.com/test.tar.gz"

    # Check properties
    comp_props = {p["name"]: p["value"] for p in comp["properties"]}
    assert comp_props["cosmo:gpg"] == "DEADBEEF"

    # Check dependencies
    assert result["dependencies"] == [{"ref": "test@1.0", "dependsOn": ["other@2.0"]}]


def test_dump_sorts_dependencies() -> None:
    """Test dump sorts dependencies: python first, then alpha, each with version_key."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="python", version="3.9.0", url="x", sha256="a", license="PSF"))
    bom.add_component(cdx.Component(name="python", version="3.10.0", url="x", sha256="a", license="PSF"))
    bom.add_component(cdx.Component(name="cosmocc", version="4.0.0", url="x", sha256="a", license="ISC"))
    bom.add_component(cdx.Component(name="openssl", version="3.0.0", url="x", sha256="a", license="Apache-2.0"))
    bom.set_dependencies("openssl@3.0.0", ["zlib@1.0"])
    bom.set_dependencies("cosmocc@4.0.0", ["gcc@1.0"])
    bom.set_dependencies("python@3.10.0", ["openssl@3.0.0"])
    bom.set_dependencies("python@3.9.0", ["openssl@3.0.0"])

    result = cdx.dump(bom)
    refs = [d["ref"] for d in result["dependencies"]]
    # python first (sorted by version_key: 3.9 < 3.10), then deps alpha
    assert refs == ["python@3.9.0", "python@3.10.0", "cosmocc@4.0.0", "openssl@3.0.0"]


def test_dump_to_file() -> None:
    """Test writing BOM to file."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="test", version="1.0", url="x", sha256="a", license="MIT"))

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        cdx.dump(bom, f.name)

    with open(f.name) as fh:
        data = json.load(fh)
    assert data["components"][0]["name"] == "test"

    Path(f.name).unlink()


def test_dump_license_with_space() -> None:
    """Test that licenses with spaces use 'name' instead of 'id'."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="test", version="1.0", url="x", sha256="a", license="Public Domain"))

    result = cdx.dump(bom)
    assert result["components"][0]["licenses"][0]["license"]["name"] == "Public Domain"
    assert "id" not in result["components"][0]["licenses"][0]["license"]


def test_dump_with_purl() -> None:
    """Test dump includes purl when set."""
    bom = cdx.Bom()
    bom.add_component(
        cdx.Component(
            name="test",
            version="1.0",
            url="x",
            sha256="a",
            license="MIT",
            purl="pkg:github/test/test@1.0",
        )
    )
    result = cdx.dump(bom)
    assert result["components"][0]["purl"] == "pkg:github/test/test@1.0"


def test_dump_with_all_properties() -> None:
    """Test dump includes all optional properties."""
    bom = cdx.Bom()
    bom.add_component(
        cdx.Component(
            name="python",
            version="3.13.11",
            url="https://example.com",
            sha256="abc",
            license="PSF-2.0",
            eol="2029-10",
            status="bugfix",
            sigstore_identity="test@python.org",
            sigstore_issuer="https://accounts.google.com",
        )
    )
    result = cdx.dump(bom)
    props = {p["name"]: p["value"] for p in result["components"][0]["properties"]}
    assert props["cosmo:eol"] == "2029-10"
    assert props["cosmo:status"] == "bugfix"
    assert props["cosmo:sigstore:identity"] == "test@python.org"
    assert props["cosmo:sigstore:issuer"] == "https://accounts.google.com"


def test_dump_with_latest() -> None:
    """Test dump includes latest version mappings in metadata."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="python", version="3.13.11", url="x", sha256="a", license="PSF"))
    bom.set_latest("python", "3.13", "3.13.11")

    result = cdx.dump(bom)
    props = {p["name"]: p["value"] for p in result["metadata"]["properties"]}
    assert props["cosmo:latest:python:3.13"] == "3.13.11"


def test_real_versions_cdx_json() -> None:
    """Test loading the real upstream.cdx.json file."""
    bom = cdx.load("upstream.cdx.json")

    # Check metadata - default should exist and be a valid version
    default_version = bom.get_default_version("python")
    assert default_version is not None
    assert re.match(r"3\.\d+\.\d+", default_version)

    # Check Python components exist
    python_versions = bom.python_versions()
    assert len(python_versions) >= 1
    for v in python_versions:
        assert re.match(r"3\.\d+\.\d+", v)

    # Check Python minors are sorted
    minors = bom.python_minors()
    assert minors == sorted(minors)
    assert all(re.match(r"3\.\d+", m) for m in minors)

    # Check default component has required fields
    default_python = bom.get_default_component("python")
    assert default_python is not None
    assert default_python.sha256 != ""
    assert default_python.url != ""
    assert default_python.license == "PSF-2.0"

    # Check dependencies exist for default python
    deps = bom.get_dependencies(default_python.bom_ref)
    assert len(deps) >= 1
    # Should have openssl and sqlite at minimum
    dep_names = [d.split("@")[0] for d in deps]
    assert "openssl" in dep_names
    assert "sqlite" in dep_names

    # Check component names include expected deps
    names = bom.component_names()
    assert "python" in names
    assert "openssl" in names
    assert "sqlite" in names


# -----------------------------------------------------------------------------
# CLI tests
# -----------------------------------------------------------------------------


def test_cli_default(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI default command."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="python", version="3.13.0", url="http://x", sha256="a", license="PSF"
    ))
    bom.set_default("python", "3.13")
    bom.set_latest("python", "3.13", "3.13.0")
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "default", "python"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    assert captured.getvalue().strip() == "3.13"


def test_cli_latest(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI latest command."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="python", version="3.13.5", url="http://x", sha256="a", license="PSF"
    ))
    bom.set_latest("python", "3.13", "3.13.5")
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "latest", "python", "3.13"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    assert captured.getvalue().strip() == "3.13.5"


def test_cli_sha256(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI sha256 command."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="xz", version="5.6.0", url="http://x", sha256="abc123def", license="MIT"
    ))
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "sha256", "xz", "5.6.0"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    assert captured.getvalue().strip() == "abc123def"


def test_cli_url(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI url command."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="xz", version="5.6.0", url="http://example.com/xz.tar.gz", sha256="a", license="MIT"
    ))
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "url", "xz", "5.6.0"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    assert captured.getvalue().strip() == "http://example.com/xz.tar.gz"


def test_cli_gpg(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI gpg command."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="xz", version="5.6.0", url="http://x", sha256="a", license="MIT", gpg="FINGERPRINT123"
    ))
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "gpg", "xz", "5.6.0"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    assert captured.getvalue().strip() == "FINGERPRINT123"


def test_cli_sigstore_identity(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI sigstore-identity command."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="python", version="3.13.0", url="http://x", sha256="a", license="PSF",
        sigstore_identity="test@python.org", sigstore_issuer="https://accounts.google.com"
    ))
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "sigstore-identity", "python", "3.13.0"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    assert captured.getvalue().strip() == "test@python.org"


def test_cli_sigstore_issuer(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI sigstore-issuer command."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="python", version="3.13.0", url="http://x", sha256="a", license="PSF",
        sigstore_identity="test@python.org", sigstore_issuer="https://accounts.google.com"
    ))
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "sigstore-issuer", "python", "3.13.0"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    assert captured.getvalue().strip() == "https://accounts.google.com"


def test_cli_versions(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI versions command."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="python", version="3.12.1", url="http://x", sha256="a", license="PSF"
    ))
    bom.add_component(cdx.Component(
        name="python", version="3.13.0", url="http://y", sha256="b", license="PSF"
    ))
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "versions"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    output = captured.getvalue().strip()
    assert "3.12.1" in output
    assert "3.13.0" in output


def test_cli_no_args(monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI with no args returns error."""
    monkeypatch.setattr("sys.argv", ["cdx"])
    result = cdx.main()
    assert result == 1


def test_cli_unknown_command(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI with unknown command returns error."""
    bom = cdx.Bom()
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "unknown"])
    result = cdx.main()
    assert result == 1


def test_cli_not_found(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI returns error when component not found."""
    bom = cdx.Bom()
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "sha256", "nonexistent", "1.0"])
    result = cdx.main()
    assert result == 1


def test_cli_default_not_found(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI default returns error when not set."""
    bom = cdx.Bom()
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "default", "nonexistent"])
    result = cdx.main()
    assert result == 1


def test_cli_latest_not_found(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI latest returns error when not set."""
    bom = cdx.Bom()
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "latest", "python", "3.99"])
    result = cdx.main()
    assert result == 1


def test_cli_url_not_found(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI url returns error when not found."""
    bom = cdx.Bom()
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "url", "nonexistent", "1.0"])
    result = cdx.main()
    assert result == 1


def test_cli_gpg_not_found(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI gpg returns error when not set."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="test", version="1.0", url="http://x", sha256="a", license="MIT"
    ))
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "gpg", "test", "1.0"])
    result = cdx.main()
    assert result == 1


def test_cli_sigstore_identity_not_found(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI sigstore-identity returns error when not set."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="test", version="1.0", url="http://x", sha256="a", license="MIT"
    ))
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "sigstore-identity", "test", "1.0"])
    result = cdx.main()
    assert result == 1


def test_cli_sigstore_issuer_not_found(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI sigstore-issuer returns error when not set."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="test", version="1.0", url="http://x", sha256="a", license="MIT"
    ))
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "sigstore-issuer", "test", "1.0"])
    result = cdx.main()
    assert result == 1


def test_build_order() -> None:
    """build_order returns dependencies with parallel levels."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="app", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="libA", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="libB", version="1.0", url="x", sha256="a", license="MIT"))
    bom.set_dependencies("app@1.0", ["libA@1.0", "libB@1.0"])
    bom.set_dependencies("libB@1.0", ["libA@1.0"])

    order = bom.build_order("app@1.0")
    # Returns (level, ref) tuples
    refs = [ref for _, ref in order]
    levels = {ref: level for level, ref in order}
    # libA at level 0, libB at level 1, app at level 2
    assert levels["libA@1.0"] == 0
    assert levels["libB@1.0"] == 1
    assert levels["app@1.0"] == 2
    # Order still correct
    assert refs.index("libA@1.0") < refs.index("libB@1.0")
    assert refs[-1] == "app@1.0"


def test_build_order_no_deps() -> None:
    """build_order returns just the ref at level 0 when no dependencies."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="solo", version="1.0", url="x", sha256="a", license="MIT"))

    order = bom.build_order("solo@1.0")
    assert order == [(0, "solo@1.0")]


def test_toposorted_names_no_python() -> None:
    """toposorted_names falls back to alphabetical when no python."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="zebra", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="alpha", version="1.0", url="x", sha256="a", license="MIT"))
    # No python, no defaults set
    names = bom.toposorted_names()
    assert names == ["alpha", "zebra"]


def test_toposorted_names_cosmo_python_in_extras() -> None:
    """toposorted_names puts cosmo-python first when not in dep graph."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="python", version="3.13.1", url="x", sha256="a", license="PSF"))
    bom.add_component(cdx.Component(name="cosmo-python", version="3.13.1", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="openssl", version="3.0.0", url="x", sha256="a", license="Apache"))
    bom.set_default("python", "3.13.1")
    # python has deps, but cosmo-python is not in dep graph (extras)
    bom.set_dependencies("python@3.13.1", ["openssl@3.0.0"])

    names = bom.toposorted_names()
    # cosmo-python should be first (it's the product)
    assert names[0] == "cosmo-python"
    # python should be after its deps
    assert names.index("python") > names.index("openssl")


def test_toposorted_names_forward_order() -> None:
    """toposorted_names with reverse=False gives build order (deps first)."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="python", version="3.13.1", url="x", sha256="a", license="PSF"))
    bom.add_component(cdx.Component(name="openssl", version="3.0.0", url="x", sha256="a", license="Apache"))
    bom.set_default("python", "3.13.1")
    bom.set_dependencies("python@3.13.1", ["openssl@3.0.0"])

    names = bom.toposorted_names(reverse=False)
    # Forward order: deps first, then python
    assert names.index("openssl") < names.index("python")


def test_toposorted_names_uses_cosmo_python_root() -> None:
    """toposorted_names uses cosmo-python as root when present with deps."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="python", version="3.13.1", url="x", sha256="a", license="PSF"))
    bom.add_component(cdx.Component(name="cosmo-python", version="3.13.1", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="openssl", version="3.0.0", url="x", sha256="a", license="Apache"))
    bom.set_default("python", "3.13.1")
    # cosmo-python has deps (manifest scenario)
    bom.set_dependencies("cosmo-python@3.13.1", ["python@3.13.1"])
    bom.set_dependencies("python@3.13.1", ["openssl@3.0.0"])

    names = bom.toposorted_names()
    # All should be present
    assert "cosmo-python" in names
    assert "python" in names
    assert "openssl" in names


def test_toposorted_names_uses_python_root() -> None:
    """toposorted_names uses python as root when no cosmo-python (upstream scenario)."""
    bom = cdx.Bom()
    # No cosmo-python - just python and deps
    bom.add_component(cdx.Component(name="python", version="3.13.1", url="x", sha256="a", license="PSF"))
    bom.add_component(cdx.Component(name="openssl", version="3.0.0", url="x", sha256="a", license="Apache"))
    bom.add_component(cdx.Component(name="sqlite", version="3.51.0", url="x", sha256="a", license="Public"))
    bom.set_default("python", "3.13.1")
    bom.set_dependencies("python@3.13.1", ["openssl@3.0.0", "sqlite@3.51.0"])

    names = bom.toposorted_names()
    # python should be first (reverse order), deps after
    assert names[0] == "python"
    assert "openssl" in names
    assert "sqlite" in names


def test_toposorted_names_with_explicit_root() -> None:
    """toposorted_names with explicit root skips auto-detection."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="app", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="lib", version="1.0", url="x", sha256="a", license="MIT"))
    bom.set_dependencies("app@1.0", ["lib@1.0"])

    names = bom.toposorted_names(root="app@1.0")
    assert "app" in names
    assert "lib" in names


def test_toposorted_names_cosmo_python_not_in_graph() -> None:
    """toposorted_names puts cosmo-python first even when not in dep graph."""
    bom = cdx.Bom()
    # cosmo-python exists but won't be in the traversal
    bom.add_component(cdx.Component(name="cosmo-python", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="app", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="lib", version="1.0", url="x", sha256="a", license="MIT"))
    bom.set_dependencies("app@1.0", ["lib@1.0"])

    # Explicit root that doesn't include cosmo-python
    names = bom.toposorted_names(root="app@1.0")
    # cosmo-python should be inserted first (it's the product)
    assert names[0] == "cosmo-python"
    assert "app" in names
    assert "lib" in names


def test_build_order_parallel() -> None:
    """build_order groups independent deps at same level."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="app", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="libA", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="libB", version="1.0", url="x", sha256="a", license="MIT"))
    bom.set_dependencies("app@1.0", ["libA@1.0", "libB@1.0"])
    # libA and libB have no deps - can build in parallel

    order = bom.build_order("app@1.0")
    levels = {ref: level for level, ref in order}
    # Both libs at level 0 (parallel)
    assert levels["libA@1.0"] == 0
    assert levels["libB@1.0"] == 0
    # app at level 1
    assert levels["app@1.0"] == 1


def test_cli_build_order(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI build-order command outputs level and ref."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="app", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="lib", version="1.0", url="x", sha256="a", license="MIT"))
    bom.set_dependencies("app@1.0", ["lib@1.0"])
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "build-order", "app", "1.0"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    output = captured.getvalue().strip().split("\n")
    assert output == ["0 lib@1.0", "1 app@1.0"]


def test_cli_build_order_exclude(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI build-order --exclude filters out packages."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="app", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="lib", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="skip", version="1.0", url="x", sha256="a", license="MIT"))
    bom.set_dependencies("app@1.0", ["lib@1.0", "skip@1.0"])
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "build-order", "app", "1.0", "--exclude", "skip"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    output = captured.getvalue().strip().split("\n")
    assert "skip@1.0" not in output[0]
    assert "lib@1.0" in output[0]


def test_cli_build_order_ignores_unknown_args(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI build-order ignores unknown arguments."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="app", version="1.0", url="x", sha256="a", license="MIT"))
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "build-order", "app", "1.0", "--unknown", "arg"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    output = captured.getvalue().strip()
    assert "app@1.0" in output


def test_upstream_table() -> None:
    """upstream_table returns table with linked dependency names."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="openssl", version="3.0.0", url="https://github.com/openssl/openssl/x",
        sha256="a", license="Apache-2.0", gpg="ABC123"
    ))
    bom.set_default("openssl", "3.0.0")

    table = bom.upstream_table()
    assert "| Dependency | Version | Integrity | Signature | License |" in table
    assert "[OpenSSL](https://github.com/openssl/openssl/x)" in table
    assert "SHA256" in table
    assert "GPG" in table


def test_upstream_table_python_version_range() -> None:
    """upstream_table shows version range for Python."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="python", version="3.12.0", url="http://x", sha256="a", license="PSF"
    ))
    bom.add_component(cdx.Component(
        name="python", version="3.13.0", url="http://y", sha256="b", license="PSF"
    ))
    bom.set_default("python", "3.13.0")

    table = bom.upstream_table()
    assert "3.12–3.13" in table


def test_load_with_non_sha256_hash(tmp_path: Path) -> None:
    """load handles components with non-SHA256 hashes."""
    data = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"timestamp": "2026-01-01T00:00:00Z"},
        "components": [{
            "type": "library",
            "name": "test",
            "version": "1.0",
            "hashes": [
                {"alg": "MD5", "content": "abc"},  # Not SHA-256
                {"alg": "SHA-256", "content": "def123"},  # This one
            ],
            "licenses": [{"license": {"id": "MIT"}}],
        }],
    }
    cdx_file = tmp_path / "test.cdx.json"
    cdx_file.write_text(json.dumps(data))

    bom = cdx.load(cdx_file)
    comp = bom.get_component("test", "1.0")
    assert comp is not None
    assert comp.sha256 == "def123"


def test_load_with_non_distribution_ref(tmp_path: Path) -> None:
    """load handles components with non-distribution external refs."""
    data = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"timestamp": "2026-01-01T00:00:00Z"},
        "components": [{
            "type": "library",
            "name": "test",
            "version": "1.0",
            "externalReferences": [
                {"type": "website", "url": "http://example.com"},  # Not distribution
                {"type": "distribution", "url": "http://download.com/test.tar.gz"},
            ],
            "licenses": [{"license": {"id": "MIT"}}],
        }],
    }
    cdx_file = tmp_path / "test.cdx.json"
    cdx_file.write_text(json.dumps(data))

    bom = cdx.load(cdx_file)
    comp = bom.get_component("test", "1.0")
    assert comp is not None
    assert comp.url == "http://download.com/test.tar.gz"


def test_load_with_license_name(tmp_path: Path) -> None:
    """load handles licenses with name instead of id."""
    data = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"timestamp": "2026-01-01T00:00:00Z"},
        "components": [{
            "type": "library",
            "name": "test",
            "version": "1.0",
            "licenses": [{"license": {"name": "Custom License"}}],
        }],
    }
    cdx_file = tmp_path / "test.cdx.json"
    cdx_file.write_text(json.dumps(data))

    bom = cdx.load(cdx_file)
    comp = bom.get_component("test", "1.0")
    assert comp is not None
    assert comp.license == "Custom License"


def test_load_with_non_cosmo_property(tmp_path: Path) -> None:
    """load ignores properties without cosmo: prefix."""
    data = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"timestamp": "2026-01-01T00:00:00Z"},
        "components": [{
            "type": "library",
            "name": "test",
            "version": "1.0",
            "licenses": [{"license": {"id": "MIT"}}],
            "properties": [
                {"name": "other:prop", "value": "ignored"},
                {"name": "cosmo:gpg", "value": "ABC123"},
            ],
        }],
    }
    cdx_file = tmp_path / "test.cdx.json"
    cdx_file.write_text(json.dumps(data))

    bom = cdx.load(cdx_file)
    comp = bom.get_component("test", "1.0")
    assert comp is not None
    assert comp.gpg == "ABC123"


def test_load_with_unknown_metadata_property(tmp_path: Path) -> None:
    """load ignores unknown metadata properties."""
    data = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": "2026-01-01T00:00:00Z",
            "properties": [
                {"name": "cosmo:unknown:prop", "value": "ignored"},
                {"name": "cosmo:default:python", "value": "3.13.0"},
            ],
        },
        "components": [{
            "type": "library",
            "name": "python",
            "version": "3.13.0",
            "licenses": [{"license": {"id": "PSF-2.0"}}],
        }],
    }
    cdx_file = tmp_path / "test.cdx.json"
    cdx_file.write_text(json.dumps(data))

    bom = cdx.load(cdx_file)
    assert bom.get_default_version("python") == "3.13.0"


def test_load_component_without_release_property(tmp_path: Path) -> None:
    """load handles components without cosmo:release property."""
    data = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"timestamp": "2026-01-01T00:00:00Z"},
        "components": [{
            "type": "library",
            "name": "test",
            "version": "1.0",
            "licenses": [{"license": {"id": "MIT"}}],
            "properties": [{"name": "cosmo:gpg", "value": "ABC"}],  # Not cosmo:release
        }],
    }
    cdx_file = tmp_path / "test.cdx.json"
    cdx_file.write_text(json.dumps(data))

    bom = cdx.load(cdx_file)
    assert bom.get_component("test", "1.0") is not None


def test_dump_with_empty_disabled(tmp_path: Path) -> None:
    """dump handles empty disabled prefixes."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="test", version="1.0", url="http://x", sha256="a", license="MIT"
    ))
    bom.set_default("test", "1.0")
    bom._disabled["test"] = []  # Empty list

    result = cdx.dump(bom)
    # Should not include cosmo:disabled:test in properties
    props = result["metadata"]["properties"]
    disabled_props = [p for p in props if p["name"].startswith("cosmo:disabled:")]
    assert len(disabled_props) == 0


def test_dump_without_dependencies(tmp_path: Path) -> None:
    """dump handles BOM without dependencies."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="test", version="1.0", url="http://x", sha256="a", license="MIT"
    ))
    bom.set_default("test", "1.0")
    # No dependencies set

    result = cdx.dump(bom)
    assert "dependencies" not in result


def test_load_component_without_license(tmp_path: Path) -> None:
    """load handles components without license."""
    data = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"timestamp": "2026-01-01T00:00:00Z"},
        "components": [{
            "type": "library",
            "name": "test",
            "version": "1.0",
            # No licenses array
        }],
    }
    cdx_file = tmp_path / "test.cdx.json"
    cdx_file.write_text(json.dumps(data))

    bom = cdx.load(cdx_file)
    comp = bom.get_component("test", "1.0")
    assert comp is not None
    assert comp.license == ""


def test_load_invalid_latest_property(tmp_path: Path) -> None:
    """load handles invalid cosmo:latest: format (missing colon)."""
    data = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": "2026-01-01T00:00:00Z",
            "properties": [
                {"name": "cosmo:latest:python", "value": "3.13.0"},  # Missing :3.13
            ],
        },
        "components": [],
    }
    cdx_file = tmp_path / "test.cdx.json"
    cdx_file.write_text(json.dumps(data))

    bom = cdx.load(cdx_file)
    # Should not crash, just ignore invalid property
    assert bom.get_latest_version("python", "3.13") is None


def test_load_empty_disabled_prefixes(tmp_path: Path) -> None:
    """load handles empty disabled prefixes."""
    data = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": "2026-01-01T00:00:00Z",
            "properties": [
                {"name": "cosmo:disabled:python", "value": ""},  # Empty value
            ],
        },
        "components": [],
    }
    cdx_file = tmp_path / "test.cdx.json"
    cdx_file.write_text(json.dumps(data))

    bom = cdx.load(cdx_file)
    assert bom.get_disabled("python") == []


def test_load_dependency_with_empty_ref(tmp_path: Path) -> None:
    """load ignores dependencies with empty ref."""
    data = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"timestamp": "2026-01-01T00:00:00Z"},
        "components": [{
            "type": "library",
            "name": "test",
            "version": "1.0",
            "licenses": [{"license": {"id": "MIT"}}],
        }],
        "dependencies": [
            {"ref": "", "dependsOn": ["other@1.0"]},  # Empty ref
            {"ref": "test@1.0", "dependsOn": []},
        ],
    }
    cdx_file = tmp_path / "test.cdx.json"
    cdx_file.write_text(json.dumps(data))

    bom = cdx.load(cdx_file)
    # Empty ref should be ignored
    assert bom.get_dependencies("") == []
    assert bom.get_dependencies("test@1.0") == []


def test_build_order_all_python() -> None:
    """build_order_all_python returns union of deps for all Python versions."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="python", version="3.13.0", url="x", sha256="a", license="PSF"))
    bom.add_component(cdx.Component(name="python", version="3.14.0", url="x", sha256="a", license="PSF"))
    bom.add_component(cdx.Component(name="libA", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="libB", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="zstd", version="1.0", url="x", sha256="a", license="BSD"))
    # 3.13 needs libA and libB; 3.14 also needs zstd
    bom.set_dependencies("python@3.13.0", ["libA@1.0", "libB@1.0"])
    bom.set_dependencies("python@3.14.0", ["libA@1.0", "libB@1.0", "zstd@1.0"])

    order = bom.build_order_all_python()
    refs = [ref for _, ref in order]
    # All deps should be included (union)
    assert "libA@1.0" in refs
    assert "libB@1.0" in refs
    assert "zstd@1.0" in refs
    assert "python@3.13.0" in refs
    assert "python@3.14.0" in refs


def test_cli_build_order_all(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI build-order-all returns union of deps for all Python versions."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="python", version="3.13.0", url="x", sha256="a", license="PSF"))
    bom.add_component(cdx.Component(name="python", version="3.14.0", url="x", sha256="a", license="PSF"))
    bom.add_component(cdx.Component(name="lib", version="1.0", url="x", sha256="a", license="MIT"))
    bom.add_component(cdx.Component(name="zstd", version="1.0", url="x", sha256="a", license="BSD"))
    bom.set_dependencies("python@3.13.0", ["lib@1.0"])
    bom.set_dependencies("python@3.14.0", ["lib@1.0", "zstd@1.0"])
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "build-order-all", "--exclude", "python"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    output = captured.getvalue()
    assert "lib@1.0" in output
    assert "zstd@1.0" in output
    assert "python@" not in output  # excluded


def test_cli_build_order_all_ignores_unknown_args(
    tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
) -> None:
    """CLI build-order-all ignores unknown arguments."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(name="python", version="3.13.0", url="x", sha256="a", license="PSF"))
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "build-order-all", "--unknown", "arg"])

    import io
    import sys
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    result = cdx.main()
    assert result == 0
    output = captured.getvalue()
    assert "python@3.13.0" in output
