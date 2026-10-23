"""Legacy provider diagnostic intentionally disabled; never access real accounts."""


def main():
    raise SystemExit(
        "Plivo diagnostics are disabled. Rotate historically exposed credentials; see docs/SECURITY.md."
    )


if __name__ == "__main__":
    main()
