# hackernews-launch

## 목적

Hacker News에서 Show HN 포스트 초안과 댓글 참여 기회를 발굴한다. 기술적·빌더 톤의 포스트 변형을 작성한다. Okara Hacker News Agent에 해당하는 기능.

> ⚠️ **플랫폼 리스크**: HN은 마케팅 톤을 즉시 감지하고 flag한다. 모든 초안은 인간 검토 후 클라이언트가 직접 게시한다.

## 에이전트 조합

```
community-manager → reviewer
```

## 입력

```
BRAND: {client}        # 클라이언트명
PRODUCT_URL: {url}     # 제품/사이트 URL
ANGLE: {angle}         # Show HN 각도 (기술 스택/만든 이유/배운 점 등, 선택)
MODE: {mode}           # show-hn / comment-scan / both (기본: both)
```

## 참조 문서

- `clients/{client}/config.md` — 제품, 기술 스택
- `knowledge-base/{client}/insights.md` — 이전 HN 반응

## 절차

### 1단계: Show HN 초안 (MODE=show-hn 또는 both)
- **HN 톤 5원칙**:
  1. 제목은 사실 진술: "Show HN: {무엇} — {한 줄 설명}" (과장·숫자 과시 금지)
  2. 본문은 무엇을 만들었는지 → 왜 만들었는지 → 어떻게 작동하는지 (기술 디테일)
  3. 약점/한계를 먼저 밝히면 신뢰 상승
  4. "피드백 부탁드립니다"로 마무리 — CTA 과다 금지
  5. 창업자 본인 1인칭
- 제목 초안 3개 + 본문 초안 1개 (300단어 이내)
- 첫 댓글 초안 (맥락 보충용 — HN 관행)

### 2단계: 댓글 참여 기회 (MODE=comment-scan 또는 both)
- `site:news.ycombinator.com {주제}` 검색으로 관련 활성 스레드 수집
- 전문성을 보여줄 수 있는 스레드 3-5개 선정 + 댓글 초안
- 제품 언급은 프로필/맥락상 자연스러울 때만, 1회

### 3단계: 타이밍·전략 메모
- HN 트래픽 피크: 미국 동부 오전 (평일) [추정]
- 재게시 규칙, Show HN 가이드라인 준수 여부 체크

### 4단계: 리스크 검토
- reviewer 검증:
  - [ ] 마케팅 어휘("혁신", "최고", "게임체인저") 없는가
  - [ ] 기술 디테일이 실제로 구체적인가
  - [ ] 인간 게시 게이트가 명시되어 있는가

## 출력

`outputs/{client}/community/{YYYYMMDD}_hackernews-launch.md`

```markdown
# HN 기회 리포트 — {client} {date}
## Show HN 초안
### 제목 후보 3개
### 본문 초안
### 첫 댓글 초안
## 댓글 참여 기회
### 스레드 1: {title} — 댓글 초안
## 타이밍·전략 메모
## 게시 전 체크포인트
```

## 금지 사항

- 자동 게시·다중 계정·업보트 요청 금지
- 마케팅 톤 초안은 FAIL — reviewer가 반려
- 경쟁사 깎아내리기 금지
