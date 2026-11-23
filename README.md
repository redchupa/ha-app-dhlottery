# DH Lottery Home Assistant Add-on

[![License](https://img.shields.io/github/license/redchupa/ha-app-dhlottery)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/redchupa/ha-app-dhlottery?style=social)](https://github.com/redchupa/ha-app-dhlottery/stargazers)

Home Assistant에서 **동행복권 로또 6/45를 자동으로 구매하고 분석**할 수 있는 애드온입니다.
실시간 당첨 결과, 통계 분석(Hot/Cold), 예치금 관리, MQTT Discovery, REST API를 한 번에 제공합니다.

> [!WARNING]
> **사용 전 필수 확인 (면책 안내)**
> 본 애드온은 동행복권과 무관한 비공식 개인 오픈소스 프로젝트입니다. 모든 통신은 사용자의 Home Assistant 로컬 환경에서 직접 이루어지며 외부 서버로 데이터를 전송하거나 중계하지 않습니다. 동행복권 이용약관 위반 소지 및 사용 중 발생하는 계정 정지, 오구매, 금전적 손실 등 모든 책임은 사용자 본인에게 있습니다. 자세한 내용은 하단 [면책 조항](#면책-조항)을 반드시 읽어주세요.

---

## 주요 기능

- ✅ **자동 구매**: 번호 랜덤 자동 구매 (1게임 / 5게임)
- ✅ **수동 구매**: 번호 수동 입력 + 자동 혼합 (예: `1,2,3,auto,auto,auto`)
- ✅ **가족용 다중 계정 지원**: 최대 **4개 계정**까지 지원 (계정 간 20초 보안 간격 적용)
- ✅ **주간 구매 한도 보호**: 1계정당 주간 최대 **5게임(5,000원)** 강제 제한
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
- [다중 계정 사용 및 자동화 주의사항](#다중-계정-사용-및-자동화-주의사항)
- [생성되는 센서](#생성되는-센서)
- [버튼 엔티티](#버튼-엔티티)
- [REST API](#rest-api)
- [문제 해결](#문제-해결)
- [참고 사항](#참고-사항)
- [후원](#-후원)
- [라이선스](#라이선스)
- [면책 조항](#면책-조항)

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
3. Configuration 탭에서 설정 (최대 **4개 계정**까지 등록 가능):

```yaml
accounts:
  - username: "my_account_1"   # 동행복권 아이디
    password: "my_password_1"  # 동행복권 비밀번호
    enabled: true
  # 가족 구성원 추가 시 (최대 4계정까지만 로드됨)
  # - username: "family_account_2"
  #   password: "family_password_2"
  #   enabled: true
enable_lotto645: true
enable_pension720: true
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

## 다중 계정 사용 및 자동화 주의사항

> [!IMPORTANT]
> **다중 계정 사용 시 동시 구매는 불가능합니다.**
> 오프라인 복권 판매점 보호, 서버 부하 방지 및 건전한 복권 구매 문화 유지를 위해 아래와 같은 보안 정책이 코드 레벨에 적용되어 있습니다.

### 적용된 보안 제한 정책
1. **최대 4계정 제한**: 동일 가구(가족 구성원)의 개별 동의 하에 최대 **4개 계정**까지만 등록 및 로드됩니다. (4개 초과 설정 시 상위 4개만 로드되며 나머지는 무시됩니다.)
2. **1계정당 주간 최대 5게임(5,000원) 제한**: 로또 6/45는 오프라인 판매점 매출 보호 및 사행성 방지 규정에 따라 **계정당 주간 최대 5게임**까지만 구매할 수 있도록 강제 제한됩니다.
3. **연금복권 720+ 1일 구매 상한선(Hard Limit)**: 자동화 버그로 예치금이 한 번에 소진되는 오구매 사고를 방지하기 위해, 연금복권은 **1계정당 1일 최대 5매(5,000원)**까지만 구매할 수 있도록 코드 레벨 상한선이 적용되어 있습니다.
4. **계정 간 20초 구매 간격 (동시 구매 차단)**:
   - A 계정이 구매 및 구매 정보 조회를 진행 중일 때는 다른 계정(B)의 구매 요청이 즉시 차단됩니다.
   - A 계정의 구매 및 구매 정보 조회가 완료된 시점부터 **최소 20초**가 지나야 다른 계정(B)으로 구매할 수 있습니다.
   - 20초 이내에 다른 계정으로 구매를 시도하면 구매가 실행되지 않으며, 해당 계정의 오류 센서(`sensor.dhlotto_{username}_lotto45_purchase_error`)에 남은 대기 시간이 표시됩니다.
5. **폴링 하한선 및 랜덤 지연(Jitter)**: 서버 부하 방지를 위해 센서 갱신 주기는 **최소 1,800초(30분)** 이상으로 제한되며, 요청 집중을 막기 위해 랜덤 지연(Jitter)이 자동 적용됩니다.

### Home Assistant 자동화 작성 가이드

다중 계정을 사용하는 경우, **하나의 자동화에서 여러 계정의 구매 버튼을 동시에 누르면 두 번째 계정부터 보안 로직에 의해 차단**됩니다.
반드시 아래 예시처럼 **계정 사이에 최소 30초 이상의 `delay`를 두거나**, 계정별로 자동화 실행 시각을 다르게 설정해 주세요.

```yaml
# ✅ 올바른 자동화 예시 (계정 간 충분한 지연 시간 추가)
alias: "가족 로또 자동 구매"
trigger:
  - platform: time
    at: "10:15:00"
action:
  # 1) 첫 번째 계정 구매
  - service: button.press
    target:
      entity_id: button.dhlotto_account1_buy_auto_5

  # 2) 구매 및 조회 완료 + 20초 보안 간격 확보를 위해 30초 이상 대기
  - delay: "00:00:30"

  # 3) 두 번째 계정 구매
  - service: button.press
    target:
      entity_id: button.dhlotto_account2_buy_auto_5
```

> [!TIP]
> 매주 토요일 마감 직전(19:50~20:00)이나 정각(09:00, 10:00 등)에 트래픽이 몰리는 시간대는 피하고, 여유 있는 시간대에 계정별로 1분 이상 간격을 두어 자동화를 분산 실행하는 것을 권장합니다.

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
- **주간 한도**: 1계정당 최대 5게임 (5,000원)
- **다중 계정 간격**: 다른 계정 구매 및 조회 완료 후 20초 경과 필수
- **예치금**: 게임당 1,000원

---

## REST API

포트 **60099** 로 접근 가능합니다.

**Base URL**: `http://homeassistant.local:60099`

### 조회 (GET)
- `/health` — 상태 확인 (계정 상태, 최대 계정 수, 주간 한도, 계정 간 쿨다운 정책 포함)
- `/accounts` — 등록된 계정 목록 및 로그인 상태
- `/api/ingress` — Home Assistant Ingress 경유 여부

### Swagger UI
- 외부 직접 접근: `http://homeassistant.local:60099/docs`
- HA Ingress 경로: `/api-docs`

---

## 문제 해결

| 증상 | 해결 |
|---|---|
| 로그인 실패 | 동행복권 웹에서 직접 로그인 테스트 → 5회 실패 시 잠금. 잠시 대기 후 재시도. 2차 인증(OTP) 계정은 미지원. |
| 다중 계정 구매 차단 | 다른 계정 구매 및 조회 완료 후 **20초**가 지나야 다음 계정 구매가 가능합니다. HA 자동화에서 액션 간 `delay: "00:00:30"` 이상을 추가하세요. |
| 5번째 이상 계정 미로드 | 보안 정책상 최대 **4계정**까지만 지원합니다. |
| 센서 미갱신 | `update_interval` 확인. `homeassistant.update_entity` 서비스로 수동 호출. |
| MQTT 센서 미생성 | `use_mqtt: true` / MQTT 브로커 동작 / `mqtt_url` 정확성 확인. 애드온 재시작. |
| 구매 실패 | 시간 / 예치금 / 주간 5게임 한도 / Log 탭 에러 메시지 확인. |
| 포트 충돌 | 60099 점유 애드온 확인. |

---

## 참고 사항

- **구매 가능 시간**: 평일·일 06:00–24:00, 토 06:00–20:00
- **주간 한도**: 1계정당 최대 5게임 (5,000원)
- **최대 계정 수**: 최대 4계정
- **다중 계정 구매 간격**: 계정 간 최소 20초 (동시 구매 불가)
- **게임당 비용**: 1,000원
- **기본 갱신 주기**: 3600초 (1시간, 최소 1800초 + 랜덤 지연 적용)
- **연금복권 1일 상한선**: 1계정당 최대 5매 (5,000원, 오구매 방지)
- **수동 갱신**: Developer Tools → Services → `homeassistant.update_entity`
- **보안**: 100% 로컬 실행, 외부 서버 미전송, 로그 아이디 마스킹, HTTPS 통신

---

## ☕ 후원

이 애드온이 도움이 되셨다면 따뜻한 커피 한 잔으로 응원해 주세요 🙏  
*(본 프로젝트의 모든 기능은 100% 무료로 제공되며, 후원은 순수 자발적 응원 목적입니다.)*

<table>
  <tr>
    <td align="center">
      <b>토스 (Toss)</b><br/>
      <img src="https://raw.githubusercontent.com/redchupa/ha-app-dhlottery/main/images/toss-donation.png" alt="Toss 후원 QR" width="200"/><br/>
      <code>1000-1261-7813</code> (우*만)
    </td>
    <td align="center">
      <b>PayPal</b><br/>
      <img src="https://raw.githubusercontent.com/redchupa/ha-app-dhlottery/main/images/paypal-donation.png" alt="PayPal 후원 QR" width="200"/>
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

1. **비공식 오픈소스 프로젝트**: 본 프로젝트는 주식회사 동행복권 및 복권위원회와 어떠한 공식적인 제휴·후원·승인 관계도 없는 개인 학습 및 편의 목적의 비공식 오픈소스 프로젝트입니다.
2. **로컬 실행 및 개인정보 보호**: 모든 로그인, 조회, 구매 요청은 사용자 본인의 로컬 Home Assistant 환경에서 동행복권 서버로 직접 통신합니다. 개발자는 사용자의 계정 정보, 비밀번호, 구매 내역 등 어떠한 데이터도 수집·저장·중계하지 않습니다.
3. **이용약관 및 법적 책임**: 동행복권은 공식 외부 API를 제공하지 않으며, 자동화 도구 사용은 동행복권 이용약관에 위배될 소지가 있습니다. 본 애드온의 설치 및 사용으로 인해 발생할 수 있는 계정 정지, 서비스 이용 제한, 오구매, 중복 구매, 당첨 확인 오류, 금전적 손실 등 모든 직·간접적 결과에 대한 책임은 전적으로 사용자 본인에게 있습니다.
4. **건전한 이용 및 상업적 악용 금지**: 본 애드온은 오프라인 복권 판매점과의 상생 및 사행성 방지를 위해 **1계정당 주간 5게임(5,000원) 제한, 최대 4계정 제한, 계정 간 20초 구매 간격 제한**을 두고 있습니다. 본 소스코드를 타인의 복권 구매 대행, 영리 목적의 유료 판매, 한도 우회 또는 서버에 과도한 부하를 주는 용도로 변조·악용하는 행위를 엄격히 금지하며, 이로 인한 모든 법적 책임은 행위자 본인에게 있습니다.
5. **무보증(AS-IS) 및 중단 안내**: 본 소프트웨어는 MIT 라이선스에 따라 어떠한 명시적·묵시적 보증 없이 "있는 그대로(AS-IS)" 제공됩니다. 동행복권 사이트의 구조 변경으로 인해 기능이 예고 없이 동작하지 않을 수 있으며, 동행복권 또는 관계 기관의 요청이 있을 경우 사전 예고 없이 배포 및 유지보수가 즉시 중단될 수 있습니다.

---

## 기여

1. Fork
2. Feature 브랜치 생성 (`git checkout -b feature/AmazingFeature`)
3. 커밋 (`git commit -m 'Add some AmazingFeature'`)
4. Push (`git push origin feature/AmazingFeature`)
5. Pull Request 생성

---

**Made with ❤️ for Home Assistant Community**
