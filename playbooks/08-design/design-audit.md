# 디자인 감사 플레이북

## 목적

기존 랜딩페이지/상세페이지/마케팅 페이지의 디자인 품질을 5개 카테고리(타이포그래피, 컬러, 레이아웃, 인터랙티브, 한국어 품질)로 감사하고, 100점 스코어카드와 우선순위별 개선 로드맵을 생성한다.

## 에이전트 조합

```
designer → reviewer
```

| 순서 | 에이전트 | 역할 | 모델 |
|------|---------|------|------|
| 1 | designer | 5카테고리 디자인 감사 수행 (각 20점, 총 100점) | sonnet |
| 2 | reviewer | 감사 결과 검증 + 개선 우선순위 정합성 확인 | sonnet |

## 입력

| 항목 | 설명 | 필수 여부 |
|------|------|---------|
| `client` | 클라이언트 폴더명 | 필수 |
| `url` | 감사 대상 URL | 필수 |
| `focus` | 중점 영역 (all / typography / color / layout / interactive / korean) | 선택 (기본: all) |

## 참조 문서

- `clients/{client}/brand-guidelines.md` — 브랜드 컬러/톤 기준
- `agents/designer.md` — 디자인 감사 체크리스트 (5카테고리)

## 프레임워크

### 5카테고리 감사 (각 20점, 총 100점)

#### 1. 타이포그래피 감사 (20점)
- 금지 폰트 미사용 (Inter, Noto Sans KR, Roboto, Arial)
- Pretendard 또는 동급 한국어 폰트 사용
- 한국어 텍스트에 break-keep-all 적용
- 헤드라인 크기/무게 충분 (text-4xl+ font-bold)
- 본문 max-width ~65ch 제한

#### 2. 컬러 감사 (20점)
- 1페이지 1액센트 컬러 이하
- 채도 80% 미만
- Purple/Blue AI 그라디언트 미사용
- 순수 #000000 미사용
- 그림자 색조 틴팅

#### 3. 레이아웃 감사 (20점)
- 인접 섹션 다른 레이아웃
- 3등분 카드 열 반복 없음
- 섹션 패딩 py-20+ 확보
- max-width 컨테이너 존재
- min-h-[100dvh] 사용 (h-screen 아님)

#### 4. 인터랙티브 감사 (20점)
- CTA 버튼 hover/active 상태
- CTA 크기 48px+
- 스크롤 애니메이션 존재
- 이징 cubic-bezier 기반

#### 5. 한국어 품질 감사 (20점)
- 자연스러운 한국어 (번역투 아님)
- 존칭 일관성
- AI 클리셰 미사용
- 구체적 숫자 사용
- 이모지 미사용

### 점수 등급
- 90-100: 프리미엄 (Excellent)
- 75-89: 양호 (Good)
- 60-74: 보통 (Fair) — 중요 개선 필요
- 40-59: 미흡 (Poor) — 즉각 개선 필요
- 0-39: 위험 (Critical) — 전면 재설계 권장

## 출력 경로

```
outputs/{client}/design/{YYYYMMDD}_design-audit.md
```
