"""Finish a stalled Flutter SDK extraction.

Expand-Archive stalled partway through a 1.8 GB zip. Rather than restart from
zero, this diffs the archive against what is already on disk and extracts only
the missing or size-mismatched entries. Safe to re-run.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ZIP = Path(r"C:\src\flutter_windows_stable.zip")
DEST = Path(r"C:\src")


def main() -> int:
    if not ZIP.exists():
        print(f"missing archive: {ZIP}")
        return 1

    with zipfile.ZipFile(ZIP) as zf:
        entries = zf.infolist()
        total = len(entries)

        missing = []
        for info in entries:
            if info.is_dir():
                continue
            target = DEST / info.filename
            if not target.exists() or target.stat().st_size != info.file_size:
                missing.append(info)

        done = total - len(missing)
        print(f"archive entries : {total}")
        print(f"already on disk : {done}")
        print(f"to extract      : {len(missing)}")

        if not missing:
            print("nothing to do — extraction is complete")
            return 0

        for i, info in enumerate(missing, 1):
            zf.extract(info, DEST)
            if i % 500 == 0 or i == len(missing):
                print(f"  {i}/{len(missing)} extracted", flush=True)

    print("EXTRACT_COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
