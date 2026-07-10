# 📑 토픽 인터페이스 정의서 — 4조

## 1. 토픽 상세 명세 표

| 토픽명 | 메시지 타입 | 발행자 (Publisher) | 구독자 (Subscriber) | 주기 | 성격 | QoS 정책 | 설명 |
|---|---|---|---|---|---|---|---|
| `/course` | `std_msgs/msg/String` | 관제탑 웹앱 (`admin.html`) | 중앙 도슨트 노드 (`docent_node`) | 변화 시 (이벤트성) | 엣지 (Edge) | **RELIABLE** / Volatile | 관제탑에서 편집된 전시물 ID, 타이틀, 해설 대본을 포함한 JSON 문자열 주입 |
| `/exhibit_seen` | `std_msgs/msg/String` | 스마트폰 웹앱 (`robot.html`) | 중앙 도슨트 노드 (`docent_node`) | 인식 즉시 (이벤트성) | 엣지 (Edge) | **RELIABLE** / Volatile | 디바이스 카메라가 QR 코드를 인식했을 때 디코딩된 전시물 고유 ID(`E1`, `E2` 등) 발행 |
| `/tts_text` | `std_msgs/msg/String` | 중앙 도슨트 노드 (`docent_node`) | 스마트폰 웹앱 (`robot.html`) | 상태 전환 시 | 엣지 (Edge) | **RELIABLE** / Volatile | 로봇이 목적지 도착 후 관람객에게 송출할 도슨트 해설용 순수 텍스트 스크립트 데이터 |
| `/tts_done` | `std_msgs/msg/Bool` | 스마트폰 웹앱 (`robot.html`) | 중앙 도슨트 노드 (`docent_node`) | 완료 시 (이벤트성) | 엣지 (Edge) | **RELIABLE** / Volatile | 디바이스의 Web Speech API 해설 재생이 완전히 완료되었음을 알리는 플래그 (`true`) |
| `/audience` | `std_msgs/msg/Bool` | 스마트폰 웹앱 (`robot.html`) | 중앙 도슨트 노드 (`docent_node`) | 상태 변화 시 | 엣지 (Edge) | **RELIABLE** / Volatile | `tracking.js` 엔진의 안면 유무 판정 결과 (`true`/`false`). 최초 인식 및 소실 시에만 발행 |
| `/set_phase` | `std_msgs/msg/String` | 관제탑 웹앱 (`admin.html`) | 중앙 도슨트 노드 (`docent_node`) | 관리자 개입 시 | 엣지 (Edge) | **RELIABLE** / Volatile | 비상 정지 및 수동 모드 강제 전이 명령 문자열 발행 (`MANUAL` 또는 `IDLE`) |
| `/tour_state` | `std_msgs/msg/String` | 중앙 도슨트 노드 (`docent_node`) | 관제탑 웹앱 (`admin.html`) | 상태 변화 시 | 엣지 (Edge) | **RELIABLE** / Volatile | 현재 로봇의 제어 Phase, 가동 인덱스, 총 코스 수, 타겟 작품 정보가 담긴 JSON 문자열 브로드캐스트 |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 중앙 도슨트 노드 (`docent_node`) <br> 관제탑 웹앱 (`admin.html`) | 터틀봇 하드웨어 구동 노드 | 10Hz (주행 시) | 연속 (Continuous) | **RELIABLE** / Volatile | 로봇의 실질적인 선속도 및 각속도 제어 명령 벡터 (수동 모드 시 관제탑이 발행 권한 소유) |
| `/camera_stream` | `std_msgs/msg/String` | 스마트폰 웹앱 (`robot.html`) | 관제탑 웹앱 (`admin.html`) | 4Hz (250ms) | 연속 (Continuous) | **BEST_EFFORT** / Volatile | 실시간 관제 모니터링을 위해 스마트폰 카메라 캔버스를 JPEG 압축 후 인코딩한 Base64 데이터 |

## 2. 데이터 구조 명세 (JSON Schema 예시)

### 2.1 `/course` 토픽 페이로드 규격
```json
[
  {
    "id": "E1",
    "title": "별이 빛나는 밤",
    "script": "첫 번째 전시물, 별이 빛나는 밤입니다. 이 작품은 고흐의 대표작입니다."
  },
  {
    "id": "E2",
    "title": "모나리자",
    "script": "두 번째 전시물, 모나리자입니다. 신비로운 미소가 특징입니다."
  }
]

```

### 2.2 `/tour_state` 토픽 페이로드 규격

```json
{
  "phase": "MOVE",
  "idx": 0,
  "total": 2,
  "current_exhibit": "E1"
}

```
