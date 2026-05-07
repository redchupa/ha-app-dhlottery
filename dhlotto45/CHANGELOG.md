# Changelog

## 2.0.7 - 2026-05-07

### Fixed
- **30초 무응답 hang 해결**: `_async_ensure_main_mode_normal()` 에서 aiohttp 응답 body 를 `async with` 로 끝까지 소비해 keep-alive 커넥션이 풀에 정상 반환되도록 수정. body 미소비로 인한 다음 요청 30초 timeout 패턴 제거.
- **재시도 경로 정상화**: `async_get_with_login()` 이 `DhAPIError` 외에 timeout 등 `DhLotteryError` 도 동일하게 잡아 항상 풀 세션 리셋 + 재로그인하도록 변경. 기존 로직은 첫 실패 후 ensure 만 하고 재요청해서 망가진 세션을 재사용하던 문제 해결.
- **로그인 응답 누수 수정**: `async_login()` 의 POST 응답을 `async with` 로 감싸 body 누수 방지.
- 요청 타임아웃 30s → 15s (connect 10s) 로 단축해 실패를 빨리 감지.

### Note
- GitHub 원본 레포가 삭제되어 동행복권 사이트의 mainMode=Y 간소화 페이지 운영으로 인해 발생한 세션 hang 문제를 패치한 로컬 빌드 버전.
