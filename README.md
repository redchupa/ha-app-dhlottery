# DH Lottery Home Assistant Add-on

[![License](https://img.shields.io/github/license/redchupa/ha-app-dhlottery)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/redchupa/ha-app-dhlottery?style=social)](https://github.com/redchupa/ha-app-dhlottery/stargazers)

Home Assistant에서 **동행복권 로또 6/45를 자동으로 구매하고 분석**할 수 있는 애드온입니다.
실시간 당첨 결과, 통계 분석(Hot/Cold), 예치금 관리, MQTT Discovery, REST API를 한 번에 제공합니다.

---

## 주요 기능

- ✅ **자동 구매**: 번호 랜덤 자동 구매
- ✅ **수동 구매**: 번호 수동 입력 + 자동 혼합 (예: `1,2,3,auto,auto,auto`)
- ✅ **실시간 분석**: 당첨번호·상금·통계 자동 업데이트
- ✅ **자동화 연동**: HA 자동화 트리거/액션 지원
- ✅ **통계 분석**: Hot / Cold 번호, 출현 빈도
- ✅ **예치금 관리**: 잔액 및 구매 가능 금액 모니터링
- ✅ **MQTT Discovery**: HA 자동 통합
- ✅ **REST API**: 외부 시스템 연동 + Swagger UI
- ✅ **모바일 알림**: 구매 완료, 당첨번호 발표 알림

---

## 목차

- [설치](#설치)
- [사용 전 필수 체크](#사용-전-필수-체크)
- [생성되는 센서](#생성되는-센서)
- [버튼 엔티티](#버튼-엔티티)
- [REST API](#rest-api)
- [문제 해결](#문제-해결)
- [참고 사항](#참고-사항)
- [후원](#후원)
- [라이선스](#라이선스)

---

## 설치

### 저장소 추가

1. Home Assistant → **Settings** → **Add-ons** → **Add-on Store**
2. 우측 상단 메뉴(⋮) → **Repositories**
3. 다음 URL 추가:
   ```
   https://github.com/redchupa/ha-app-dhlottery
   ```

### 애드온 설치

1. Add-on Store에서 **DH Lotto 45** 선택
2. **Install** 클릭
3. Configuration 탭에서 설정:

```yaml
username: ""        # 동행복권 아이디
password: ""        # 동행복권 비밀번호
enable_lotto645: true
update_interval: 3600   # 센서 갱신 주기(초), 기본 1시간
use_mqtt: true
mqtt_url: "mqtt://homeassistant.local:1883"
mqtt_username: ""
mqtt_password: ""
```

4. **Start** 클릭 → **Log** 탭에서 `Login successful` 확인

---

## 사용 전 필수 체크

1. 동행복권 사이트 https://www.dhlottery.co.kr 에서  
   회원가입 → 로그인 → 마이페이지 → **건전구매 서약하기** (필수)
2. 자동 구매를 위해 **예치금 충전** 필요

---

## 생성되는 센서

애드온을 시작하면 다음 센서들이 자동으로 생성됩니다.

<details>
<summary><b>계정 정보 센서</b></summary>

### 동행복권 예치금
- **센서 ID**: `sensor.dhlotto_{username}_lotto45_balance`
- **단위**: KRW
- **추가 속성**:
  - `purchase_available`: 구매 가능 금액
  - `reservation_purchase`: 예약 구매 금액
  - `withdrawal_request`: 출금 신청 중 금액
  - `this_month_accumulated`: 이번 달 누적 구매 금액

</details>

<details>
<summary><b>로또 당첨 결과 센서</b></summary>

### 기본 정보
- `sensor.dhlotto_{username}_lotto645_round` — 최신 회차
- `sensor.dhlotto_{username}_lotto645_draw_date` — 추첨일 (YYYY-MM-DD)
- `sensor.dhlotto_{username}_lotto645_winning_numbers` — 전체 당첨번호

### 당첨번호 (개별)
- `sensor.dhlotto_{username}_lotto645_number1` ~ `number6`
- `sensor.dhlotto_{username}_lotto645_bonus`

</details>

<details>
<summary><b>상금 및 당첨자 정보 센서</b></summary>

### 총 판매액
- `sensor.dhlotto_{username}_lotto645_total_sales` (KRW)

### 등수별 정보
각 등수마다 **상금**과 **당첨자** 센서가 생성됩니다:

- 1등: `first_prize`, `first_winners`
- 2등: `second_prize`, `second_winners`
- 3등: `third_prize`, `third_winners`
- 4등: `fourth_prize`, `fourth_winners`
- 5등: `fifth_prize`, `fifth_winners`
- 전체: `total_winners`

</details>

<details>
<summary><b>번호 통계 분석 센서</b></summary>

- `sensor.dhlotto_{username}_lotto45_top_frequency_number` — 최다 출현 번호 (최근 50회차)
- `sensor.dhlotto_{username}_lotto45_hot_numbers` — 핫 넘버 (최근 20회차 상위 10개)
- `sensor.dhlotto_{username}_lotto45_cold_numbers` — 콜드 넘버 (최근 20회차 하위 10개)
- `sensor.dhlotto_{username}_lotto45_total_winning` — 총 당첨금 (최근 1년, KRW)

#### `total_winning` 추가 속성
- `total_purchase`: 총 구매 금액
- `total_purchase_count`: 총 구매 횟수
- `total_winning_count`: 총 당첨 횟수
- `win_rate`: 당첨률 (%)
- `roi`: 수익률 (%)
- `rank_distribution`: 등수별 당첨 횟수

</details>

<details>
<summary><b>구매 내역 센서</b></summary>

- `sensor.dhlotto_{username}_lotto45_latest_purchase` — 가장 최근 구매 정보
- `sensor.dhlotto_{username}_lotto45_purchase_history_count` — 구매 기록 수 (최근 1주)
- `sensor.dhlotto_{username}_lotto45_game_1` ~ `game_5` — 구매한 게임별 번호

#### `latest_purchase` 추가 속성
`round_no`, `barcode`, `result`, `games`, `games_count`

#### `game_*` 추가 속성
`slot`(A~E), `mode`(자동/수동/반자동), `numbers`, `round_no`, `result`

</details>

<details>
<summary><b>시스템 센서</b></summary>

- `sensor.dhlotto_{username}_lotto45_last_update` — 마지막 업데이트 시간

</details>

---

## 버튼 엔티티

MQTT Discovery를 활성화하면 자동 구매 버튼이 생성됩니다.

- `button.dhlotto_{username}_buy_auto_1` — 1게임 자동 구매
- `button.dhlotto_{username}_buy_auto_5` — 5게임 자동 구매 (주간 최대)

### 사용 시 자동 체크
- **구매 가능 시간**: 평일·일 06:00–24:00, 토 06:00–20:00
- **주간 한도**: 최대 5게임
- **예치금**: 게임당 1,000원

---

## REST API

포트 **60099** 로 접근 가능합니다.

**Base URL**: `http://homeassistant.local:60099`

### 조회 (GET)
- `/health` — 상태 확인
- `/balance` — 예치금
- `/stats` — 통계 정보
- `/buy/history` — 구매 내역

### 실행 (POST)
- `/random?count=6&games=1` — 랜덤 번호 생성
- `/check` — 당첨 확인
- `/buy` — 로또 구매
- `/buy/auto?count=1` — 자동 구매

### 예시

```bash
curl http://homeassistant.local:60099/health
curl http://homeassistant.local:60099/balance
curl -X POST "http://homeassistant.local:60099/random?count=6&games=2"
curl -X POST "http://homeassistant.local:60099/buy/auto?count=3"
```

### Swagger UI
- 외부 직접 접근: `http://homeassistant.local:60099/docs`
- HA Ingress 경로: `/api-docs`

---

## 문제 해결

| 증상 | 해결 |
|---|---|
| 로그인 실패 | 동행복권 웹에서 직접 로그인 테스트 → 5회 실패 시 잠금. 잠시 대기 후 재시도. 2차 인증(OTP) 계정은 미지원. |
| 센서 미갱신 | `update_interval` 확인. `homeassistant.update_entity` 서비스로 수동 호출. |
| MQTT 센서 미생성 | `use_mqtt: true` / MQTT 브로커 동작 / `mqtt_url` 정확성 확인. 애드온 재시작. |
| 구매 실패 | 시간 / 예치금 / 주간 5게임 한도 / Log 탭 에러 메시지 확인. |
| 포트 충돌 | 60099 점유 애드온 확인. |

---

## 참고 사항

- **구매 가능 시간**: 평일·일 06:00–24:00, 토 06:00–20:00
- **주간 한도**: 최대 5게임
- **게임당 비용**: 1,000원
- **기본 갱신 주기**: 3600초 (1시간)
- **수동 갱신**: Developer Tools → Services → `homeassistant.update_entity`
- **보안**: 비밀번호 암호화 저장, 세션 자동 관리, HTTPS

---

## 후원

이 애드온이 유용하셨다면 커피 한 잔 후원 부탁드립니다! 🙏

<table>
  <tr>
    <td align="center">
      <b>Toss (토스)</b><br>
      <img src="https://raw.githubusercontent.com/redchupa/ha-app-dhlottery/main/images/toss-donation.png" width="200">
    </td>
    <td align="center">
      <b>PayPal</b><br>
      <img src="https://raw.githubusercontent.com/redchupa/ha-app-dhlottery/main/images/paypal-donation.png" width="200">
    </td>
  </tr>
</table>

---

## 지원 / 문의

- **Issues**: https://github.com/redchupa/ha-app-dhlottery/issues
- **Discussions**: https://github.com/redchupa/ha-app-dhlottery/discussions

---

## 라이선스

MIT License — [LICENSE](LICENSE)

---

## 면책 조항

본 프로젝트는 동행복권과 공식적인 관계가 없는 개인 학습용 프로젝트입니다.
모든 데이터 요청은 사용자 환경에서 직접 이루어지며, 데이터를 외부에 저장/중계하지 않습니다.
사용에 따른 책임은 사용자에게 있습니다.

---

## 기여

1. Fork
2. Feature 브랜치 생성 (`git checkout -b feature/AmazingFeature`)
3. 커밋 (`git commit -m 'Add some AmazingFeature'`)
4. Push (`git push origin feature/AmazingFeature`)
5. Pull Request 생성

---

**Made with ❤️ for Home Assistant Community**
