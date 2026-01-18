"""Entry point for python -m ci.cdx."""

# no cover: start
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
# no cover: stop
