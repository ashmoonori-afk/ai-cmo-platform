# 소셜 포스트 플레이북

## 목적

LinkedIn, Instagram, Twitter(X) 각 플랫폼의 특성과 알고리즘에 맞는 소셜 미디어 포스트를 작성하여 브랜드 인지도를 높이고, 팔로워 인게이지먼트를 확보하며, 트래픽 및 리드를 생성한다.

---

## 에이전트 조합

```
copywriter → reviewer
```

| 순서 | 에이전트 | 역할 | 모델 |
|------|---------|------|------|
| 1 | copywriter | 3개 플랫폼별 포스트 초안 작성 | sonnet |
| 2 | reviewer | 플랫폼 규격·브랜드 준수 여부 검증 | sonnet |

---

## 입력

| 항목 | 설명 | 필수 여부 |
|------|------|---------|
| `topic` | 포스트 주제 또는 핵심 메시지 | 필수 |
| `client` | 클라이언트 폴더명 | 필수 |
| `platform` | 타겟 플랫폼 (all / linkedin / instagram / twitter) | 선택 (기본: all) |
| `purpose` | 포스트 목적 (인지 / 관심 / 전환 / 커뮤니티) | 선택 |
| `cta_url` | CTA 링크 (있는 경우) | 선택 |
| `visual_concept` | 함께 사용할 이미지·영상 컨셉 설명 | 선택 |
| `image_required` | 실제 이미지 생성 필요 여부 (yes / no) | 선택 |

---

## 참조 문서

| 문서 | 경로 | 목적 |
|------|------|------|
| 클라이언트 설정 | `clients/{client}/config.md` | 회사·ICP·업종 파악 |
| 브랜드 가이드라인 | `clients/{client}/brand-guidelines.md` | 톤앤매너, 이모지 사용 여부 |
| 카피 패턴 | `clients/{client}/copy-patterns.md` | 검증된 훅·CTA 패턴 참조 |
| 우수 카피 KB | `knowledge-base/{client}/winning-copy.md` | 성과 좋은 소셜 카피 재활용 |

---

## 프레임워크

### 플랫폼별 규격

#### LinkedIn (300–500자)
```
구조: Hook → Body → CTA
- Hook (1–2줄): 스크롤을 멈추게 하는 첫 문장. 질문·통계·반직관적 주장
- Body (3–6줄): 핵심 메시지. 줄바꿈 적극 활용. 리스트 또는 번호 목록 허용
- CTA (1줄): 링크 클릭 / 댓글 유도 / 공유 요청

알고리즘 팁:
- 외부 링크는 첫 댓글에 달거나 "링크는 댓글에" 방식 사용
- 이모지는 절제하여 사용 (최대 3–5개)
- 해시태그 3–5개, 포스트 하단
```

#### Instagram (150자 + 해시태그)
```
구조: Hook (캡션 첫 줄) → 본문 → 해시태그 블록
- Hook (1줄, 125자 이내): "더 보기" 버튼 클릭을 유도하는 강렬한 첫 줄
- 본문 (100–300자): 이미지·영상을 보완하는 스토리 또는 정보
- 해시태그: 10개 (니치 5개 + 중간 규모 3개 + 대형 2개)
- 줄바꿈: 가독성을 위해 빈 줄 삽입

비주얼 방향:
- 이미지/영상 컨셉 1줄 설명 포함
- 캐러셀 사용 시 슬라이드별 카피 제안
```

#### Twitter / X (280자 단일 또는 스레드)
```
단일 트윗 (280자):
- 핵심 메시지 하나에 집중
- 숫자·리스트·반전 포인트 활용
- 해시태그 1–2개만

스레드 (5–7트윗):
- 트윗 1: Hook — 가장 강한 주장 또는 결론 먼저
- 트윗 2–5: 근거·단계·사례 (각 250자 이내)
- 트윗 6: 요약 또는 실행 팁
- 트윗 7: CTA + 링크
- 각 트윗 번호 표기 (예: 1/ 2/ ...)
```

---

## 출력 템플릿

```markdown
## LinkedIn

**Hook:**
{첫 1–2줄 — 스크롤 멈추게 하는 문장}

**본문:**
{3–6줄 핵심 내용, 줄바꿈 활용}

**CTA:**
{행동 유도 1줄}

**해시태그:** #{태그1} #{태그2} #{태그3}

---

## Instagram

**캡션 첫 줄 (Hook):**
{125자 이내}

**본문:**
{스토리 또는 정보, 100–300자}

**해시태그:**
#{태그1} #{태그2} #{태그3} #{태그4} #{태그5}
#{태그6} #{태그7} #{태그8} #{태그9} #{태그10}

**비주얼 컨셉:**
{이미지 또는 영상 방향 1줄}

**codex-image-gen prompt brief (image_required=yes인 경우):**
- visual_goal:
- target_channel:
- audience:
- brand_constraints:
- must_include:
- must_avoid:
- prompt:
- visual_asset_status: generated | unavailable | needs_approval
- png_path: required when generated
- unavailable_reason: required when unavailable
- approval_owner: required when needs_approval
- reviewer_notes:

Reviewer must FAIL the visual route if `image_required=yes` and the artifact has
only a prompt brief without one of these statuses.

---

## Twitter / X

### 단일 트윗 버전
{280자 이내 단일 메시지}

### 스레드 버전
**1/** {Hook — 가장 강한 주장}

**2/** {근거 또는 단계 1}

**3/** {근거 또는 단계 2}

**4/** {근거 또는 단계 3}

**5/** {사례 또는 데이터}

**6/** {요약 또는 실행 팁}

**7/** {CTA + 링크}
```

---

## 출력 경로

```
outputs/{client}/content/{YYYYMMDD}_social-post-{topic-slug}.md
```

예시:
```
outputs/flowerplus/content/20260318_social-post-spring-campaign.md
```

**Knowledge Base handoff:**
- 인게이지먼트 높은 포스트 → reporter에게 `winning-copy.md` 반영 후보로 전달
