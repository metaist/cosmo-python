"""I/O functions for loading and saving CycloneDX BOMs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ci.common import version_key
from ci.json_fmt import dumps as json_dumps

from .bom import Bom
from .component import Component


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
        attestation_repo=props.get("attestation:repo"),
    )


def load(path: Path | str) -> Bom:
    """Load a CycloneDX BOM from a JSON file."""
    with open(path) as f:
        data = json.load(f)

    bom = Bom()

    # Parse BOM version (revision number)
    bom._version = data.get("version", 1)

    # Parse metadata
    metadata = data.get("metadata", {})
    bom.timestamp = metadata.get("timestamp")

    # Parse release version from metadata.component.version
    meta_component = metadata.get("component", {})
    bom._release = meta_component.get("version")

    # Parse metadata properties for defaults, latest, and disabled
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
        elif name.startswith("cosmo:disabled:"):
            # e.g., "cosmo:disabled:python" -> "3.9,3.8" (comma-separated prefixes)
            pkg = name[15:]  # Remove "cosmo:disabled:" prefix
            prefixes = [p.strip() for p in value.split(",") if p.strip()]
            if prefixes:
                bom.set_disabled(pkg, prefixes)

    # Parse components and per-component releases
    for comp_data in data.get("components", []):
        comp = _parse_component(comp_data)
        bom.add_component(comp)

        # Check for per-component release property
        for prop in comp_data.get("properties", []):
            if prop.get("name") == "cosmo:release":
                bom._component_releases[comp.bom_ref] = prop.get("value", "")

    # Parse dependencies
    for dep in data.get("dependencies", []):
        ref = dep.get("ref", "")
        depends_on = dep.get("dependsOn", [])
        if ref:
            bom.set_dependencies(ref, depends_on)

    return bom


def _component_to_cdx(comp: Component, release: str | None = None) -> dict[str, Any]:
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

    # Only include hash if present
    if comp.sha256:
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

    # Only include distribution URL if present
    if comp.url:
        result["externalReferences"] = [{"type": "distribution", "url": comp.url}]

    # Properties
    properties: list[dict[str, str]] = []
    if comp.eol:
        properties.append({"name": "cosmo:eol", "value": comp.eol})
    if comp.status:
        properties.append({"name": "cosmo:status", "value": comp.status})
    if comp.sigstore_identity:
        properties.append({"name": "cosmo:sigstore:identity", "value": comp.sigstore_identity})
    if comp.sigstore_issuer:
        properties.append({"name": "cosmo:sigstore:issuer", "value": comp.sigstore_issuer})
    if comp.gpg:
        properties.append({"name": "cosmo:gpg", "value": comp.gpg})
    if comp.attestation_repo:
        properties.append({"name": "cosmo:attestation:repo", "value": comp.attestation_repo})
    if release:
        properties.append({"name": "cosmo:release", "value": release})

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

    # Add disabled
    for pkg, prefixes in sorted(bom._disabled.items()):
        if prefixes:
            meta_props.append({"name": f"cosmo:disabled:{pkg}", "value": ",".join(prefixes)})

    # Add latest
    for key, version in sorted(bom._latest.items()):
        pkg, minor = key.split(":", 1)
        meta_props.append({"name": f"cosmo:latest:{pkg}:{minor}", "value": version})

    # Build metadata component
    meta_component: dict[str, Any] = {
        "type": "application",
        "name": "cosmo-python",
        "publisher": "metaist",
    }
    if bom._release:
        meta_component["version"] = bom._release

    # Build components in topological order (by level, then alphabetical)
    # This makes the JSON reflect actual build order
    components: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    # Get toposorted order for deps
    ordered_names = bom.toposorted_names()

    # Add components in order (all versions of each name together)
    for name in ordered_names:
        if name in seen_names:
            continue
        seen_names.add(name)
        for c in sorted(bom.get_components(name), key=lambda x: version_key(x.version)):
            release = bom._component_releases.get(c.bom_ref)
            components.append(_component_to_cdx(c, release))

    # Add any remaining components not in toposort (shouldn't happen normally)
    for c in bom.all_components():
        name = c.name
        if name not in seen_names:
            seen_names.add(name)
            release = bom._component_releases.get(c.bom_ref)
            components.append(_component_to_cdx(c, release))

    result: dict[str, Any] = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": bom._version,
        "metadata": {
            "timestamp": bom.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": meta_component,
            "properties": meta_props,
        },
        "components": components,
    }

    # Add dependencies
    # Sort dependencies by ref: python first, then alpha, each with version_key
    def dep_sort_key(
        item: tuple[str, list[str]],
    ) -> tuple[int, str, list[tuple[int, int | str]]]:
        ref = item[0]
        name, version = ref.split("@", 1)
        if name == "cosmo-python":
            order = 0
        elif name == "python":
            order = 1
        else:
            order = 2
        return (order, name, version_key(version))

    deps_list: list[dict[str, Any]] = []
    for ref, depends_on in sorted(bom._dependencies.items(), key=dep_sort_key):
        deps_list.append({"ref": ref, "dependsOn": sorted(depends_on)})
    if deps_list:
        result["dependencies"] = deps_list

    if path:
        Path(path).write_text(json_dumps(result) + "\n")

    return result
