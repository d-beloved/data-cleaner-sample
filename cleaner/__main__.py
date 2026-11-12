"""Command line entry point: python -m cleaner input.csv -o cleaned.csv"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import CleanConfig, clean, read_table, write_table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cleaner", description="Clean a CSV, Excel or JSON dataset.")
    parser.add_argument("input", help="Input file (.csv .tsv .xlsx .json .jsonl)")
    parser.add_argument("-o", "--output", help="Output file. Default: <input>_cleaned.<ext>")
    parser.add_argument("-c", "--config", help="JSON config file (see config.example.json)")
    parser.add_argument("-r", "--report", help="Write the cleaning report to this JSON file")
    args = parser.parse_args(argv)

    src = Path(args.input)
    out = Path(args.output) if args.output else src.with_name(f"{src.stem}_cleaned{src.suffix}")
    try:
        config = CleanConfig.from_dict(json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else None)
        df, report = clean(read_table(src), config)
        write_table(df, out)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{report['rows_in']} rows in, {report['rows_out']} rows out -> {out}")
    print(f"  duplicates removed: {report['duplicates_removed']}")
    print(f"  rows dropped: {report['rows_dropped'] or 'none'}")
    print(f"  null tokens replaced: {report['null_tokens_replaced']}")
    for warning in report.get("warnings", []):
        print(f"  warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
