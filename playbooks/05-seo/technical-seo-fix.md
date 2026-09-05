# technical-seo-fix

## 목적

SEO 감사에서 식별된 기술적 문제를 실제 코드 수정으로 완결한다. "진단 → 수정안 → 패치/PR → 검증" 루프를 닫는다. Okara Coding Agent에 해당하는 기능.

## 에이전트 조합

```
growth-engineer → reviewer
```

- growth-engineer: 감사 결과를 코드 변경으로 변환
- reviewer: 수정의 정확성·최소성·검증 로그 확인

## 입력

```
BRAND: {client}        # 클라이언트명
AUDIT_PATH: {path}     # SEO 감사 결과 파일 (outputs/{client}/seo/...)
REPO_PATH: {path}      # 클라이언트 코드베이스 경로 (선택 — 없으면 스니펫/지시서 형태)
SITE_URL: {url}        # 라이브 사이트 (현재 상태 확인용)
SCOPE: {scope}         # 수정 범위 (meta/schema/sitemap/links/performance/all, 기본: all)
```

## 참조 문서

- `outputs/{client}/seo/` — 감사 결과 (수정 대상의 유일한 출처 — 감사에 없는 임의 수정 금지)
- `prompts/shared/geo-checklist.md` — AI 크롤러 robots.txt 기준
- `clients/{client}/config.md` — 기술 스택 [미확인 시 표기]

## 절차

### 1단계: 수정 백로그 확정
- 감사 결과에서 기술적 SEO 미통과 항목만 추출
- 우선순위: 크롤링/인덱싱 차단 > 구조화 데이터 부재 > 메타 누락 > 성능
- 각 항목에 수정 난�도(상/중/하)와 기대 효과 표기

### 2단계: 코드 수정 (REPO_PATH 있는 경우)
- 카테고리별 수정:
  | 카테고리 | 수정 내용 |
  |---------|----------|
  | meta | title/description/OG/Twitter Card 누락·중복·길이 수정 |
  | schema | Organization/Product/FAQ/Article JSON-LD 삽입 |
  | sitemap | sitemap.xml 생성/갱신, robots.txt 정리 (AI 크롤러 허용 기본값) |
  | links | 깨진 내부 링크, canonical, 리다이렉트 체인 정리 |
  | performance | 이미지 lazy-load, render-blocking 리소스 제안 |
- 최소 변경 원칙: 감사 항목 외 리팩터링 금지

### 3단계: 검증
- 각 수정에 검증 명령 실행 + 결과 캡처:
  - 빌드/린트 통과 (코드베이스의 기존 명령 사용)
  - 구조화 데이터: JSON-LD 문법 검증
  - sitemap/robots: 파일 존재 + 문법 확인
- 검증 불가 항목은 "수동 검증 지시서"로 전환

### 4단계: 전달 형태 결정
- REPO_PATH 있음: PR 설명서 + diff (직접 push/배포 금지 — 승인 게이트)
- REPO_PATH 없음: 파일별 적용 스니펫 + 개발자 전달용 지시서

## 출력

`outputs/{client}/seo/{YYYYMMDD}_technical-seo-fix.md`

```markdown
# 기술 SEO 수정 — {client} {date}
## 수정 요약표 (항목/파일/변경/기대효과/검증결과)
## 패치/스니펫
## 미적용 항목 + 수동 지시서
## 검증 로그
```

## 금지 사항

- 승인 없는 배포·push 금지
- 감사 결과에 없는 임의 수정 금지
- 검증 없는 완료 보고 금지
- 콘텐츠 의미 변경 금지 (카피는 copywriter 영역)
