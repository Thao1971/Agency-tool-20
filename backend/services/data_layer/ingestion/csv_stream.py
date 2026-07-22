"""Streaming CSV reader for Iberinform deliveries (sep ';', mixed UTF-8/latin-1).

Yields dict rows without ever materializing the whole file in RAM (O(1) memory).
"""

import csv
from typing import Dict, Iterator, Tuple


def detect_encoding(path: str) -> str:
    with open(path, "rb") as fh:
        sample = fh.read(65536)
    try:
        sample.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def stream_rows(path: str) -> Iterator[Dict[str, str]]:
    enc = detect_encoding(path)
    with open(path, encoding=enc, errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            yield row


def count_rows(path: str) -> int:
    enc = detect_encoding(path)
    with open(path, encoding=enc, errors="replace") as fh:
        return max(0, sum(1 for _ in fh) - 1)


def file_stats(path: str) -> Tuple[str, int]:
    """Returns (sha256_hex, bytes)."""
    import hashlib
    import os
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest(), os.path.getsize(path)
