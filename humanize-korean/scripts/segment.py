#!/usr/bin/env python3
"""한국어 문서를 무손실 문장 세그먼트와 윤문 작업표로 나눈다.

원본의 조각을 순서대로 이으면 입력과 바이트가 아니라 유니코드 문자 기준으로 정확히 같아야 한다.
Markdown 헤딩·목록·표·인용·코드 펜스는 structure 세그먼트로 보호한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys


STRUCTURE_RE = re.compile(
    r"""^\s*(
        \#{1,6}\s        |
        [-*+]\s          |
        \d{1,2}[.)]\s    |
        >\s?             |
        \|               |
        (-{3,}|\*{3,}|_{3,})\s*$  |
        ```              |
        ~~~
    )""",
    re.VERBOSE,
)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
SENT_END_RE = re.compile(r'([.?!…。]+["\'”’」』)\]]*)(\s+|$)')
ABBREV_RUN_RE = re.compile(r"(?:[A-Za-z]{1,2}\.){2,}$")
ABBREV_WORD_RE = re.compile(
    r"(?:^|[\s(\"'\[])(vs|etc|cf|al|et|Dr|Mr|Mrs|Ms|St|No|Fig|Vol|pp|eq)\.$",
    re.IGNORECASE,
)


def _is_abbrev_dot(upto: str) -> bool:
    """현재 마침표가 영문 약어의 일부인지 확인한다."""
    return bool(ABBREV_RUN_RE.search(upto[-40:]) or ABBREV_WORD_RE.search(upto))


def _split_lines(prefix: str, core: str, trail: str) -> list[tuple[str, str, str]]:
    """종결 부호가 없는 여러 물리 줄을 무손실 줄 단위로 나눈다."""
    pieces = core.splitlines(keepends=True)
    result: list[tuple[str, str, str]] = []
    for index, piece in enumerate(pieces):
        if piece.endswith("\n"):
            content, suffix = piece[:-1], "\n"
        else:
            content, suffix = piece, ""
        if index == len(pieces) - 1:
            suffix += trail
        result.append((prefix if index == 0 else "", content, suffix))
    return result


def split_sentences(block: str) -> list[tuple[str, str, str]]:
    """prose 블록을 (prefix, core, suffix) 문장 튜플로 나눈다."""
    result: list[tuple[str, str, str]] = []
    lead_match = re.match(r"\s*", block)
    lead = lead_match.group(0) if lead_match else ""
    pending_prefix = lead
    last = len(lead)

    for match in SENT_END_RE.finditer(block, last):
        if match.group(1) == "." and (
            block[match.start(1) - 1 : match.start(1)].isdigit()
            or _is_abbrev_dot(block[last : match.start(2)])
        ):
            continue
        core = block[last : match.start(1)] + match.group(1)
        result.append((pending_prefix, core, match.group(2)))
        pending_prefix = ""
        last = match.end()

    if last < len(block):
        tail = block[last:]
        trail_match = re.search(r"\s*$", tail)
        trail = trail_match.group(0) if trail_match else ""
        core = tail[: len(tail) - len(trail)]
        if core and "\n" in core:
            result.extend(_split_lines(pending_prefix, core, trail))
        elif core:
            result.append((pending_prefix, core, trail))
        elif result:
            prefix, previous_core, suffix = result[-1]
            result[-1] = (prefix, previous_core, suffix + tail)
        else:
            result.append((pending_prefix, "", tail))
    return result


def segment(text: str) -> list[dict[str, object]]:
    """문서를 prose와 structure 세그먼트로 나눈다."""
    segments: list[dict[str, object]] = []
    index = 0
    in_fence = False
    prose_buffer: list[str] = []

    def flush_prose() -> None:
        nonlocal index
        if not prose_buffer:
            return
        block = "".join(prose_buffer)
        prose_buffer.clear()
        for prefix, core, suffix in split_sentences(block):
            index += 1
            segments.append(
                {
                    "idx": index,
                    "kind": "prose",
                    "prefix": prefix,
                    "core": core,
                    "suffix": suffix,
                }
            )

    for line in text.splitlines(keepends=True):
        is_fence = bool(FENCE_RE.match(line))
        is_structure = (
            in_fence
            or is_fence
            or line.strip() == ""
            or bool(STRUCTURE_RE.match(line))
        )
        if is_structure:
            flush_prose()
            index += 1
            segments.append({"idx": index, "kind": "structure", "raw": line})
            if is_fence:
                in_fence = not in_fence
        else:
            prose_buffer.append(line)
    flush_prose()
    return segments


def reconstruct(segments: list[dict[str, object]]) -> str:
    """세그먼트를 수정 없이 다시 연결한다."""
    parts: list[str] = []
    for item in segments:
        if item["kind"] == "prose":
            parts.append(str(item["prefix"]) + str(item["core"]) + str(item["suffix"]))
        else:
            parts.append(str(item["raw"]))
    return "".join(parts)


def build_worksheet(segments: list[dict[str, object]]) -> str:
    """에이전트가 한 문장씩 채우는 Markdown 작업표를 만든다."""
    lines = [
        "# 윤문 워크시트",
        "",
        "> 각 문장의 **윤문:**에 결과를, **규칙:**에 적용한 규칙 ID를 적습니다.",
        "> 고칠 게 없으면 원문을 그대로 옮기고 규칙에 `변경없음`을 적습니다.",
        "> 문장을 합치거나 나누거나 순서를 바꾸지 말고 structure 구간은 수정하지 않습니다.",
        "> 수치·고유명사·직접 인용·영어 약어·법령·코드·링크 대상을 보존합니다.",
        "",
        "---",
        "",
    ]
    for item in segments:
        if item["kind"] == "structure":
            shown = str(item["raw"]).rstrip("\n")
            lines.append(f"<!-- SEG {item['idx']} structure (수정 금지): {shown} -->")
            lines.append("")
            continue
        lines.append(f"<!-- SEG {item['idx']} prose -->")
        shown_core = re.sub(r"\s*\n\s*", " ", str(item["core"]))
        lines.append(f"원문: {shown_core}")
        lines.append("윤문: ")
        lines.append("규칙: ")
        lines.append("")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="한국어 문서 분절 및 윤문 작업표 생성")
    parser.add_argument("input", help="UTF-8 입력 텍스트 파일")
    parser.add_argument("--outdir", help="출력 디렉터리. 기본값은 입력 파일의 디렉터리")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        with open(args.input, "r", encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeError) as exc:
        print(f"error: 입력 파일을 읽을 수 없습니다: {exc}", file=sys.stderr)
        return 3

    segments = segment(text)
    if reconstruct(segments) != text:
        print("error: 분절한 조각을 다시 이은 결과가 원문과 다릅니다.", file=sys.stderr)
        return 2

    output_dir = args.outdir or os.path.dirname(os.path.abspath(args.input))
    try:
        os.makedirs(output_dir, exist_ok=True)
        segment_path = os.path.join(output_dir, "segments.json")
        with open(segment_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "source": os.path.abspath(args.input),
                    "n_prose": sum(item["kind"] == "prose" for item in segments),
                    "n_total": len(segments),
                    "segments": segments,
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
        worksheet_path = os.path.join(output_dir, "worksheet.md")
        with open(worksheet_path, "w", encoding="utf-8") as handle:
            handle.write(build_worksheet(segments))
    except (OSError, UnicodeError) as exc:
        print(f"error: 출력 파일을 만들 수 없습니다: {exc}", file=sys.stderr)
        return 3

    prose_count = sum(item["kind"] == "prose" for item in segments)
    print(f"문장 {prose_count}개로 나눔 (전체 조각 {len(segments)}개)")
    print(f"segments.json: {segment_path}")
    print(f"worksheet.md: {worksheet_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
