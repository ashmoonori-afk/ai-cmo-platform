# x-twitter-daily

## 목적

X(Twitter) 전용 일일 포스트 초안을 브랜드 보이스로 작성한다. 제품 인사이트, 빌딩 인 퍼블릭, 업계 코멘트 등 X 네이티브 포맷에 맞춘 일일 드래프트. Okara X Agent에 해당하는 기능.

> 기존 `social-post.md`가 범용 멀티채널이라면, 이 플레이북은 X 전용 포맷(스레드, 훅, 280자 리듬)과 일일 루틴에 특화.

## 에이전트 조합

```
copywriter → reviewer
```

## 입력

```
BRAND: {client}        # 클라이언트명
COUNT: {count}         # 포스트 수 (기본: 3)
THEMES: {themes}       # 오늘의 주제 (선택 — 없으면 아래 로테이션)
SOURCE: {source}       # 소재 파일 (선택 — 블로그, 제품 업데이트 노트 등)
```

## 참조 문서

- `clients/{client}/config.md` — 제품, ICP
- `clients/{client}/brand-guidelines.md` — 톤앤매너 (필수)
- `clients/{client}/copy-patterns.md` — 검증된 카피 패턴
- `knowledge-base/{client}/winning-copy.md` — 반응 좋았던 포스트

## 주제 로테이션 (THEMES 미지정 시)

| 요일 | 주제 |
|------|------|
| 월 | 이번 주 인사이트/배운 점 |
| 화 | 제품 디테일/사용법 |
| 수 | 업계 트렌드 코멘트 |
| 목 | 고객 문제/스토리 |
| 금 | 빌딩 인 퍼블릭 (숫자/진행 상황) |

## 절차

### 1단계: 소재 수집
- SOURCE 파일, 최근 outputs, KB winning-copy에서 오늘의 소재 선정

### 2단계: 포스트 초안 작성
- X 네이티브 규칙:
  1. 첫 줄이 훅 — 스크롤을 멈추는 한 문장 (280자 제한 내)
  2. 단문 리듬, 줄바꿈 적극 활용
  3. 해시태그 0-2개 (남발 금지)
  4. 링크는 댓글로 (본문 링크는 도달 감소) [추정]
  5. 스레드 포맷 1개 포함 옵션 (5-7트윗)
- 포맷 믹스: 단문 포스트 + 스레드 + 질문/폴 유도

### 3단계: 검토
- reviewer 검증:
  - [ ] brand-guidelines 톤 준수
  - [ ] 금지 표현 없음
  - [ ] 각 포스트가 독립적으로 성립 (복붙 변형 아님)

## 출력

`outputs/{client}/content/{YYYYMMDD}_x-twitter-daily.md`

```markdown
# X 일일 초안 — {client} {date}
## 포스트 1 (단문) — 훅 / 본문 / 의도
## 포스트 2 (스레드) — 5-7트윗 전문
## 포스트 3 (참여 유도) — 질문/폴
## 게시 제안 시간대 [추정]
```

## KB 업데이트

- 사용자가 "좋다"고 한 포스트는 `knowledge-base/{client}/winning-copy.md`에 append

## 금지 사항

- 자동 게시 금지 — 초안만 전달, 게시는 클라이언트
- 경쟁사 멘션·논쟁 유발 정치/사회 이슈 금지 (config에 명시된 경우 제외)
