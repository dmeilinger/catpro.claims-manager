#!/usr/bin/env python3
"""CLI entry point for processing a single EML file."""

import sys


def main():
    from app.services.claim_processor import main as _main
    _main()


if __name__ == "__main__":
    main()
