# Screenshot 은 Playwright 우선, Chrome CLI 폴백, 캡처 전 HTTP 확인

날짜: 2026-10-01

## 배경

Phase 6 는 Playwright 로 Desktop / Mobile Screenshot 을 만들고, 새 프로젝트·명시적 refresh 때만 갱신하며, 실패해도 Sync 를 멈추지 않도록 요구한다. 사용자 Mac 에 Playwright 가 설치되어 있다는 보장은 없다.

## 결정

1. 캡처 엔진은 자동 선택한다. Playwright (설치된 Chrome 사용, 없으면 Playwright Chromium) 가 있으면 Desktop + Mobile, 없으면 시스템 Chrome CLI 로 Desktop 만. 엔진이 없으면 경고 후 건너뛴다.
2. 캡처 전에 `live_url` 이 HTTP 400 미만으로 응답하는지 확인한다. Chrome CLI 는 로딩 실패를 알려주지 않아 오류 페이지를 저장할 위험이 있기 때문이다.
3. 이미지 형식은 Pillow(WebP) → cwebp → sips(JPEG) → PNG 순으로 쓸 수 있는 것을 쓴다. 실제 경로는 manifest 에 기록하므로 확장자가 달라도 된다.
4. 갱신 조건: 새 프로젝트, live_url 변경, 파일 없음, 30일 경과(SPEC §18 "일정 기간"), 명시적 refresh, `screenshot_refresh: true`.
5. 상태는 `data/screenshots.json` 에 따로 둔다. sync 는 이 manifest 에서 파일이 실제로 있는 것만 `screenshots` 로 붙인다. 그래서 sync 가 레포 항목을 다시 만들어도 Screenshot 이 사라지지 않는다.
6. portfolio.yml 에 `screenshot: false` 를 추가했다. 로그인 후 개인 데이터가 보이는 서비스를 공개 사이트에 올리지 않기 위한 opt-out 이다.
7. 업데이터는 sync 다음에 Screenshot 단계를 실행하고, 결과물(`assets/projects/**`, `data/screenshots.json`)만 commit 대상에 추가한다.

## 영향

- 현재 실데이터에는 `liveUrl` 이 있는 프로젝트가 없어 Screenshot 대상이 0개다. 각 레포 portfolio.yml 에 `live_url` 을 넣은 뒤 업데이터를 실행하면 생성된다.
- 개발·검증은 로컬 HTTP 서버의 샘플 페이지로만 했다. 실제 서비스(pacer, life 등)는 캡처하지 않았다.

## 되돌릴 조건

- Screenshot 이 저장소 크기를 과하게 키우면 해상도/품질을 낮추거나 Mobile 을 끈다.
