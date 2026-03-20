# 영업 준비 번들 체인

## 목적
타겟 기업 리서치 → 미팅 브리프 → 콜드 아웃바운드 시퀀스를 한 번에 실행한다.

## 실행 순서

### Phase 1: 기업 리서치 (병렬)
- researcher 에이전트: 타겟 기업 심층 리서치
- competitor 에이전트: 타겟 기업이 사용 중인 경쟁 솔루션 파악
→ 두 결과 합쳐서 Phase 2-3에 전달

### Phase 2-3: 미팅 브리프 + 아웃바운드 (병렬)
- playbook: `04-sales/call-prep.md` → sales-writer (미팅 브리프)
- playbook: `04-sales/outbound-sequence.md` → sales-writer (3통 이메일 병렬)
→ 두 작업은 독립적이므로 동시 실행 가능

### Phase 4: 검증
- reviewer 에이전트: 이메일 시퀀스 검증 (개인화, 톤앤매너)

## 입력
- `client`: 클라이언트명
- `target_company`: 타겟 기업명 (필수)
- `target_contact`: 타겟 담당자 (선택)
- `context`: 영업 맥락 (예: "콜드 아웃바운드", "인바운드 리드", "미팅 전 준비")

## 출력
```
outputs/{client}/intelligence/{YYYYMMDD}_account-research-{target}.md
outputs/{client}/sales/{YYYYMMDD}_call-prep-{target}.md
outputs/{client}/sales/{YYYYMMDD}_outbound-sequence-{target}.md
```

## 예상 소요 시간
- Phase 1 (병렬): ~3분
- Phase 2-3 (병렬): ~3분
- Phase 4 (검증): ~1분
- **총 ~7분**

## 명령어 패턴
"영업 준비 풀세트", "영업 자료 다 만들어줘", "{회사명} 영업 준비", "세일즈 번들"
