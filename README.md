# DH Lottery Home Assistant Add-on (App Build)

[![License](https://img.shields.io/github/license/redchupa/ha-app-dhlottery)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/redchupa/ha-app-dhlottery?style=social)](https://github.com/redchupa/ha-app-dhlottery/stargazers)

Home Assistant에서 동행복권 로또 6/45를 자동으로 구매하고 분석할 수 있는 애드온의 **단일 빌드(app) 버전**입니다.

> 메인 저장소(다중 애드온, 패치 채널 포함)는 **[ha-addons-dhlottery](https://github.com/redchupa/ha-addons-dhlottery)** 입니다. 이 레포는 단일 애드온만 빠르게 설치하고 싶을 때 사용하세요.

---

## 주요 기능

- ✅ **자동 구매**: 번호 랜덤 자동 구매
- ✅ **수동 구매**: 번호 수동 입력 + 자동 혼합 (예: `1,2,3,auto,auto,auto`)
- ✅ **실시간 분석**: 당첨번호·상금·통계 자동 업데이트
- ✅ **자동화 연동**: HA 자동화 트리거/액션 지원
- ✅ **통계 분석**: Hot / Cold 번호, 출현 빈도
- ✅ **예치금 관리**: 잔액 및 구매 가능 금액 모니터링
- ✅ **MQTT Discovery**: HA 자동 통합
- ✅ **REST API**: 외부 시스템 연동
- ✅ **모바일 알림**: 구매 완료, 당첨번호 발표 알림

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

1. Add-on Store에서 **DH Lotto 45 (App)** 선택
2. **Install** 클릭
3. Configuration 탭에서 설정:

```yaml
username: ""        # 동행복권 아이디
password: ""        # 동행복권 비밀번호
update_interval: 3600
use_mqtt: true
mqtt_url: "mqtt://homeassistant.local:1883"
mqtt_username: ""
mqtt_password: ""
```

4. **Start** 클릭 → Log 탭에서 "Login successful" 확인

---

## 사용 전 필수 체크

1. 동행복권 사이트 https://www.dhlottery.co.kr 에 직접 들어가서
   회원가입 → 로그인 → 마이페이지 → **건전구매 서약하기** (필수)
2. 예치금 충전 (자동 구매에 필요)

---

## 생성되는 엔티티 / API

`ha-addons-dhlottery`와 동일한 센서·버튼·REST API를 제공합니다. 자세한 항목은 메인 저장소 [README](https://github.com/redchupa/ha-addons-dhlottery#readme)를 참고하세요.

| 분류 | 엔티티/API 예시 |
|---|---|
| 예치금 | `sensor.dhlotto_<id>_lotto45_balance` |
| 당첨번호 | `sensor.dhlotto_<id>_lotto645_winning_numbers`, `number1`~`number6`, `bonus` |
| 상금/당첨자 | `first_prize`/`first_winners` ~ `fifth_prize`/`fifth_winners` |
| 통계 | `top_frequency_number`, `hot_numbers`, `cold_numbers`, `total_winning` |
| 구매 내역 | `latest_purchase`, `purchase_history_count`, `game_1`~`game_5` |
| 자동 구매 버튼 | `button.dhlotto_<id>_buy_auto_1`, `buy_auto_5` |
| REST API | `http://homeassistant.local:60099/{health,balance,stats,buy,buy/auto,buy/history}` |

Swagger UI: `http://homeassistant.local:60099/docs`

---

## 자동화 / 대시보드 예시

자동화 YAML 예시와 대시보드 카드 예시는 메인 저장소 [ha-addons-dhlottery](https://github.com/redchupa/ha-addons-dhlottery)의 첨부 yaml을 그대로 사용 가능합니다.

---

## 문제 해결

| 증상 | 해결 |
|---|---|
| 로그인 실패 | 동행복권 웹사이트 직접 로그인 테스트 → 5회 실패 시 잠금, 잠시 대기 |
| 센서 미갱신 | `update_interval` 확인, `homeassistant.update_entity` 수동 호출 |
| MQTT 센서 미생성 | `use_mqtt: true` 확인, MQTT 브로커 동작 확인 |
| 구매 실패 | 시간(평일 06–24시, 토 06–20시) / 예치금 / 주간 5게임 제한 확인 |
| 포트 충돌 | 60099 포트 다른 애드온 확인 |

---

## 참고 사항

- **구매 시간**: 평일·일 06:00–24:00, 토 06:00–20:00
- **주간 제한**: 최대 5게임
- **게임당 비용**: 1,000원
- **기본 업데이트**: 3600초 (1시간)
- **보안**: 비밀번호 암호화 저장, HTTPS 통신

---

## 후원

이 애드온이 유용하셨다면 커피 한 잔 후원 부탁드립니다!

<table>
  <tr>
    <td align="center">
      <b>Toss (토스)</b><br>
      <img src="https://raw.githubusercontent.com/redchupa/ha-addons-dhlottery/main/images/toss-donation.png" width="200">
    </td>
    <td align="center">
      <b>PayPal</b><br>
      <img src="https://raw.githubusercontent.com/redchupa/ha-addons-dhlottery/main/images/paypal-donation.png" width="200">
    </td>
  </tr>
</table>

---

## 지원 / 문의

- **Issues**: https://github.com/redchupa/ha-app-dhlottery/issues
- **Discussions**: https://github.com/redchupa/ha-app-dhlottery/discussions
- **메인 저장소**: https://github.com/redchupa/ha-addons-dhlottery

---

## 라이선스

MIT License — [LICENSE](LICENSE)

---

## 면책 조항

본 프로젝트는 동행복권과 공식적인 관계가 없는 개인 학습용 프로젝트입니다.
모든 데이터 요청은 사용자 환경에서 직접 이루어지며, 데이터를 외부에 저장/중계하지 않습니다.
사용에 따른 책임은 사용자에게 있습니다.

---

**Made with ❤️ for Home Assistant Community**
