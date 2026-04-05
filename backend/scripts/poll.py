#!/usr/bin/env python3
"""Poller entry point."""


def main():
    from app.services.poller import main as _main
    _main()


if __name__ == "__main__":
    main()
