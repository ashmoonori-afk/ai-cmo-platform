# 전체 마케팅 전략 체인

## 목적
GTM 전략 → 포지셔닝 → 채널 전략 → 퍼널 설계를 한 번에 순차 실행하여 종합 마케팅 전략을 수립한다.

## 실행 순서

### Phase 1: 리서치 (병렬)
- researcher 에이전트: 시장/업종 리서치
- competitor 에이전트: 경쟁사 분석
→ 두 결과를 합쳐서 Phase 2로 전달

### Phase 2: GTM 모션 분석
- playbook: `01-strategy/gtm-motion-analysis.md`
- 입력: Phase 1 리서치 결과
- 출력: GTM 스코어카드 + 상위 3개 모션
→ 출력을 Phase 3 입력으로 전달

### Phase 3: 포지셔닝 맵
- playbook: `01-strategy/positioning-map.md`
- 입력: Phase 1 경쟁사 분석 + Phase 2 GTM 결과
- 출력: 포지셔닝 스테이트먼트 + 메시지 프레임워크
→ 출력을 Phase 4 입력으로 전달

### Phase 4: 채널 전략
- playbook: `01-strategy/channel-strategy.md`
- 입력: Phase 2 GTM 상위 모션 + Phase 3 메시지 프레임워크
- 출력: 채널 매트릭스 + 채널별 전술
→ 출력을 Phase 5 입력으로 전달

### Phase 5: 퍼널 설계
- playbook: `01-strategy/funnel-design.md`
- 입력: Phase 3 포지셔닝 + Phase 4 채널 전략
- 출력: 6단계 퍼널 + 콘텐츠 매핑

### Phase 6: 검증 + 종합
- reviewer 에이전트: 전체 산출물 검증
- 최종 산출물: 종합 전략 보고서 (Phase 2-5 결과 통합)

## 입력
- `client`: 클라이언트명 (필수)
- 추가 입력 없음 — config.md에서 모든 정보 로드

## 출력
```
outputs/{client}/strategy/{YYYYMMDD}_full-strategy-report.md
```
개별 Phase 산출물도 각각 저장:
```
outputs/{client}/intelligence/{YYYYMMDD}_market-research.md
outputs/{client}/intelligence/{YYYYMMDD}_competitor-analysis.md
outputs/{client}/strategy/{YYYYMMDD}_gtm-motion-analysis.md
outputs/{client}/strategy/{YYYYMMDD}_positioning-map.md
outputs/{client}/strategy/{YYYYMMDD}_channel-strategy.md
outputs/{client}/strategy/{YYYYMMDD}_funnel-design.md
```

## 예상 소요 시간
- Phase 1 (병렬): ~3분
- Phase 2-5 (순차): 각 ~2분 = ~8분
- Phase 6 (검증): ~2분
- **총 ~13분**

## 명령어 패턴
"전체 마케팅 전략", "마케팅 플랜 세워줘", "종합 전략", "풀 전략"
