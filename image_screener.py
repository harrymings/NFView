"""Compatibility launcher; application code lives in nfview/."""
from nfview.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
