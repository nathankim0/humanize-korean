#!/usr/bin/env python3
"""한국어 윤문본의 변경률과 보호 요소 보존 여부를 결정적으로 검사한다.

이 검사는 의미 동등성을 증명하지 않는다. 수치, 인용, URL, 코드처럼 기계적으로
비교할 수 있는 요소의 누락·추가와 과도한 수정 범위를 조기에 잡는 안전 게이트다.

Exit codes:
  0: 통과
  1: 변경률 경고
  2: 보호 요소 변경 또는 변경률 중단 기준 초과
  3: 입력·실행 오류
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
from typing import Pattern


SUMMARY_RE = re.compile(r"<!--\s*HUMANIZE-SUMMARY\b.*?-->", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ProtectedPattern:
    kind: str
    regex: Pattern[str]


PATTERNS = (
    ProtectedPattern("fenced_code", re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)),
    ProtectedPattern("inline_code", re.compile(r"`[^`\n]+`")),
    ProtectedPattern("blockquote", re.compile(r"(?:^>[^\n]*(?:\n|$))+", re.MULTILINE)),
    ProtectedPattern("markdown_target", re.compile(r"(?<=\]\()[^)\s]+(?=\))")),
    ProtectedPattern(
        "url",
        re.compile(
            r"https?://[A-Za-z0-9]"
            r"(?:[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*[A-Za-z0-9/#%=])?"
        ),
    ),
    ProtectedPattern(
        "email",
        re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])"),
    ),
    ProtectedPattern("double_quote", re.compile(r'"[^"\n]+"|“[^”\n]+”')),
    ProtectedPattern("korean_quote", re.compile(r"「[^」\n]+」|『[^』\n]+』")),
    ProtectedPattern("acronym", re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,}(?:[-_.][A-Z0-9]+)*(?![A-Za-z0-9])")),
    ProtectedPattern(
        "version",
        re.compile(r"(?<![\w])v?\d+(?:\.\d+){1,}(?:[-+][A-Za-z0-9.-]+)?(?![\w])", re.IGNORECASE),
    ),
    ProtectedPattern(
        "number",
        re.compile(
            r"(?<![\w])(?:₩|\$|€|£)?[+-]?\d[\d,]*(?:\.\d+)?"
            r"(?:\s?(?:%|퍼센트|원|달러|유로|명|개|건|회|배|점|년|월|일|시|분|초|"
            r"kg|g|mg|km|m|cm|mm|GB|MB|KB|TB|Hz|px))?(?![\w])",
            re.IGNORECASE,
        ),
    ),
)


@dataclass
class AuditResult:
    before_chars: int
    after_chars: int
    change_rate: float
    protected_before: int
    protected_after: int
    missing: list[str]
    added: list[str]
    gate: str
    message: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def strip_summary(text: str) -> str:
    return SUMMARY_RE.sub("", text).strip()


def overlaps(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
    return any(start < used_end and end > used_start for used_start, used_end in occupied)


def extract_protected(text: str) -> Counter[str]:
    """우선순위가 높은 큰 span부터 추출해 중복 카운트를 피한다."""
    found: Counter[str] = Counter()
    occupied: list[tuple[int, int]] = []

    for pattern in PATTERNS:
        for match in pattern.regex.finditer(text):
            if overlaps(match.start(), match.end(), occupied):
                continue
            value = match.group(0)
            found[f"{pattern.kind}\0{value}"] += 1
            occupied.append((match.start(), match.end()))
    return found


def display_items(items: Counter[str], limit: int = 20) -> list[str]:
    rendered: list[str] = []
    shown_count = 0
    for key, count in sorted(items.items()):
        kind, value = key.split("\0", 1)
        compact = value.replace("\n", "\\n")
        if len(compact) > 120:
            compact = compact[:117] + "..."
        suffix = f" ×{count}" if count > 1 else ""
        rendered.append(f"{kind}: {compact}{suffix}")
        shown_count += count
        if len(rendered) == limit:
            remaining = sum(items.values()) - shown_count
            if remaining > 0:
                rendered.append(f"... 외 {remaining}건")
            break
    return rendered


def audit(
    before: str,
    after: str,
    warn_threshold: float,
    abort_threshold: float,
    allow_wide_change: bool,
) -> tuple[AuditResult, int]:
    before = strip_summary(before)
    after = strip_summary(after)
    protected_before = extract_protected(before)
    protected_after = extract_protected(after)
    missing_counter = protected_before - protected_after
    added_counter = protected_after - protected_before
    rate = 1.0 - SequenceMatcher(None, before, after, autojunk=False).ratio()

    missing = display_items(missing_counter)
    added = display_items(added_counter)

    if missing or added:
        gate = "REJECT"
        message = "보호 요소가 변경되었습니다. 해당 수정을 롤백하고 확인하세요."
        code = 2
    elif not allow_wide_change and rate >= abort_threshold:
        gate = "REJECT"
        message = "변경률이 중단 기준을 넘었습니다. 윤문본을 채택하지 마세요."
        code = 2
    elif not allow_wide_change and rate >= warn_threshold:
        gate = "WARN"
        message = "과윤문 가능성이 있습니다. 원문과 의미를 다시 대조하세요."
        code = 1
    else:
        gate = "PASS"
        message = "결정적 보호 요소와 변경률 게이트를 통과했습니다."
        code = 0

    result = AuditResult(
        before_chars=len(before),
        after_chars=len(after),
        change_rate=rate,
        protected_before=sum(protected_before.values()),
        protected_after=sum(protected_after.values()),
        missing=missing,
        added=added,
        gate=gate,
        message=message,
    )
    return result, code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="한국어 윤문 결과 안전 검사")
    parser.add_argument("--before", type=Path, required=True, help="원문 UTF-8 파일")
    parser.add_argument("--after", type=Path, required=True, help="윤문본 UTF-8 파일")
    parser.add_argument("--warn-threshold", type=float, default=0.30)
    parser.add_argument("--abort-threshold", type=float, default=0.50)
    parser.add_argument(
        "--allow-wide-change",
        action="store_true",
        help="명시적 문체 변환처럼 넓은 수정에서 변경률 게이트만 면제",
    )
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not 0 <= args.warn_threshold <= args.abort_threshold <= 1:
        print("error: 임계값은 0 <= warn <= abort <= 1이어야 합니다.", file=sys.stderr)
        return 3

    try:
        before = read_text(args.before)
        after = read_text(args.after)
    except (OSError, UnicodeError) as exc:
        print(f"error: 파일을 읽을 수 없습니다: {exc}", file=sys.stderr)
        return 3

    result, code = audit(
        before,
        after,
        args.warn_threshold,
        args.abort_threshold,
        args.allow_wide_change,
    )

    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        print(f"gate: {result.gate}")
        print(f"change_rate: {result.change_rate * 100:.1f}%")
        print(f"chars: {result.before_chars} -> {result.after_chars}")
        print(
            "protected: "
            f"{result.protected_before} -> {result.protected_after} "
            f"({'PASS' if not result.missing and not result.added else 'CHANGED'})"
        )
        for item in result.missing:
            print(f"missing: {item}")
        for item in result.added:
            print(f"added: {item}")
        print(result.message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
