"""Scan tracked/current source without printing suspected values.

This is a repository guardrail, not a complete credential audit or history scan.
Provider-side rotation remains necessary for historical exposure.
"""

import re
import subprocess
from pathlib import Path

PATTERNS = [
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{24,})\b"),
    re.compile(r"\bMA[A-Z0-9]{18,}\b"),
    re.compile(r"auth\s*=\s*\(\s*['\"][^'\"]+['\"]\s*,\s*['\"][^'\"]+['\"]"),
    re.compile(r"(?i)(?:api_key|auth_token|secret_key)\s*=\s*['\"]([^'\"]{24,})['\"]"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def suspicious_lines(content):
    findings = []
    for number, line in enumerate(content.splitlines(), 1):
        for pattern in PATTERNS:
            match = pattern.search(line)
            if match:
                # Explicit non-provider signing keys used by isolated tests only.
                value = match.group(1) if match.lastindex else match.group(0)
                if value.startswith(("test-only-", "e2e-only-")):
                    continue
                findings.append(number)
                break
    return findings


def main():
    root = Path(__file__).resolve().parents[1]
    names = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
        )
        .decode()
        .split("\0")
    )
    findings = []
    for name in set(names):
        path = root / name
        if not name or not path.is_file():
            continue
        try:
            content = path.read_text()
        except UnicodeError:
            continue
        findings.extend(f"{name}:{line}" for line in suspicious_lines(content))
    if findings:
        print(
            "Potential credentials found (values redacted):\n"
            + "\n".join(sorted(findings))
        )
        raise SystemExit(1)
    print(
        "Secret guard passed: no supported credential patterns found in current source."
    )


if __name__ == "__main__":
    main()
