#!/usr/bin/env python3
"""채운 윤문 작업표를 원문 구조에 맞춰 안전하게 재조립한다.

문장 수가 달라지거나 변경률이 한계를 넘으면 결과 파일을 쓰지 않는다. 보호 요소 검사는
재조립 후 audit_revision.py로 별도 실행한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys


SEG_HEADER_RE = re.compile(r"<!--\s*SEG\s+(\d+)\s+(prose|structure)")


def parse_worksheet(text: str) -> dict[int, tuple[str, str]]:
    """작업표에서 prose 세그먼트별 (윤문, 규칙)을 추출한다."""
    result: dict[int, tuple[str, str]] = {}
    current_index: int | None = None
    current_kind: str | None = None
    field: str | None = None
    revision_lines: list[str] = []
    rule_lines: list[str] = []

    def commit() -> None:
        if current_index is not None and current_kind == "prose":
            if current_index in result:
                raise ValueError(f"중복된 prose 세그먼트: {current_index}")
            result[current_index] = (
                "\n".join(revision_lines).strip(),
                "\n".join(rule_lines).strip(),
            )

    for line in text.splitlines():
        header = SEG_HEADER_RE.search(line)
        if header:
            commit()
            current_index = int(header.group(1))
            current_kind = header.group(2)
            field = None
            revision_lines = []
            rule_lines = []
            continue
        if current_kind != "prose":
            continue
        if line.startswith("원문:"):
            field = None
        elif line.startswith("윤문:"):
            field = "revision"
            revision_lines.append(line[len("윤문:") :].lstrip())
        elif line.startswith("규칙:"):
            field = "rule"
            rule_lines.append(line[len("규칙:") :].lstrip())
        elif field == "revision":
            revision_lines.append(line)
        elif field == "rule":
            rule_lines.append(line)
    commit()
    return result


def levenshtein(left: str, right: str) -> int:
    """두 문자열의 Levenshtein 편집 거리를 두 행 DP로 계산한다."""
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, 1):
        current = [row]
        for column, right_char in enumerate(right, 1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="윤문 작업표 재조립")
    parser.add_argument("segments", help="segment.py가 만든 segments.json")
    parser.add_argument("worksheet", help="채운 worksheet.md")
    parser.add_argument("--out", help="최종 파일. 기본값은 segments.json 옆 final.md")
    parser.add_argument("--warn-change", type=float, default=0.30)
    parser.add_argument("--max-change", type=float, default=0.50)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not 0 <= args.warn_change <= args.max_change <= 1:
        print("error: 변경률은 0 <= warn <= max <= 1이어야 합니다.", file=sys.stderr)
        return 4

    try:
        with open(args.segments, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        with open(args.worksheet, "r", encoding="utf-8") as handle:
            worksheet = handle.read()
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"error: 입력을 읽을 수 없습니다: {exc}", file=sys.stderr)
        return 4

    segments = data.get("segments")
    if not isinstance(segments, list):
        print("error: segments.json 형식이 올바르지 않습니다.", file=sys.stderr)
        return 4

    prose_ids = [int(item["idx"]) for item in segments if item.get("kind") == "prose"]
    try:
        revisions = parse_worksheet(worksheet)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    prose_id_set = set(prose_ids)
    missing = [index for index in prose_ids if index not in revisions]
    extra = [index for index in revisions if index not in prose_id_set]
    if missing or extra:
        print("error: 작업표의 문장 수가 원본과 다릅니다.", file=sys.stderr)
        if missing:
            print(f"누락 세그먼트: {missing}", file=sys.stderr)
        if extra:
            print(f"알 수 없는 세그먼트: {extra}", file=sys.stderr)
        return 2

    parts: list[str] = []
    total_chars = 0
    total_distance = 0
    changed_count = 0
    for item in segments:
        if item.get("kind") == "structure":
            parts.append(str(item["raw"]))
            continue
        index = int(item["idx"])
        original = str(item["core"])
        revision, _rule = revisions[index]
        revised = revision or original
        parts.append(str(item["prefix"]) + revised + str(item["suffix"]))
        total_chars += len(original)
        total_distance += levenshtein(original, revised)
        changed_count += revised != original

    change_rate = total_distance / total_chars if total_chars else 0.0
    if change_rate >= args.max_change:
        print(
            f"REJECT: 변경률 {change_rate:.1%} >= 한계 {args.max_change:.0%}. "
            "결과 파일을 쓰지 않습니다.",
            file=sys.stderr,
        )
        return 3

    output_path = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.segments)), "final.md"
    )
    try:
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write("".join(parts))
    except (OSError, UnicodeError) as exc:
        print(f"error: 결과 파일을 쓸 수 없습니다: {exc}", file=sys.stderr)
        return 4

    print(
        f"재조립 완료: {len(prose_ids)}문장, 변경 {changed_count}건, "
        f"변경률 {change_rate:.1%}"
    )
    print(f"final: {output_path}")
    if change_rate >= args.warn_change:
        print(
            f"WARN: 변경률 {change_rate:.1%} >= {args.warn_change:.0%}. "
            "원문과 의미를 다시 대조하세요.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
