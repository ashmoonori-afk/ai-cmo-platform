# CLAUDE.md — Claude Code 어댑터 (포인터)

> ⚠️ 이 파일은 **포인터**입니다. 플랫폼의 시스템 두뇌는 도구 중립 파일로 이동했습니다.
>
> - **운용 규칙 전문**: [`AGENTS.md`](AGENTS.md) — 클라이언트 로딩, 디스패치, 출력 경로, 검증 게이트, KB, 안전 게이트, Lite 모드
> - **기계 판독 레지스트리**: [`registry/capabilities.yaml`](registry/capabilities.yaml) — 에이전트 13개, 자연어→플레이북 매핑 74개, 모듈/게이트 규칙
>
> Claude Code든 다른 CLI/에이전트든 위 두 파일을 읽고 동일하게 운용하세요. 매핑·규칙을 바꿀 때는 `AGENTS.md`와 `registry/capabilities.yaml`을 함께 수정합니다 (`tests/test_capabilities_registry.py`가 동기화를 강제).

## Claude Code 특화 메모

- 서브에이전트 디스패치는 Agent tool 사용. `+` 조합은 한 메시지에 Agent tool을 여러 개 호출해 병렬 실행
- 에이전트 호출 시 `agents/{name}.md` 전문을 프롬프트에 포함 + 클라이언트 설정 경로 + 출력 경로 전달
- 자연어→워크플로우 매칭은 `registry/capabilities.yaml`의 `mappings[].triggers` 기준 (정확 > 부분 > 복합)
- 검증 게이트·안전 게이트·승인 게이트는 `AGENTS.md` §5-6과 `prompts/shared/gate-check.md`를 그대로 적용
