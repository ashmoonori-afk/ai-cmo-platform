# 콘텐츠 풀 사이클 체인

## 목적
키워드 리서치 → 콘텐츠 브리프 → 블로그 작성 → 멀티채널 리퍼포징을 한 번에 실행한다.

## 실행 순서

### Phase 1: 키워드 리서치
- playbook: `05-seo/keyword-research.md`
- seo-specialist 에이전트
- 출력: 키워드 클러스터 + 우선순위 1번 키워드 선정

### Phase 2: 콘텐츠 브리프
- playbook: `05-seo/content-brief.md`
- seo-specialist 에이전트
- 입력: Phase 1 우선순위 키워드
- 출력: SEO 브리프 (H2 구조, 참조 URL)

### Phase 3: 블로그 작성
- playbook: `03-content/blog-article.md`
- copywriter 에이전트
- 입력: Phase 2 브리프
- 출력: SEO 최적화 블로그 (1500-3000자)

### Phase 4: 리퍼포징 (4개 병렬)
- playbook: `03-content/repurpose.md`
- repurposer 에이전트 (4개 병렬)
- 입력: Phase 3 블로그
- 출력: LinkedIn + Twitter + 뉴스레터 + 카드뉴스

### Phase 4.5: 비주얼 에셋 (선택)
- route: `codex-image-gen`
- 입력: Phase 3 블로그 + Phase 4 카드뉴스/소셜 방향
- 출력: 아래 3개 상태 중 정확히 하나
  - `visual_asset_status=generated` + 실제 `png_path`
  - `visual_asset_status=unavailable` + `unavailable_reason`
  - `visual_asset_status=needs_approval` + `approval_owner`
- 주의: 이미지가 생성되지 않았으면 생성된 것처럼 보고하지 않는다

### Phase 5: 검증
- reviewer 에이전트: 블로그 + 4개 변환물 검증

## 입력
- `client`: 클라이언트명
- `topic`: 콘텐츠 주제 (선택 — 없으면 키워드 리서치에서 자동 선정)
- `seed_keyword`: 시드 키워드 (선택)

## 출력
```
outputs/{client}/seo/{YYYYMMDD}_keyword-research.md
outputs/{client}/seo/{YYYYMMDD}_content-brief.md
outputs/{client}/content/{YYYYMMDD}_blog-{topic}.md
outputs/{client}/content/{YYYYMMDD}_repurpose-{topic}.md
```

## 예상 소요 시간
- Phase 1-3 (순차): ~6분
- Phase 4 (병렬): ~2분
- Phase 5 (검증): ~2분
- **총 ~10분**

## 명령어 패턴
"블로그 쓰고 SNS도", "콘텐츠 풀세트", "글 쓰고 퍼뜨려줘", "콘텐츠 풀사이클"
