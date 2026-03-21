# AI CMO Platform — 에이전트 개선 설계서

**작성일**: 2026-03-20
**범위**: 11개 에이전트 심층 개선 (Designer 신규 포함) (연계 강화 + 개별 품질 향상)
**접근 방식**: B (Comprehensive) — 각 에이전트 프롬프트 구조적 재설계

---

## 1. 공통 개선 사항

모든 에이전트에 다음 4개 섹션을 표준화하여 추가한다.

### 1.1 연계 프로토콜 (JSON 핸드오프)

에이전트 간 데이터 전달은 `_handoff/` 폴더의 JSON 파일을 통해 수행한다.

**경로 규칙:**
```
outputs/{client}/_handoff/{YYYYMMDD}_{source_agent}_{task}.json
```

**표준 JSON 구조:**
```json
{
  "meta": {
    "source_agent": "researcher",
    "target_agent": "strategist",
    "client": "flowerplus",
    "created": "2026-03-20",
    "task": "gtm-motion-analysis"
  },
  "summary": "핵심 요약 3줄 이내",
  "key_findings": [],
  "data": {},
  "recommendations": []
}
```

**핸드오프 쌍별 data 필드 정의:**

| 소스 → 타겟 | data 필드 |
|------------|----------|
| researcher → strategist | market_size, growth_rate, channel_benchmarks, sources[] |
| researcher → sales-writer | company_profile, sales_triggers[], contact_profile, icp_score |
| competitor → strategist | competitors[], white_space, threats[] |
| competitor → reviewer | competitor_changes[], threat_level |
| seo-specialist → copywriter | target_keyword, secondary_keywords[], recommended_h2[], search_intent, competitor_avg_length, internal_links[] |
| strategist → copywriter | strategy_summary, key_messages[], target_persona, funnel_stage |
| strategist → sales-writer | positioning_statement, differentiators[], value_props[] |
| copywriter → repurposer | core_messages[3], key_data_points[], quotable_lines[] |
| copywriter → reviewer | content_type, word_count, keywords_used[], sections[] |
| data-analyst → strategist | metrics{}, trends[], anomalies[], action_items[] |
| reporter → (다음 주 reporter) | weekly_summary, completed_actions[], pending_actions[], kb_updates_count |
| reviewer → (FAIL 대상 에이전트) | verdict, failed_items[], fix_instructions[] |

### 1.2 자체 검증 (Self-Check)

모든 에이전트는 산출물 제출 전 자체 검증을 수행한다. 에이전트별 5-7개 체크 항목을 프롬프트에 명시한다.

### 1.3 에러 핸들링 (Fallback)

모든 에이전트에 다음 상황별 대응 규칙을 추가한다:
- 참조 문서 누락 시
- WebSearch 결과 부족 시
- 데이터 부족/품질 저하 시
- 글자 수 초과/미달 시

### 1.4 한국어 특화 규칙

- 문체: brand-guidelines.md 기반 (~입니다/~합니다 vs ~해요/~에요)
- 외래어: 첫 등장 시 "한글(English)" 병기
- 수치: 한국식 (만/억 단위, ₩ 표기)
- 날짜: YYYY년 MM월 DD일 또는 YYYY-MM-DD

---

## 2. 에이전트별 고유 개선

### 2.1 Researcher (리서처)

| 항목 | 현재 | 개선 |
|------|------|------|
| 검색 전략 | "WebSearch로 최신 정보 수집" | 3단계 검색 전략 (브랜드 키워드 → 업종 키워드 → 트렌드 키워드) |
| 소스 평가 | 없음 | 신뢰도 3등급 (high: 공식기관·보고서 / medium: 업계미디어·뉴스 / low: 일반블로그·포럼) |
| 한국어 검색 | 없음 | 한국어 + 영어 병행 검색, 네이버/구글 이중 검색 |
| 핸드오프 | 마크다운 전문 | JSON (summary + key_findings + data + sources) |
| 에러 핸들링 | 없음 | 검색 결과 부족 시 키워드 확장 → 3회 시도 → [데이터 부족] 태그 |
| 자체 검증 | 없음 | 출처 5개+, 6개월 이내 정보 80%+, 추정 태그 확인, 중복 제거 |

### 2.2 Competitor (경쟁사 분석가)

| 항목 | 현재 | 개선 |
|------|------|------|
| 변화 감지 | 없음 | KB 이전 분석과 diff 비교, 변화 강도 태깅 (없음/낮음/중간/높음) |
| 경쟁사 수 | 무제한 | 최대 5개, config.md 우선 + 시장점유율 기준 선택 |
| 가격 비교 | "공개된 것만" | 가격 정규화 (월 기준, ₩, VAT 포함 여부 명시) |
| 핸드오프 | 마크다운 | JSON (competitors[] + white_space + threats[]) |
| WebSearch | 전략 없음 | 경쟁사별 3개 필수 검색 (웹사이트 + 뉴스 + 채용공고) |
| 자체 검증 | 없음 | 경쟁사당 3개+ 출처, 비교 기준 동일성, 가격 단위 통일 |

### 2.3 Strategist (전략가)

| 항목 | 현재 | 개선 |
|------|------|------|
| 입력 수신 | "텍스트 또는 파일 경로" | _handoff/ JSON Read → key_findings와 data 기반 전략 수립 |
| KB 반영 | "반드시 읽기" | insights 최근 3개 인용 의무, lessons-learned 실패 패턴 회피 |
| 프레임워크 선택 | 없음 | 비즈니스 상황 → 적합 프레임워크 매칭 기준표 |
| 실행 가능성 | "바로 실행할 수 있는 전술" | 각 액션에 난이도(상/중/하) + 필요 리소스 + 예상 소요 기간 필수 |
| 핸드오프 | 마크다운 | JSON (strategy_summary + action_items[] + kpis[] + risks[]) |
| 자체 검증 | 없음 | 모든 전략에 근거 데이터 역추적 가능, 로드맵 기한 누락 체크 |

### 2.4 Copywriter (카피라이터)

| 항목 | 현재 | 개선 |
|------|------|------|
| SEO 키워드 | "자연스럽게 녹여넣기" | H1 1회, 첫 100자 1회, H2 2개+, 본문 밀도 1-2% |
| 입력 수신 | brief 텍스트 | seo-specialist JSON → target_keyword, h2 구조, search_intent |
| 한국어 특화 | 없음 | 문장 40자 이내, 문체 통일, 외래어 병기 |
| content_type | blog/social/newsletter만 | case-study(SCSR), lead-magnet(유형별) 출력 형식 추가 |
| CTA | "CTA 포함" | 퍼널 단계별 CTA 매핑 (인지→구독, 고려→데모, 전환→구매) |
| 자체 검증 | 없음 | 글자 수 범위, placeholder 없음, 금지 표현 스캔, 키워드 밀도 |

### 2.5 Repurposer (리퍼포저)

| 항목 | 현재 | 개선 |
|------|------|------|
| 메시지 추출 | "핵심 메시지 3개" | 기준: ①강한 주장 ②수치 근거 ③독자 액션 |
| LinkedIn | 300-500자 | 외부 링크 첫 댓글, 이모지 3개 이하, 줄바꿈 2줄 이내 |
| Twitter/X | 5-7트윗 | 트윗당 독립성, 마지막에만 링크, 인용 트윗용 단독 버전 추가 |
| 카드뉴스 | 고정 5장 | 5-8장 유동적, 비주얼 방향 구체화 |
| 입력 수신 | 텍스트/경로 | copywriter JSON에서 core_messages 직접 수신 |
| 자체 검증 | 없음 | 글자 수 제한 준수, 원본 외 정보 추가 여부 확인 |

### 2.6 SEO Specialist (SEO 전문가)

| 항목 | 현재 | 개선 |
|------|------|------|
| GEO | 에이전트에 없음 | AI 검색 최적화: 정의형 문장, Q&A 구조, Schema.org, E-E-A-T |
| 네이버 SEO | 없음 | 스마트블록 대응, 네이버 블로그 최적화, 키워드 광고 연계 |
| 검색량 추정 | "추정" | SERP 기반 방법론: 상위 결과 수, 광고 유무, 자동완성 후보로 상대 추정 |
| 경쟁 분석 | "경쟁 콘텐츠 조사" | 상위 5개 H구조, 글자수, 멀티미디어, FAQ 유무 분석 의무 |
| 핸드오프 | 마크다운 | JSON (keyword + h2 + intent + competitor_avg_length) |
| 자체 검증 | 없음 | 클러스터 3개+, pillar+supporting 존재, 검색의도 분류 완료 |

### 2.7 Data Analyst (데이터 분석가)

| 항목 | 현재 | 개선 |
|------|------|------|
| Python | "필요 시 실행" | 행 100+ 또는 피벗/그룹화 시 pandas, 코드→마크다운 표 변환 |
| 시각화 | 없음 | 텍스트 시각화: 트렌드→ASCII 막대, 비교→표, 분포→백분율 바 |
| 이상치 | 없음 | 평균 ± 2σ 또는 전월 ±30% → 원인 분석 필수 플래그 |
| 데이터 부족 | "추측 금지" | ①부분 분석 ②부족 항목 명시 ③추가 데이터 요청 목록 |
| 핸드오프 | 마크다운 | JSON (metrics + trends + anomalies + action_items) |
| 자체 검증 | 없음 | 출처 파일/행 명시, 합계 교차 검증, 비율 합산 100% |

### 2.8 Sales Writer (세일즈 라이터)

| 항목 | 현재 | 개선 |
|------|------|------|
| 한국식 예절 | 없음 | ~님 호칭, 격식체, 첫 이메일 자기소개, CC 문화 반영 |
| 개인화 등급 | "최소 1개" | L1(회사명/업종), L2(최근 뉴스/채용), L3(LinkedIn 활동). 콜드메일 L2+, 제안서 L3 |
| 가격 화법 | "pricing-rules.md 준수" | ROI 역산 → 효과 → 가격, "비용"이 아닌 "투자" 용어 |
| 이메일 길이 | "300자 이내" | 콜드메일 200자, 팔로업 150자, 제안서 300자, 감사 200자 |
| 입력 수신 | "researcher 결과물" | JSON (sales_triggers + contact_profile + icp_score) |
| 자체 검증 | 없음 | 개인화 등급, 가격 범위, 경쟁사 비하 없음, CTA 명확성 |

### 2.9 Reporter (리포터)

| 항목 | 현재 | 개선 |
|------|------|------|
| 파일 스캔 | "최근 7일" | Glob 패턴: `outputs/{client}/**/*{YYYYMMDD}*`, 날짜 필터링 |
| KB 중복 방지 | 없음 | 유사 인사이트 검색, 70%+ 중복 시 스킵 + 날짜 갱신 |
| 분기별 정리 | "구조 변경 허용" | ①6개월+ 아카이브 ②중복 병합 ③카테고리 재분류 |
| 인사이트 추출 | "핵심 내용 추출" | "## 핵심 발견" / "## 추천" 섹션 우선 스캔, 없으면 첫 3문단 |
| 핸드오프 | 해당 없음 | 주간 리포트 JSON을 _handoff/에 저장 → 다음 주 전주 대비 비교 |
| 자체 검증 | 없음 | 스캔 vs 언급 파일 수 일치, 모든 모듈 커버, KB 500자 이내 |

### 2.10 Reviewer (검증자)

| 항목 | 현재 | 개선 |
|------|------|------|
| 유형별 검증 | 단일 체크리스트 | 6개 유형별 가중치 매트릭스 |
| 수정 지시 | "구체적 수정" | 템플릿: [위치] + [문제] + [수정 방향] + [예시] |
| 브랜드 범위 | content/sales만 | strategy/seo도 용어 일관성, 클라이언트명 표기 검증 |
| 판정 기준 | PASS/WARN/FAIL | 점수 기반: 90%+ PASS, 70-89% WARN, 70% 미만 FAIL |
| 핸드오프 | 없음 | FAIL 시 수정 지시 JSON → 대상 에이전트가 구조화된 수정 |
| 자체 검증 | 없음 | 모든 항목에 판정 근거 존재, 빈 판정 없음 |

**유형별 검증 가중치:**

| 검증 항목 | strategy | research | content | sales | seo | report |
|---------|----------|----------|---------|-------|-----|--------|
| 구조 완결성 | 30% | 20% | 25% | 25% | 20% | 30% |
| 데이터 정확성 | 30% | 40% | 15% | 20% | 35% | 35% |
| 브랜드 일관성 | 10% | 5% | 35% | 30% | 10% | 5% |
| 실행 가능성 | 30% | 15% | 10% | 25% | 25% | 15% |
| 출처 명시 | 0% | 20% | 15% | 0% | 10% | 15% |

---

## 3. _handoff/ 폴더 규칙

- 경로: `outputs/{client}/_handoff/`
- 파일명: `{YYYYMMDD}_{source_agent}_{task}.json`
- 보존 기간: 30일 (이후 자동 정리 대상)
- 최종 산출물은 기존대로 마크다운(.md)으로 저장
- JSON은 중간 전달 전용, 사용자에게는 마크다운 산출물만 안내
