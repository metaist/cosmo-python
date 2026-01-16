"""CycloneDX helper functions for reading and manipulating SBOMs.

This module provides a Python-native representation of CycloneDX BOMs
that's easier to work with than the raw JSON structure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Display names for components (only entries that differ from name)
DISPLAY_NAMES: dict[str, str] = {
    "python": "Python",
    "cacert": "CA certs",
    "cosmocc": "Cosmopolitan",
    "openssl": "OpenSSL",
    "xz": "xz/liblzma",
}


@dataclass
class Component:
    """A software component (package/library/application).

    >>> c = Component(name="python", version="3.13.11", url="https://python.org/ftp/python/3.13.11/Python-3.13.11.tgz", sha256="abc123", license="PSF-2.0")
    >>> c.bom_ref
    'python@3.13.11'
    >>> c.display_name
    'Python'
    >>> c.source_domain
    'python.org'
    >>> c.has_sigstore
    False
    >>> c.has_gpg
    False

    >>> c2 = Component(name="sqlite", version="3.0", url="https://www.sqlite.org/file.tar.gz", sha256="x", license="Public Domain", license_url="https://sqlite.org/copyright.html")
    >>> c2.display_name
    'sqlite'
    >>> c2.source_domain
    'sqlite.org'
    >>> c2.license_link
    '[Public Domain](https://sqlite.org/copyright.html)'

    >>> c3 = Component(name="test", version="1.0", url="https://ftp.gnu.org/test.tar.gz", sha256="x", license="MIT")
    >>> c3.source_domain
    'gnu.org'
    >>> c3.license_link
    'MIT'
    """

    name: str
    version: str
    url: str
    sha256: str
    license: str  # SPDX ID or custom name
    license_url: str | None = None
    purl: str | None = None
    gpg: str | None = None
    sigstore_identity: str | None = None
    sigstore_issuer: str | None = None
    description: str | None = None
    eol: str | None = None  # End of life date (YYYY-MM)
    status: str | None = None  # e.g., "bugfix", "security"
    component_type: str = "library"  # CycloneDX type: application, library, data

    @property
    def bom_ref(self) -> str:
        """Return the bom-ref identifier (name@version)."""
        return f"{self.name}@{self.version}"

    @property
    def display_name(self) -> str:
        """Return human-readable display name."""
        return DISPLAY_NAMES.get(self.name, self.name)

    @property
    def source_domain(self) -> str:
        """Return the source domain from the URL."""
        from urllib.parse import urlparse

        domain = urlparse(self.url).netloc
        # Strip www/ftp subdomain for cleaner display
        if domain.startswith(("www.", "ftp.")):
            domain = domain.split(".", 1)[1]
        return domain

    @property
    def license_link(self) -> str:
        """Return license as markdown link if URL available, otherwise just the license."""
        if self.license_url:
            return f"[{self.license}]({self.license_url})"
        return self.license

    @property
    def has_sigstore(self) -> bool:
        """Return True if this component has Sigstore verification."""
        return self.sigstore_identity is not None

    @property
    def has_gpg(self) -> bool:
        """Return True if this component has GPG verification."""
        return self.gpg is not None

    @property
    def signature_type(self) -> str:
        """Return the signature type for display."""
        if self.has_sigstore:
            return "Sigstore"
        elif self.has_gpg:
            return "GPG"
        return "—"


@dataclass
class Bom:
    """A Bill of Materials containing components and their relationships.

    >>> bom = Bom()
    >>> c = Component(name="test", version="1.0", url="http://x", sha256="abc", license="MIT")
    >>> bom.add_component(c)
    >>> bom.get_component("test", "1.0") == c
    True
    >>> bom.set_default("test", "1.0")
    >>> bom.get_default_version("test")
    '1.0'
    """

    # Internal storage
    _components: dict[str, dict[str, Component]] = field(default_factory=dict)
    _defaults: dict[str, str] = field(default_factory=dict)
    _latest: dict[str, str] = field(default_factory=dict)  # "python:3.13" -> "3.13.11"
    _dependencies: dict[str, list[str]] = field(default_factory=dict)

    # Metadata
    timestamp: str | None = None

    # Component access

    def add_component(self, component: Component) -> None:
        """Add a component to the BOM."""
        if component.name not in self._components:
            self._components[component.name] = {}
        self._components[component.name][component.version] = component

    def get_component(self, name: str, version: str) -> Component | None:
        """Get a specific component by name and version."""
        return self._components.get(name, {}).get(version)

    def get_components(self, name: str) -> list[Component]:
        """Get all components with a given name (all versions)."""
        return list(self._components.get(name, {}).values())

    def get_component_by_ref(self, ref: str) -> Component | None:
        """Get a component by its bom-ref (name@version)."""
        if "@" not in ref:
            return None
        name, version = ref.rsplit("@", 1)
        return self.get_component(name, version)

    def all_components(self) -> list[Component]:
        """Get all components in the BOM."""
        result: list[Component] = []
        for versions in self._components.values():
            result.extend(versions.values())
        return result

    def component_names(self) -> list[str]:
        """Get all unique component names."""
        return list(self._components.keys())

    # Defaults and latest

    def set_default(self, name: str, version: str) -> None:
        """Set the default version for a package."""
        self._defaults[name] = version

    def get_default_version(self, name: str) -> str | None:
        """Get the default version for a package."""
        return self._defaults.get(name)

    def get_default_component(self, name: str) -> Component | None:
        """Get the default component for a package."""
        version = self.get_default_version(name)
        if version is None:
            return None
        # For Python, default is minor (e.g., "3.13"), need to resolve to patch
        latest_key = f"{name}:{version}"
        if latest_key in self._latest:
            version = self._latest[latest_key]
        return self.get_component(name, version)

    def set_latest(self, name: str, minor: str, version: str) -> None:
        """Set the latest patch version for a minor version."""
        self._latest[f"{name}:{minor}"] = version

    def get_latest_version(self, name: str, minor: str) -> str | None:
        """Get the latest patch version for a minor version."""
        return self._latest.get(f"{name}:{minor}")

    # Dependencies

    def set_dependencies(self, ref: str, deps: list[str]) -> None:
        """Set the dependencies for a component (by bom-ref)."""
        self._dependencies[ref] = deps

    def get_dependencies(self, ref: str) -> list[str]:
        """Get the dependency refs for a component."""
        return self._dependencies.get(ref, [])

    # Convenience methods

    def python_versions(self) -> list[str]:
        """Get all Python versions in the BOM."""
        return sorted(c.version for c in self.get_components("python"))

    def python_minors(self) -> list[str]:
        """Get all Python minor versions (e.g., ['3.10', '3.11', ...])."""
        versions = self.python_versions()
        return sorted(set(".".join(v.split(".")[:2]) for v in versions))

    # Merging (for spanning manifest)

    def merge(self, other: Bom) -> Bom:
        """Merge another BOM into this one, returning a new BOM.

        Components from `other` override components in `self` with the same name@version.
        """
        result = Bom(timestamp=other.timestamp or self.timestamp)

        # Copy all components from self
        for comp in self.all_components():
            result.add_component(comp)

        # Override/add components from other
        for comp in other.all_components():
            result.add_component(comp)

        # Merge defaults (other wins)
        result._defaults = {**self._defaults, **other._defaults}

        # Merge latest (other wins)
        result._latest = {**self._latest, **other._latest}

        # Merge dependencies (other wins for same ref)
        result._dependencies = {**self._dependencies, **other._dependencies}

        return result


def _parse_component(data: dict[str, Any]) -> Component:
    """Parse a CycloneDX component dict into a Component object."""
    # Extract hash
    sha256 = ""
    for h in data.get("hashes", []):
        if h.get("alg") == "SHA-256":
            sha256 = h.get("content", "")
            break

    # Extract URL
    url = ""
    for ref in data.get("externalReferences", []):
        if ref.get("type") == "distribution":
            url = ref.get("url", "")
            break

    # Extract license
    license_id = ""
    license_url = None
    for lic in data.get("licenses", []):
        license_obj = lic.get("license", {})
        license_id = license_obj.get("id") or license_obj.get("name", "")
        license_url = license_obj.get("url")
        break

    # Extract properties
    props: dict[str, str] = {}
    for prop in data.get("properties", []):
        name = prop.get("name", "")
        if name.startswith("cosmo:"):
            key = name[6:]  # Remove "cosmo:" prefix
            props[key] = prop.get("value", "")

    return Component(
        name=data.get("name", ""),
        version=data.get("version", ""),
        url=url,
        sha256=sha256,
        license=license_id,
        license_url=license_url,
        purl=data.get("purl"),
        gpg=props.get("gpg"),
        sigstore_identity=props.get("sigstore:identity"),
        sigstore_issuer=props.get("sigstore:issuer"),
        description=data.get("description"),
        eol=props.get("eol"),
        status=props.get("status"),
        component_type=data.get("type", "library"),
    )


def load(path: Path | str) -> Bom:
    """Load a CycloneDX BOM from a JSON file."""
    with open(path) as f:
        data = json.load(f)

    bom = Bom()

    # Parse metadata
    metadata = data.get("metadata", {})
    bom.timestamp = metadata.get("timestamp")

    # Parse metadata properties for defaults and latest
    for prop in metadata.get("properties", []):
        name = prop.get("name", "")
        value = prop.get("value", "")
        if name.startswith("cosmo:default:"):
            pkg = name[14:]  # Remove "cosmo:default:" prefix
            bom.set_default(pkg, value)
        elif name.startswith("cosmo:latest:"):
            # e.g., "cosmo:latest:python:3.13" -> "3.13.11"
            rest = name[13:]  # Remove "cosmo:latest:" prefix
            if ":" in rest:
                pkg, minor = rest.split(":", 1)
                bom.set_latest(pkg, minor, value)

    # Parse components
    for comp_data in data.get("components", []):
        bom.add_component(_parse_component(comp_data))

    # Parse dependencies
    for dep in data.get("dependencies", []):
        ref = dep.get("ref", "")
        depends_on = dep.get("dependsOn", [])
        if ref:
            bom.set_dependencies(ref, depends_on)

    return bom


def _component_to_cdx(comp: Component) -> dict[str, Any]:
    """Convert a Component to CycloneDX dict format."""
    result: dict[str, Any] = {
        "type": comp.component_type,
        "bom-ref": comp.bom_ref,
        "name": comp.name,
        "version": comp.version,
    }

    if comp.description:
        result["description"] = comp.description

    if comp.purl:
        result["purl"] = comp.purl

    result["hashes"] = [{"alg": "SHA-256", "content": comp.sha256}]

    # License - use id if it looks like SPDX, otherwise use name
    license_entry: dict[str, str] = {}
    # Simple heuristic: SPDX IDs don't have spaces
    if " " not in comp.license:
        license_entry["id"] = comp.license
    else:
        license_entry["name"] = comp.license
    if comp.license_url:
        license_entry["url"] = comp.license_url
    result["licenses"] = [{"license": license_entry}]

    result["externalReferences"] = [{"type": "distribution", "url": comp.url}]

    # Properties
    properties: list[dict[str, str]] = []
    if comp.eol:
        properties.append({"name": "cosmo:eol", "value": comp.eol})
    if comp.status:
        properties.append({"name": "cosmo:status", "value": comp.status})
    if comp.sigstore_identity:
        properties.append(
            {"name": "cosmo:sigstore:identity", "value": comp.sigstore_identity}
        )
    if comp.sigstore_issuer:
        properties.append(
            {"name": "cosmo:sigstore:issuer", "value": comp.sigstore_issuer}
        )
    if comp.gpg:
        properties.append({"name": "cosmo:gpg", "value": comp.gpg})

    if properties:
        result["properties"] = properties

    return result


def dump(bom: Bom, path: Path | str | None = None) -> dict[str, Any]:
    """Convert a Bom to CycloneDX dict format, optionally writing to a file."""
    # Build metadata properties
    meta_props: list[dict[str, str]] = []

    # Add defaults
    for pkg, version in sorted(bom._defaults.items()):
        meta_props.append({"name": f"cosmo:default:{pkg}", "value": version})

    # Add latest (only python for now)
    for key, version in sorted(bom._latest.items()):
        pkg, minor = key.split(":", 1)
        meta_props.append({"name": f"cosmo:latest:{pkg}:{minor}", "value": version})

    result: dict[str, Any] = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": bom.timestamp
            or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": {
                "type": "application",
                "name": "cosmo-python",
                "publisher": "metaist",
            },
            "properties": meta_props,
        },
        "components": [_component_to_cdx(c) for c in bom.all_components()],
    }

    # Add dependencies
    deps_list: list[dict[str, Any]] = []
    for ref, depends_on in sorted(bom._dependencies.items()):
        deps_list.append({"ref": ref, "dependsOn": depends_on})
    if deps_list:
        result["dependencies"] = deps_list

    if path:
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
            f.write("\n")

    return result
