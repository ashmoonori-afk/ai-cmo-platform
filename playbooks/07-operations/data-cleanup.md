# data-cleanup

## 목적

입력 데이터를 분석하여 정규화 규칙을 정의하고 변환을 실행한 뒤, 결과를 검증하여 정리된 데이터 파일과 변환 로그를 생성한다.

## 에이전트 조합

```
data-analyst
```

단일 에이전트. 파일 읽기/쓰기 및 데이터 변환 처리.

## 입력

```
BRAND: {brand}              # 브랜드명
INPUT_FILE: {filepath}      # 정리할 입력 파일 경로 (CSV/JSON/TSV/Excel)
OUTPUT_FILE: {filepath}     # 정리된 파일 출력 경로
DATA_TYPE: {type}           # 데이터 유형 (contacts/transactions/keywords/content/analytics/custom)
RULES: {rules}              # 특별 정규화 규칙 (선택, 없으면 자동 감지)
ENCODING: {encoding}        # 파일 인코딩 (기본: UTF-8)
```

### 민감정보 입력 Gate

- 입력 파일은 원본이 아니라 redacted working copy를 사용한다.
- 고객명, 전화번호, 이메일, 주민/사업자번호, 계정 ID, 쿠키, 토큰, API 키, 인증 헤더가 있으면 `SENSITIVE_COLUMNS`로 지정하고 마스킹/삭제 규칙을 먼저 적용한다.
- 변환 로그와 미리보기에는 원본 민감값을 남기지 않고 마스킹된 값 또는 컬럼명만 남긴다.
- 민감정보가 제거되지 않은 입력이면 중단하고 redacted working copy를 요청한다.

## 참조 문서

- `clients/{brand}/config.md` — 브랜드별 데이터 기준 (날짜 포맷, 통화, 지역)

## 프레임워크

### Phase 1: 입력 데이터 분석 (Profiling)

```
구조 분석:
- 파일 형식 (CSV/JSON/TSV/Excel)
- 컬럼 수, 행 수
- 헤더 존재 여부
- 인코딩 (UTF-8/EUC-KR 등)

컬럼별 분석:
- 데이터 타입 (문자열/숫자/날짜/불리언)
- 고유값 수 (카디널리티)
- 누락값 (null/빈칸/N/A) 비율
- 이상값 (outlier) 존재 여부
- 중복 행 수

데이터 품질 점수 (0-100):
- 완전성 (누락값 없음): 30점
- 일관성 (포맷 통일): 30점
- 정확성 (이상값 없음): 20점
- 중복 없음: 20점
```

### Phase 2: 정규화 규칙 정의

```
기본 정규화 규칙 (자동 적용):

텍스트 필드:
  - 앞뒤 공백 제거 (strip)
  - 연속 공백 단일화
  - 인코딩 통일 (UTF-8)
  - 특수문자 처리 (유지/제거/대체 중 선택)

날짜 필드:
  - 목표 포맷: YYYY-MM-DD
  - 입력 포맷 자동 감지: YYYYMMDD / DD/MM/YYYY / MM-DD-YYYY 등

숫자 필드:
  - 통화 기호 제거 (₩, $, ,)
  - 퍼센트 → 소수 변환 (50% → 0.50, 선택)
  - 결측값 → 0 또는 NULL (비즈니스 로직에 따라)

카테고리 필드:
  - 대소문자 통일 (소문자 권장)
  - 동의어 통합 (예: "서울" / "seoul" / "Seoul" → "서울")
  - 허용값 목록(whitelist) 외 값 → "기타" 처리

사용자 정의 규칙:
  - RULES 입력값으로 추가 정의
```

### Phase 3: 변환 실행

```
변환 순서:
1. redacted working copy 확인 (원본 파일 복사/백업 금지)
2. 헤더 정규화
3. 행별 변환 적용
4. 중복 행 제거 (중복 기준 컬럼 지정)
5. 정렬 (지정된 컬럼 기준)
6. 출력 파일 저장

변환 로그 기록 (행별):
- 변환된 행 ID
- 변환 유형 (strip/format/dedup/replace/null_fill)
- 마스킹된 원본값 → 변환값
```

### Phase 4: 결과 검증

```
검증 항목:
- 행 수 변화 (원본 vs 정리 후)
- 컬럼 수 일치 여부
- 누락값 비율 (변환 전후 비교)
- 중복 제거 확인
- 민감정보 제거 후 샘플 10행 미리보기

검증 통과 기준:
- 데이터 손실 0% (의도치 않은 행 삭제 없음)
- 누락값 비율 감소 또는 동일
- 포맷 일관성 100%
```

## 출력 템플릿

```markdown
# 데이터 정리 리포트 — {brand}
**처리일**: {date}
**입력 파일**: {input_file}
**출력 파일**: {output_file}
**담당**: data-analyst

---

## 1. 입력 데이터 프로파일링

| 항목 | 값 |
|-----|---|
| 파일 형식 | {format} |
| 총 행 수 | {rows} |
| 총 컬럼 수 | {cols} |
| 인코딩 | {encoding} |
| 파일 크기 | {size} |

### 컬럼별 분석

| 컬럼명 | 타입 | 고유값 수 | 누락값 (%) | 이상값 | 품질 점수 |
|-------|-----|---------|---------|------|---------|
| {col_1} | {type} | {n} | {pct}% | {n} | {score} |
| {col_2} | {type} | {n} | {pct}% | {n} | {score} |

**데이터 품질 점수 (변환 전)**: {score}/100

---

## 2. 적용된 정규화 규칙

| 컬럼 | 규칙 | 적용 사례 |
|-----|-----|---------|
| {col} | 날짜 포맷 통일 (→ YYYY-MM-DD) | "20260318" → "2026-03-18" |
| {col} | 앞뒤 공백 제거 | " 서울 " → "서울" |
| {col} | 동의어 통합 | "seoul" → "서울" |
| {col} | 결측값 처리 | NULL → 0 |

---

## 3. 변환 결과 요약

| 항목 | 변환 전 | 변환 후 |
|-----|-------|-------|
| 총 행 수 | {before} | {after} |
| 중복 제거 | - | {removed}행 제거 |
| 누락값 비율 | {before}% | {after}% |
| 데이터 품질 점수 | {before}/100 | {after}/100 |

---

## 4. 변환 로그 (상위 20건)

| 행 번호 | 컬럼 | 변환 유형 | 마스킹된 원본값 | 변환값 |
|--------|-----|---------|------|------|
| {row} | {col} | {type} | {before} | {after} |

> 전체 변환 로그: `outputs/{brand}/operations/data-cleanup-log-{YYYYMMDD}.csv`

---

## 5. 샘플 미리보기 (변환 후 10행)

```csv
{header_row}
{sample_row_1}
{sample_row_2}
...
```

---

## 6. 검증 결과

| 검증 항목 | 결과 | 상태 |
|---------|-----|-----|
| 데이터 손실 없음 | {result} | Pass/Fail |
| 포맷 일관성 | {result} | Pass/Fail |
| 중복 제거 확인 | {result} | Pass/Fail |

> **최종 상태**: {Pass/Fail} — {comment}
```

## 출력 경로

```
outputs/{brand}/operations/data-cleanup-{YYYYMMDD}.md      (리포트)
outputs/{brand}/operations/data-cleanup-log-{YYYYMMDD}.csv (변환 로그)
{OUTPUT_FILE}                                               (정리된 데이터)
```
