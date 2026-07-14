#!/usr/bin/env python3
"""Entry shim — production app is Flask via hibs_racing.web (not FastAPI)."""
from hibs_racing.cli import main

if __name__ == "__main__":
    main()
