"""Internal stdin/stdout parser executable. Never accepts filenames or URLs."""

import io
import json
import sys


def parse():
    # Fail closed on platforms without Unix resource limits. Runtime support is
    # Linux/macOS; Windows should run the worker in a resource-limited container.
    import resource

    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    # Darwin cannot reliably lower AS/DATA below its pre-reserved address space;
    # it retains CPU/deadline/input/output limits. Use Linux for memory isolation.
    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    from pypdf import PdfReader

    raw = sys.stdin.buffer.read(524289)
    if len(raw) > 524288 or not raw.startswith(b"%PDF-"):
        return {"error": "pdf_invalid"}
    reader = PdfReader(io.BytesIO(raw), strict=True)
    if reader.is_encrypted:
        return {"error": "pdf_encrypted"}
    if len(reader.pages) > 30:
        return {"error": "pdf_page_limit"}
    pages, count = [], 0
    for number, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").replace("\r\n", "\n").replace("\r", "\n")
        text = "".join(c for c in text if ord(c) >= 32 or c in "\n\t")
        count += len(text)
        if count > 200000:
            return {"error": "text_limit"}
        pages.append([number, text])
    if not any(text.strip() for _, text in pages):
        return {"error": "pdf_no_text"}
    return {"pages": pages}


if __name__ == "__main__":
    try:
        result = parse()
    except MemoryError:
        result = {"error": "pdf_resource_limit"}
    except Exception:
        result = {"error": "pdf_invalid"}
    print(json.dumps(result))
