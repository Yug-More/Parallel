"""Untrusted PDF parser subprocess: no shell, short deadline, bounded resources/I/O.

The parser never runs in the HTTP/worker process. This is a resource boundary,
not a filesystem/network sandbox. No links, attachments or PDF scripts execute.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

MAX_PAGES = 30


def extract_pdf(raw, timeout=8):
    if not raw.startswith(b"%PDF-") or len(raw) > 524288:
        raise ValueError("pdf_invalid")
    try:
        result = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("pdf_parser.py"))],
            input=raw,
            capture_output=True,
            timeout=timeout,
            env={"PATH": os.defpath},
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("pdf_timeout") from None
    if result.returncode or len(result.stdout) > 1_300_000:
        raise ValueError("pdf_resource_limit")
    try:
        payload = json.loads(result.stdout)
        if "error" in payload:
            raise ValueError(payload["error"])
        pages = payload["pages"]
        if not 1 <= len(pages) <= MAX_PAGES or sum(len(p[1]) for p in pages) > 200000:
            raise ValueError("text_limit")
        return pages
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ValueError("pdf_invalid") from None
