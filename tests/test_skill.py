"""humanize-korean의 결정적 스크립트 회귀 테스트."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "humanize-korean" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_revision  # noqa: E402
import reassemble  # noqa: E402
import segment  # noqa: E402


SAMPLES = (
    "오늘은 날씨가 좋다. 내일은 비가 온다고 한다.\n",
    "질문인가요? 그렇다! 줄임표도… 끝.\n\n다음 문단입니다.\n",
    "# 제목\n\n본문 첫 문장이다. 두 번째 문장.\n\n- 항목 하나\n- 항목 둘\n",
    "```python\nprint('코드는 그대로.')\n```\n바깥 문장.\n",
    "오늘 날씨 좋다\n내일은 비\n모레는 맑음",
    "A.I. 기술은 좋다. U.S.A. 시장도 크다. e.g. 같은 표현이다.\n",
    "1980. 그해 여름은 더웠다. 끝.\n",
    "이것은 긴 문장인데\n줄바꿈으로 나뉘어 있다. 둘째 문장.\n",
    "",
)


class SegmentTests(unittest.TestCase):
    def test_lossless_roundtrip(self) -> None:
        for sample in SAMPLES:
            self.assertEqual(segment.reconstruct(segment.segment(sample)), sample)

    def test_abbreviation_and_year_do_not_oversplit(self) -> None:
        abbreviations = [
            item["core"]
            for item in segment.segment(SAMPLES[5])
            if item["kind"] == "prose"
        ]
        self.assertEqual(len(abbreviations), 3)
        years = [
            item["core"]
            for item in segment.segment(SAMPLES[6])
            if item["kind"] == "prose"
        ]
        self.assertEqual(years, ["1980. 그해 여름은 더웠다.", "끝."])

    def test_markdown_structure_is_protected(self) -> None:
        items = segment.segment(SAMPLES[2])
        structure = [item["raw"] for item in items if item["kind"] == "structure"]
        self.assertIn("# 제목\n", structure)
        self.assertIn("- 항목 하나\n", structure)


class ReassembleTests(unittest.TestCase):
    def _prepare(self, directory: str, text: str) -> tuple[Path, Path]:
        input_path = Path(directory) / "input.md"
        input_path.write_text(text, encoding="utf-8")
        self.assertEqual(segment.main([str(input_path), "--outdir", directory]), 0)
        return Path(directory) / "segments.json", Path(directory) / "worksheet.md"

    def test_blank_revisions_reproduce_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            segments_path, worksheet_path = self._prepare(directory, SAMPLES[0])
            output_path = Path(directory) / "final.md"
            self.assertEqual(
                reassemble.main(
                    [str(segments_path), str(worksheet_path), "--out", str(output_path)]
                ),
                0,
            )
            self.assertEqual(output_path.read_text(encoding="utf-8"), SAMPLES[0])

    def test_missing_sentence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            segments_path, worksheet_path = self._prepare(directory, "문장 하나. 문장 둘.\n")
            worksheet = worksheet_path.read_text(encoding="utf-8")
            last_header = worksheet.rfind("<!-- SEG 2 prose -->")
            worksheet_path.write_text(worksheet[:last_header], encoding="utf-8")
            self.assertEqual(
                reassemble.main([str(segments_path), str(worksheet_path)]), 2
            )

    def test_overedit_fails_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            segments_path, worksheet_path = self._prepare(directory, "짧다.\n")
            worksheet = worksheet_path.read_text(encoding="utf-8")
            worksheet_path.write_text(
                worksheet.replace(
                    "윤문: ",
                    "윤문: 원문과 전혀 관계없는 매우 긴 문장으로 통째로 바꿨다.",
                    1,
                ),
                encoding="utf-8",
            )
            output_path = Path(directory) / "rejected.md"
            self.assertEqual(
                reassemble.main(
                    [str(segments_path), str(worksheet_path), "--out", str(output_path)]
                ),
                3,
            )
            self.assertFalse(output_path.exists())

    def test_duplicate_sentence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            segments_path, worksheet_path = self._prepare(directory, "문장 하나.\n")
            worksheet = worksheet_path.read_text(encoding="utf-8")
            duplicate = "\n<!-- SEG 1 prose -->\n원문: 문장 하나.\n윤문: 문장 하나.\n규칙: 변경없음\n"
            worksheet_path.write_text(worksheet + duplicate, encoding="utf-8")
            self.assertEqual(
                reassemble.main([str(segments_path), str(worksheet_path)]), 2
            )

    def test_exact_change_limit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            segments_path, worksheet_path = self._prepare(directory, "가나")
            worksheet = worksheet_path.read_text(encoding="utf-8")
            worksheet_path.write_text(
                worksheet.replace("윤문: ", "윤문: 가다", 1), encoding="utf-8"
            )
            self.assertEqual(
                reassemble.main([str(segments_path), str(worksheet_path)]), 3
            )


class AuditTests(unittest.TestCase):
    def test_protected_elements_pass_when_unchanged(self) -> None:
        before = "2026년 7월 23일 GPT-5는 1.8초 걸린다. `POST /api/chat` 참고."
        after = "2026년 7월 23일 GPT-5 응답에는 1.8초가 걸린다. `POST /api/chat` 참고."
        result, code = audit_revision.audit(before, after, 0.30, 0.50, False)
        self.assertEqual(code, 0)
        self.assertFalse(result.missing)
        self.assertFalse(result.added)

    def test_protected_element_change_rejects(self) -> None:
        before = "응답 시간은 1.8초다."
        after = "응답 시간은 2.1초다."
        result, code = audit_revision.audit(before, after, 0.30, 0.50, False)
        self.assertEqual(code, 2)
        self.assertTrue(result.missing)
        self.assertTrue(result.added)

    def test_relative_file_path_change_rejects(self) -> None:
        before = "humanize-korean/scripts/segment.py를 실행한다."
        after = "humanize-korean/scripts/reassemble.py를 실행한다."
        result, code = audit_revision.audit(before, after, 0.30, 0.50, False)
        self.assertEqual(code, 2)
        self.assertTrue(result.missing)
        self.assertTrue(result.added)

    def test_number_attached_to_korean_word_is_protected(self) -> None:
        before = "제1항에 따라 20명이 참여했다."
        after = "제2항에 따라 20명이 참여했다."
        result, code = audit_revision.audit(before, after, 0.30, 0.50, False)
        self.assertEqual(code, 2)
        self.assertTrue(result.missing)
        self.assertTrue(result.added)

    def test_new_conventional_naming_claim_rejects(self) -> None:
        before = (
            "누가복음 11장 5절부터 13절에는 한 사람이 밤중에 벗을 찾아가는 "
            "장면이 나온다. 본문을 읽고 기도에 관해 묵상한다. "
            "본문이 직접 말하는 내용만 차례로 살펴본다."
        )
        after = (
            "누가복음 11장 5절부터 13절에는 한 사람이 밤중에 벗을 찾아가는 "
            "장면이 나온다. 이 본문은 보통 한밤중 친구 이야기로 소개됩니다. "
            "본문을 읽고 기도에 관해 묵상한다. 본문이 직접 말하는 내용만 "
            "차례로 살펴본다."
        )
        result, code = audit_revision.audit(before, after, 0.30, 0.50, False)
        self.assertEqual(code, 2)
        self.assertTrue(result.new_knowledge_claims)
        self.assertIn("conventional_naming", result.new_knowledge_claims[0])

    def test_existing_conventional_claim_is_not_counted_as_new(self) -> None:
        before = (
            "이 장면은 보통 밤중의 요청으로 소개됩니다. "
            "이 문장은 원문에 이미 있는 주장이다. 뒤 문장도 그대로 둔다."
        )
        after = (
            "이 장면은 흔히 밤중의 요청으로 불립니다. "
            "이 문장은 원문에 이미 있는 주장이다. 뒤 문장도 그대로 둔다."
        )
        result, _ = audit_revision.audit(before, after, 0.30, 0.50, False)
        self.assertFalse(result.new_knowledge_claims)

    def test_other_new_knowledge_claim_types_reject(self) -> None:
        before = (
            "원문은 확인할 수 있는 장면만 설명한다. "
            "추가 배경이나 사람들의 평가는 제시하지 않는다."
        )
        additions = (
            "전통적으로 이 이름이 사용되어 왔다.",
            "전문가들은 이 장면을 같은 뜻으로 해석합니다.",
        )
        for addition in additions:
            with self.subTest(addition=addition):
                result, code = audit_revision.audit(
                    before,
                    f"{before} {addition}",
                    0.30,
                    0.50,
                    False,
                )
                self.assertEqual(code, 2)
                self.assertTrue(result.new_knowledge_claims)


class RulebookTests(unittest.TestCase):
    def test_concrete_fact_rule_is_linked_across_workflow(self) -> None:
        skill = (ROOT / "humanize-korean" / "SKILL.md").read_text(encoding="utf-8")
        sentence_rules = (
            ROOT / "humanize-korean" / "references" / "sentence-rules.md"
        ).read_text(encoding="utf-8")
        ai_rules = (
            ROOT / "humanize-korean" / "references" / "ai-tell-rulebook.md"
        ).read_text(encoding="utf-8")

        self.assertIn("구체적인 기능이나 사실을 막연한 평가로 바꾸지 않는다", skill)
        self.assertIn("S-27. 구체적인 사실을 가리는 추상 평가", sentence_rules)
        self.assertIn("N. 관찰 가능한 사실을 감상으로 바꾸는 문장", ai_rules)
        self.assertIn("구절마다 해설을 볼 수 있었어요", sentence_rules)

    def test_evidence_boundary_rule_is_linked_across_workflow(self) -> None:
        skill = (ROOT / "humanize-korean" / "SKILL.md").read_text(encoding="utf-8")
        workflow = (
            ROOT / "humanize-korean" / "references" / "core-workflow.md"
        ).read_text(encoding="utf-8")
        sentence_rules = (
            ROOT / "humanize-korean" / "references" / "sentence-rules.md"
        ).read_text(encoding="utf-8")
        ai_rules = (
            ROOT / "humanize-korean" / "references" / "ai-tell-rulebook.md"
        ).read_text(encoding="utf-8")

        self.assertIn("근거 지도", skill)
        self.assertIn("근거 경계 불변", workflow)
        self.assertIn("S-28. 편집 표지를 본문 사실로 승격", sentence_rules)
        self.assertIn("O. 출처 없는 통용성·합의·배경 문장", ai_rules)

if __name__ == "__main__":
    unittest.main(verbosity=2)
