"""CLI for querying CycloneDX BOM data from bash scripts."""

from __future__ import annotations

import sys

from ci import common

from .io import load


def main() -> int:
    """CLI for querying version data from bash scripts.

    Usage:
        python -m ci.cdx default <pkg>                  # Get default version
        python -m ci.cdx latest <pkg> <minor>           # Get latest patch version
        python -m ci.cdx sha256 <pkg> <version>         # Get SHA256 hash
        python -m ci.cdx url <pkg> <version>            # Get download URL
        python -m ci.cdx gpg <pkg> <version>            # Get GPG fingerprint
        python -m ci.cdx sigstore-identity <pkg> <ver>  # Get sigstore identity
        python -m ci.cdx sigstore-issuer <pkg> <ver>    # Get sigstore issuer
        python -m ci.cdx versions                       # List all Python versions
        python -m ci.cdx build-order <pkg> <ver> [--exclude <name>...]
                                                        # Get deps in build order
    """
    args = sys.argv[1:]
    if not args:
        print(__doc__ or "Usage: python -m ci.cdx <command> [args]", file=sys.stderr)
        return 1

    cmd = args[0]
    bom = load(common.CDX_FILE)

    if cmd == "default" and len(args) == 2:
        pkg = args[1]
        result = bom.get_default_version(pkg)
        if result:
            print(result)
            return 0
        return 1

    if cmd == "latest" and len(args) == 3:
        pkg, minor = args[1], args[2]
        result = bom.get_latest_version(pkg, minor)
        if result:
            print(result)
            return 0
        return 1

    if cmd == "sha256" and len(args) == 3:
        pkg, version = args[1], args[2]
        comp = bom.get_component(pkg, version)
        if comp and comp.sha256:
            print(comp.sha256)
            return 0
        return 1

    if cmd == "url" and len(args) == 3:
        pkg, version = args[1], args[2]
        comp = bom.get_component(pkg, version)
        if comp and comp.url:
            print(comp.url)
            return 0
        return 1

    if cmd == "gpg" and len(args) == 3:
        pkg, version = args[1], args[2]
        comp = bom.get_component(pkg, version)
        if comp and comp.gpg:
            print(comp.gpg)
            return 0
        return 1

    if cmd == "sigstore-identity" and len(args) == 3:
        pkg, version = args[1], args[2]
        comp = bom.get_component(pkg, version)
        if comp and comp.sigstore_identity:
            print(comp.sigstore_identity)
            return 0
        return 1

    if cmd == "sigstore-issuer" and len(args) == 3:
        pkg, version = args[1], args[2]
        comp = bom.get_component(pkg, version)
        if comp and comp.sigstore_issuer:
            print(comp.sigstore_issuer)
            return 0
        return 1

    if cmd == "versions" and len(args) == 1:
        versions = bom.python_versions()
        print(" ".join(versions))
        return 0

    if cmd == "build-order" and len(args) >= 3:
        pkg, version = args[1], args[2]
        # Parse --exclude options
        excludes = set()
        i = 3
        while i < len(args):
            if args[i] == "--exclude" and i + 1 < len(args):
                excludes.add(args[i + 1])
                i += 2
            else:
                i += 1
        ref = f"{pkg}@{version}"
        order = bom.build_order(ref)
        for level, dep in order:
            name = dep.split("@")[0]
            if name not in excludes:
                print(f"{level} {dep}")
        return 0

    print(f"Unknown command: {' '.join(args)}", file=sys.stderr)
    return 1
