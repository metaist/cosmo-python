"""Tests for ci/cdx.py."""

import json
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
    """Test loading the real versions.cdx.json file."""
    bom = cdx.load("versions.cdx.json")

    # Check metadata
    assert bom.get_default_version("python") == "3.13.11"
    assert bom.get_latest_version("python", "3.13") == "3.13.11"

    # Check Python components
    python_versions = bom.python_versions()
    assert "3.13.11" in python_versions
    assert len(python_versions) == 5

    # Check Python minors
    assert bom.python_minors() == ["3.10", "3.11", "3.12", "3.13", "3.14"]

    # Check a specific component
    comp = bom.get_component("python", "3.13.11")
    assert comp is not None
    assert comp.sha256 != ""
    assert comp.url != ""
    assert comp.license == "PSF-2.0"
    assert comp.sigstore_identity == "thomas@python.org"
    assert comp.has_sigstore is True

    # Check default component resolution
    default_python = bom.get_default_component("python")
    assert default_python is not None
    assert default_python.version == "3.13.11"

    # Check dependencies
    deps = bom.get_dependencies("python@3.13.11")
    assert "openssl@3.5.4" in deps
    assert "sqlite@3.51.2" in deps

    # Check non-SPDX license (sqlite)
    sqlite = bom.get_component("sqlite", "3.51.2")
    assert sqlite is not None
    assert sqlite.license == "Public Domain"

    # Check component names
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "unknown"])
    result = cdx.main()
    assert result == 1


def test_cli_not_found(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI returns error when component not found."""
    bom = cdx.Bom()
    cdx_file = tmp_path / "versions.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "sha256", "nonexistent", "1.0"])
    result = cdx.main()
    assert result == 1


def test_cli_default_not_found(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI default returns error when not set."""
    bom = cdx.Bom()
    cdx_file = tmp_path / "versions.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "default", "nonexistent"])
    result = cdx.main()
    assert result == 1


def test_cli_latest_not_found(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI latest returns error when not set."""
    bom = cdx.Bom()
    cdx_file = tmp_path / "versions.cdx.json"
    cdx.dump(bom, cdx_file)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("sys.argv", ["cdx", "latest", "python", "3.99"])
    result = cdx.main()
    assert result == 1


def test_cli_url_not_found(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """CLI url returns error when not found."""
    bom = cdx.Bom()
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
    cdx_file = tmp_path / "versions.cdx.json"
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
