# Humanize Korean

두 한국어 윤문 프로젝트의 장점을 하나로 합친 Codex 전역 스킬입니다. 원문의 사실과 의미는 지키면서 AI 특유의 상투어·번역투·기계적 구조를 덜어 내고, 필요하면 맞춤법 교정과 문체 변환까지 한 흐름에서 처리합니다.

기반 프로젝트:

- [epoko77-ai/im-not-ai](https://github.com/epoko77-ai/im-not-ai) — AI 문체 분류, 국소 편집, 변경률·사실 보존 검증
- [amondnet/yoonmoon](https://github.com/amondnet/yoonmoon) — 교정, 번역 윤문, AI 티 제거, 문체 변환, 진단 라우팅

## 주요 기능

- `AI스럽지 않게`, `사람이 쓴 것처럼`, `ChatGPT 티 제거` 같은 자연어 요청으로 자동 호출
- AI 티 제거, 전체 윤문, 교정·교열, 번역 윤문, 문체 변환, AI 문체 신호 진단의 6개 모드
- 고유명사·수치·날짜·인용·URL·코드·전문 용어 보호
- 보수·기본·적극의 3단계 윤문 강도
- 원문 장르와 존댓말·반말·격식 수준 유지
- 과윤문 변경률과 보호 요소 변조를 잡는 결정적 검사 스크립트
- `~로 이어진다`, `~로 이어지게 한다`처럼 반복되는 만능 결과 동사도 별도 패턴으로 억제

이 스킬은 AI 탐지기 회피가 아니라 사람이 읽기 편한 자연스러운 한국어를 목표로 합니다. 가짜 경험, 감정, 수치, 오탈자를 만들어 사람 글처럼 위장하지 않습니다.

## 설치

Codex에 다음과 같이 요청하면 됩니다.

> `nathankim0/humanize-korean 저장소의 humanize-korean 스킬을 전역 설치해줘.`

CLI로 설치하려면 Codex 기본 스킬 설치기를 사용합니다.

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo nathankim0/humanize-korean \
  --path humanize-korean
```

설치 위치는 `${CODEX_HOME:-$HOME/.codex}/skills/humanize-korean`입니다. 이미 같은 이름의 스킬이 있으면 먼저 백업하거나 이름 충돌을 해소해야 합니다. 새 설치본은 다음 Codex 대화부터 자동으로 발견됩니다.

## 사용 예시

```text
이 글 AI스럽지 않게 자연스럽게 윤문해줘.
```

```text
맞춤법부터 번역투, AI 티까지 싹 다듬어줘. 강도는 보수로.
```

```text
이 기계번역 문장을 한국 사람이 처음부터 쓴 것처럼 다듬어줘. 원문 의미는 절대 바꾸지 마.
```

```text
이 공지문을 하십시오체로 정리하되 수치와 날짜는 그대로 둬.
```

```text
이 글에 AI 문체 신호가 있는지 단정하지 말고 근거와 신뢰도를 알려줘.
```

명시적으로 호출하려면 `$humanize-korean`을 붙입니다.

```text
$humanize-korean 이 문단을 AI 같지 않게 윤문해줘. 결과만 보여줘.
```

## 처리 모드

| 모드 | 대표 요청 | 처리 범위 |
| --- | --- | --- |
| AI 티 제거 | AI스럽지 않게, 사람처럼 | 상투어·번역투·구조·리듬을 국소 수정 |
| 전체 윤문 | 싹 다듬어줘, 풀코스 | 교정 → 번역투 → AI 티 → 요청 시 문체 변환 |
| 교정·교열 | 맞춤법, 띄어쓰기, 비문 | 객관적 규범 오류만 수정 |
| 번역 윤문 | 번역투, 직역체, MTPE | 정보는 유지하고 번역체만 수정 |
| 문체 변환 | 존댓말, 반말, 이메일 톤 | 목표 register와 매체 톤으로 변환 |
| 신호 진단 | AI가 쓴 것 같아? | 확률적 문체 신호만 진단하고 원문은 유지 |

## 안전 검증

파일 윤문 결과는 포함된 검사기로 확인할 수 있습니다.

```bash
python3 humanize-korean/scripts/audit_revision.py \
  --before original.md \
  --after original.humanized.md
```

검사기는 다음을 확인합니다.

- 수치·날짜·인용·URL·이메일·코드·약어의 누락 또는 추가
- 원문 대비 변경률
- 30% 이상 과윤문 경고, 50% 이상 결과 거부

명시적 문체 변환처럼 넓은 수정이 정상인 작업은 `--allow-wide-change`로 변경률 게이트만 면제할 수 있습니다. 보호 요소 검사는 계속 적용됩니다.

## 저장소 구조

```text
humanize-korean/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── core-workflow.md
│   ├── ai-tell-rulebook.md
│   ├── proofreading-rules.md
│   ├── translationese-rules.md
│   ├── register-guide.md
│   └── detection-guide.md
└── scripts/audit_revision.py
```

## 라이선스

MIT License. 원본 프로젝트의 저작권과 라이선스는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 명시했습니다.
