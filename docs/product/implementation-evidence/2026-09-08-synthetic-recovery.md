# G26 첫 D — 정지 합성 자료 복구 증거 — 2026-09-08

## 한 장 요약

**G26 첫 범위 bounded D PASS.** 개발용 실습 모듈이 직접 만든 완료 실행팩 1건과 queued Job 1건에 한정해, 웹·엔진 DB 두 개와 고정 참조 파일을 새 백업 및 새 복원 사본에서 대조했다. 독립 reviewer가 최종 두 소스·집중 검사·합성 증거·지원 문서를 대조해 PASS로 판정했다. 기존 고객 자료를 입력받는 운영 백업 CLI나 배포 패키지 기능은 아니다. G26 전체·G22-08/09·운영 H·G02·T01–T16·전체 goal은 **OPEN**이다.

## 실행법과 변경 경계

저장소 개발 의존성과 기존 테스트 helper가 있는 checkout에서 실행한다. `NEW_DIRECTORY`는 아직 존재하지 않는 새 출력 경로로 바꾼다.

```text
uv run python -m scripts.rehearse_store_recovery --output NEW_DIRECTORY
```

- 구현은 `scripts/rehearse_store_recovery.py`, 회귀는 `tests/test_store_recovery_rehearsal.py`에 있다. 실제 고객 source 인자는 없으며 기존 DB·고객 root를 검색하거나 가져오지 않는다.
- `source/` 생성 단계에서만 기존 ORM·migration·엔진 작업과 합성 승인/검토 fixture를 사용한다. 완료 팩 1건과 실행 전 queued Job 1건을 준비하고 소유한 연결을 닫는다. 이후 웹·worker·공급자를 시작하거나 복원 상태를 수리하지 않는다.
- 정지한 원본의 DB 두 개는 SQLite backup API로, 고정 참조·산출물·승인 snapshot은 상대 경로·크기·SHA로 새 `backup/`에 복사한다. 원본과 백업 DB의 schema·논리 내용을 대조한 뒤 완성 manifest를 마지막에 기록한다.
- 새 `restored/`는 고정 manifest의 파일을 복사하고 모든 읽기 검증을 통과한 뒤에만 완성 manifest를 기록한다. 기존 목적지·겹치는 root·외부/redirect 경로·파일 변조를 거절하며 실패 디렉터리는 불완전 상태로 남긴다.
- Windows 긴 경로는 논리 경로를 검증한 뒤 기존 `native_io_path`를 파일 I/O·디렉터리 순회와 테스트 사본 읽기/복사에 재사용한다. 공유 제품 소스는 수정하지 않았다.

## 검증하는 것

복원 사본을 `mode=ro`와 기존 읽기 전용 엔진 경로로 열어 integrity/FK·schema·고정 runtime 범위를 확인한다. Job↔run의 client·workflow·입력, 완료/queued 상태와 queued run 미존재, 승인 snapshot의 바이트 및 기존 `verified_pack`의 owner 승인·terminal 검토·정확한 파일 근거를 대조한다.

신뢰한 DB 본체와 별도로 비어 있지 않은 WAL이 백업/복원 집합에 추가되면 읽기 전에 거절한다. 원본 DB 본체·논리 내용·고정 업무 파일 불변과 WAL/SHM·OS lock 보조 파일 관측을 구분한다. `mode=ro`를 모든 보조 파일 바이트 불변이나 잠금에 참여하지 않는 writer 차단의 증명으로 쓰지 않는다.

## 현재 실행 근거

로그는 `artifacts/real-use-review/` 아래에 있다. 문서 작성자는 소스·로그·합성 증거를 읽었으며 별도 CLI나 검사를 실행하지 않았다. 테스트 모듈의 fixture subprocess가 실제 개발용 실습 모듈을 호출한다.

| 관측 | 결과와 범위 |
|---|---|
| 최초 집중 검사 | `g26-first-d-tests-initial.log`: **11 PASS / 29.81초**. |
| 경계 보완 | reviewer가 복원 검증 전 manifest 기록과 비어 있지 않은 WAL 수용을 지적했다. 구현 순서를 보완하고 두 회귀를 추가했다. `g26-first-d-tests-final.log`: **13 PASS / 35.50초**. |
| 정적 검사 | 최초 `g26-type.log`에 기존 private helper 사용 오류 2개. 최종 소스의 `g26-type-native.log`: **0 errors / 0 warnings / 0 notes**, `g26-ruff-native.log`: 대상 Ruff PASS. 실행자 종료 코드 0 전달. |
| 긴 경로 실패 이력 | `g26-first-d-tests-frozen.log`: **5 FAIL + 8 PASS / 21.27초**. 테스트 사본 복사/읽기 4건과 **실제 복원 디렉터리 생성의 WinError 206 1건**이다. 해당 실행의 `g26-proof-e9c421a7` 합성 fixture 성공은 이 모듈 실패를 대체하지 않는다. |
| 최종 집중 재검사 | 긴 경로 처리를 보완한 소스로 기존과 같은 길이의 새 `g26-proof-e9c421a8` 경로에서 실행했다. `g26-first-d-tests-native.log`: **13 PASS / 30.74초**, 실행자 종료 코드 0 전달. |
| 최종 합성 실습 | `g26-proof-e9c421a8/store-recovery0/fixture/evidence.json`: `synthetic-pass`, `stopped-synthetic-only`, 완료 Job 1/queued Job 1/엔진 run 1, **원본의 고정 업무 파일 27개 전후 일치**. |
| 제출 전 검사·검토 | root의 `g26-pre-push-ruff.log`: 저장소 전체 Ruff PASS. `g26-final-source.json`: 현재 두 소스와 합성 증거 SHA, 원본 27개 파일의 실제 바이트 재대조. `g26-final-review.md`: 첫 범위 bounded D 및 지원 문서 PASS. |

최종 fixture ID는 `8f79abce2eef4066a1f076dab0592980`, bundle SHA-256은 `ba9fe85d8fef28c9057145bd40f2fceec1e6f912bc97ed5fe5d9b2230a38dad5`다. 아래 SHA는 문서 작성 시 직접 읽기 대조했다.

| 파일 | SHA-256 |
|---|---|
| 최종 `evidence.json` | `8f356bc21080bc051fad6f9afd75020a7db7d0a371ad55c9b92e9b87b4aaefc3` |
| `scripts/rehearse_store_recovery.py` | `598451baa83a20ef669aed3ffaa06d3e2efe35e9415b16cf21fbf3253837ae6a` |
| `tests/test_store_recovery_rehearsal.py` | `6a86aa3135c043cbc69f9050948ebcf2eda637664dfda21fa5d5d9f687e646c5` |

runtime digest는 core Python·Store model/migration·선택한 테스트 helper·실습 모듈 범위이며 앱 전체 해시가 아니다.

## 남은 범위

이번 변경 후 전체 pytest는 재실행하지 않았다. 기존 제품 코드·공용 DB 경로·웹 route의 새 기능이나 설치 wheel에서의 실행 성공을 주장하지 않는다. 이 사진 없는 합성 팩은 실제 사진·KB·source URL/manifest·다른 workflow·중단 상태 전체를 포함하지 않는다.

실제 서비스 정지와 전역 writer 통제, 부분 복원 재개, 복원 사본의 업무 재개, 최신 권한 철회·세션·삭제 정책 반영, 실제 서버 전환과 운영 복구는 후속 H다. 두 DB의 시점 일치는 직접 만든 정지 fixture가 전제이며 운영 중 원자적 동시 snapshot을 보장하지 않는다.

## 다음 단계

1. 판정된 두 소스와 지원 문서를 Git에 반영하고 실제 원격 SHA를 확인한다. 이전 실패와 현재 증거는 구분해 보존한다.
2. 첫 D의 승인된 범위만 Git 반영하고 G26 나머지·G22-08/09·운영 H·G02·T01–T16·전체 goal은 OPEN으로 유지한다.
