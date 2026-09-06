# 한 장 요약

피드백과 Reporter가 기존 기록을 덮어쓰거나 동시에 추가한 내용을 잃는 문제를 공통 저장 함수에서 수정했다. 저장 전 지원 개인정보·시크릿 최소화, 같은 피드백 재전달의 중복 방지, 기존 바이트 보존을 검증한다. 운영자는 개인정보 없는 짧은 요약을 입력하고 저장 실패 시 원인을 해소한 뒤 재시도한다.

## 문제와 수정

| 문제 | 구현과 검증 위치 |
|---|---|
| feedback의 잠금 없는 read/write와 Reporter의 텍스트 재인코딩 | `reporter.append_record`로 통합. 파일별 잠금 안에서 기존 바이트 읽기, 고유 임시 파일 작성, 성공 시 교체. BOM·CRLF·마지막 줄 보존 |
| Windows의 비어 있지 않은 lock 파일에서 잠금/해제 위치 불일치 | 잠금과 해제 모두 `seek(0)`. 실제 Windows byte-range locking 검사 |
| 재전달 또는 append 후 consume 전 중단으로 중복 기록 | 최소화된 피드백 본문의 SHA 기반 marker, Reporter의 run/step/path 기반 marker 및 과거 marker 호환 |
| 새 피드백과 KB 큐에 지원 PII/시크릿 원문 저장 | `safe_kb_text`를 SQLite 삽입 전과 파일 저장 전에 적용. 500자 상한·빈 표시·제어 문자 거부. feedback은 실행 전 사전 검사 |
| 입력으로 marker를 위조해 후속 기록 억제 | 새 내용은 들여쓴 리터럴 블록으로 저장, marker는 독립된 줄로만 인식 |
| 실패 시 기존 파일 손상 또는 큐 소진 | UTF-8 오류/교체 실패 시 원본 보존, 임시 파일 정리, 성공·재실행 확인 후에만 consume |
| 500자 제한과 기존 최대 128자 식별자 계약 충돌 | 큐 본문의 중복 run/step 식별자를 제거하고 SQLite/Reporter 제목에 유지. 최대 길이 client/run/step으로 실제 workflow·flush 회귀 검사 |
| Windows 동시 생성/교체 중 같은 경로를 외부로 오판 | 실제 resolve 결과의 드라이브/UNC extended namespace 표기 차이를 공통 `paths.py`에서 정규화한 뒤 containment 검사. 부모 검사 후 고정 파일명을 결합하고 파일 symlink는 잠금 내부에서 거부 |

## 검사 증거

실행 가능한 회귀 검사는 `tests/test_feedback_storage.py`, 기존 Reporter 검사는 `tests/test_reliability.py` 및 `tests/test_concurrency_kb_idempotency.py`에 있다. 합성 입력을 사용하며 실제 고객 데이터는 사용하지 않았다. 별도 Python 프로세스 3개의 중복/다른 피드백 기록, 실제 Windows 잠금, 잘못된 인코딩, 교체 실패, 새/과거 marker 재실행, SQLite 저장 전 최소화를 검사한다.

독립 리뷰가 발견한 최대 길이 식별자와 Windows 경로 표기 경쟁 문제를 수정했다. 최종 전체 483개 통과·1개 건너뜀(181.98초), 표적 41개 통과·1개 건너뜀(20.30초), 동시 기록 12회 연속 통과, Ruff PASS, basedpyright 0 errors·0 warnings를 확인했다. 독립 최종 판정은 저장 기반 범위 PASS이며, 별도 전체 483개 통과·1개 건너뜀(174.27초), 새 저장소에서 실제 3프로세스 동시 기록 50회 연속 PASS를 확인했다. 건너뛴 검사는 아래 명시한 Windows 파일 symlink 생성 권한 제한이다.

## 근거와 적용 한계

이미 기록된 과거 marker를 확인한 재실행에서는 원문을 다시 쓰지 않고 큐를 소진한다. 아직 기록되지 않은 과거 큐도 현재 저장 검사를 통과해야 한다.

독립 동시 반복 검사에서 발견한 경로 실패는 candidate에만 `\\?\`가 붙어 root와 다른 경로로 비교된 것이었다. 단순 부모 검사만으로 해결되지 않아 공통 resolve 결과의 표기 정규화까지 수정했다. 실제 파일 symlink 생성 검사는 이 Windows 호스트의 권한 오류 1314로 건너뛴다. 드라이브/UNC 표기와 실제 외부 경로 거부는 재현 입력으로 검사한다.

Python 공식 문서에 따르면 Windows 잠금은 현재 파일 위치에서 시작하며 실패하면 제한된 재시도 후 오류가 발생한다. 따라서 같은 바이트를 잠그고 해제하도록 수정했다. [Python msvcrt 문서, 2026 확인](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking). 기존 파일의 교체에는 표준 라이브러리의 [Path.replace](https://docs.python.org/3/library/pathlib.html#pathlib.Path.replace)를 사용한다.

기존 저장 데이터는 소급 정리하지 않는다. 500자에는 피드백 메타데이터도 포함된다. 지원 패턴의 최소화는 모든 자유 서술 개인정보의 인식 또는 법적 익명화를 의미하지 않는다. 과거 marker 없는 피드백에는 소급 중복 제거를 적용하지 않는다. 전체 파일을 다시 쓰는 방식은 큰 KB에서 비용이 증가하며, 비협조적 외부 쓰기·정전·다중 가게 권한 격리는 이 검증 범위 밖이다.

G12 전체는 미완료다. 기존 `kb.update`의 운영 상태 큐를 저장하는 동작은 채택·수정 이유·관측 성과로부터 검토된 인사이트를 만드는 기능이 아니다. 승인된 사실의 KB 반영과 다음 생성 연결은 별도 구현·검증이 필요하다. G02는 OPEN이다.

## 다음 단계

1. 운영자는 피드백 저장 오류가 발생하면 사용 문서의 인코딩·권한 복구 절차를 적용하고 기존 파일을 보존한다.
2. 개발자와 reviewer는 G12에서 실제 채택/수정 이유/관측 성과의 증거와 승인된 인사이트만 연결하고 다음 생성의 변화를 합성 사례로 검사한다.
