#!/usr/bin/env python3
"""Test email injection entry point."""


def main():
    from app.services.test_email import main as _main
    _main()


if __name__ == "__main__":
    main()
