"""Bill of Materials class for managing components and relationships."""

from __future__ import annotations

from dataclasses import dataclass, field

from .component import Component


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
    >>> bom.set_disabled("python", ["3.9"])
    >>> bom.get_disabled("python")
    ['3.9']
    >>> bom.is_disabled("python", "3.9.1")
    True
    >>> bom.is_disabled("python", "3.10.1")
    False
    """

    # Internal storage
    _components: dict[str, dict[str, Component]] = field(default_factory=dict)
    _defaults: dict[str, str] = field(default_factory=dict)
    _latest: dict[str, str] = field(default_factory=dict)  # "python:3.13" -> "3.13.11"
    _dependencies: dict[str, list[str]] = field(default_factory=dict)
    _disabled: dict[str, list[str]] = field(default_factory=dict)  # package -> [version prefixes]
    _component_releases: dict[str, str] = field(
        default_factory=dict
    )  # "python@3.13.11" -> "20260115-134426"

    # Metadata
    timestamp: str | None = None
    _release: str | None = None  # Release tag for manifest
    _version: int = 1  # BOM revision number

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
        """Get all components in the BOM, sorted: cosmo-python, python, then alpha."""
        from ci.common import version_key

        def sort_key(c: Component) -> tuple[int, str, list[tuple[int, int | str]]]:
            # cosmo-python first (0), python second (1), everything else alpha (2)
            if c.name == "cosmo-python":
                order = 0
            elif c.name == "python":
                order = 1
            else:
                order = 2
            return (order, c.name, version_key(c.version))

        result: list[Component] = []
        for versions in self._components.values():
            result.extend(versions.values())
        return sorted(result, key=sort_key)

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

    def build_order(self, ref: str) -> list[tuple[int, str]]:
        """Get dependencies in build order (topological sort) with parallel levels.

        Returns list of (level, ref) tuples. Items at the same level can be
        built in parallel; higher levels depend on lower levels completing.
        """
        from graphlib import TopologicalSorter

        graph: dict[str, set[str]] = {}

        def add_deps(r: str) -> None:
            if r in graph:
                return
            deps = self.get_dependencies(r)
            graph[r] = set(deps)
            for dep in deps:
                add_deps(dep)

        add_deps(ref)

        # Use iterative approach to get levels
        ts = TopologicalSorter(graph)
        ts.prepare()
        result: list[tuple[int, str]] = []
        level = 0
        while ts.is_active():
            ready = list(ts.get_ready())
            for item in ready:
                result.append((level, item))
                ts.done(item)
            level += 1

        return result

    # Disabled versions

    def set_disabled(self, name: str, prefixes: list[str]) -> None:
        """Set disabled version prefixes for a package."""
        self._disabled[name] = prefixes

    def get_disabled(self, name: str) -> list[str]:
        """Get disabled version prefixes for a package."""
        return self._disabled.get(name, [])

    def is_disabled(self, name: str, version: str) -> bool:
        """Check if a version is disabled (matches any disabled prefix)."""
        for prefix in self.get_disabled(name):
            if version.startswith(prefix):
                return True
        return False

    # Convenience methods

    def python_versions(self) -> list[str]:
        """Get all Python versions in the BOM."""
        return sorted(c.version for c in self.get_components("python"))

    def python_minors(self) -> list[str]:
        """Get all Python minor versions (e.g., ['3.10', '3.11', ...])."""
        versions = self.python_versions()
        return sorted(set(".".join(v.split(".")[:2]) for v in versions))

    def upstream_table(self) -> str:
        """Generate upstream sources table.

        Columns: Dependency (linked), Version, Integrity, Signature, License.
        """
        lines = [
            "| Dependency | Version | Integrity | Signature | License |",
            "|------------|---------|-----------|-----------|---------|",
        ]

        for name in self.component_names():
            comp = self.get_default_component(name)
            if not comp:  # pragma: no cover - component_names always have defaults
                continue
            # Use version range for python
            if name == "python":
                minors = self.python_minors()
                version = f"{minors[0]}–{minors[-1]}" if minors else comp.version
            else:
                version = comp.version

            lines.append(
                f"| [{comp.display_name}]({comp.url}) | {version} "
                f"| SHA256 | {comp.signature_type} | {comp.license_link} |"
            )

        return "\n".join(lines)

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

        # Merge disabled (other wins for same package)
        result._disabled = {**self._disabled, **other._disabled}

        return result
