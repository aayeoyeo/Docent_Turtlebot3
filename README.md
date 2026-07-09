# 🤖 AI 도슨트 로봇 프로젝트 (Autonomous Docent Robot)

## 📌 프로젝트 개요
본 프로젝트는 **ROS 2(Humble)** 기반의 터틀봇3를 활용하여, 전시관에서 관람객을 안내하고 작품을 해설하는 **'자율주행 AI 도슨트 로봇 시스템'**을 구현한 프로젝트입니다. 

단순한 라인 트레이싱을 넘어, 로봇이 스스로 QR 코드를 인식해 전시물을 판별하고, 관람객의 얼굴을 인식하여 해설을 진행하는 **지능형 상태 머신(State Machine)**을 구축했습니다. 또한, 웹 브라우저를 통한 원격 관제 및 CCTV 스트리밍 기능을 더해 실전 활용도를 극대화했습니다.

## ✨ 주요 기능 (Key Features)
1. **자율 주행 및 전시물 인식:** 로봇 뷰어(스마트폰) 카메라로 전시물의 QR 코드를 인식하여 지정된 위치에 정지.
2. **상황 인지형 TTS 해설:** 코스 데이터(JSON)에 입력된 대본을 TTS(Text-to-Speech)로 읽어주며 해설 진행.
3. **AI 관람객 얼굴 인식:** 해설 완료 후, `tracking.js` 기반의 경량 AI 모델이 관람객의 얼굴을 인식해야만 다음 코스로 이동.
4. **웹 기반 실시간 관제소 (Web UI):** * 노트북에서 로봇의 현재 상태(IDLE, MOVE, EXPLAIN)와 진행률 실시간 모니터링.
   * 로봇의 시야를 노트북 화면으로 실시간 전송 (Base64 이미지 스트리밍).
   * 비상시 자동 주행을 멈추고 조이패드로 수동 원격 조종 가능 (MANUAL 모드).

## 🛠 기술 스택 (Tech Stack)
* **Hardware:** TurtleBot3 (Burger), Raspberry Pi 4, 스마트폰(로봇 시각/청각), 우분투 노트북(관제탑)
* **Software / Framework:** ROS 2 (Humble), Python 3
* **Web & AI:** HTML5, JavaScript, `roslibjs` (WebSockets), `tracking.js` (Face Detection), Web Speech API


## 🛠 1. 공통 작업 (터틀봇3, 우분투 노트북)

### ROS 2 환경 변수 설정

로봇과 노트북이 통신할 수 있도록 고유 도메인 ID를 설정합니다. 터미널을 열고 아래 명령어를 입력하세요.

```bash
echo "export ROS_DOMAIN_ID=7" >> ~/.bashrc
source ~/.bashrc

```

### 노트북 필수 패키지 설치

노트북 터미널에서 웹 소켓 통신을 위한 브릿지 패키지를 설치합니다.

```bash
sudo apt update
sudo apt install ros-humble-rosbridge-suite

```

---

## 🍓 2. 라즈베리파이 (터틀봇3) 패키지 세팅

### 워크스페이스 및 패키지 생성

라즈베리파이에 SSH로 접속한 뒤 아래 명령어를 순서대로 입력합니다.

```bash
mkdir -p ~/project-root/ros2_ws/src
cd ~/project-root/ros2_ws/src
ros2 pkg create --build-type ament_python docent_robot --dependencies rclpy std_msgs geometry_msgs

```

### 도슨트 노드(파이썬) 코드 작성

```bash
cd ~/project-root/ros2_ws/src/docent_robot/docent_robot
nano docent_node.py

```

편집기가 열리면 아래 코드를 전체 복사하여 붙여넣고 저장합니다. (`Ctrl+O` -> `Enter` -> `Ctrl+X`)

```python
#!/usr/bin/env python3
import json
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from geometry_msgs.msg import Twist

CRUISE = 0.08
WAIT_AUDIENCE = 20.0
MOVE_TIMEOUT = 30.0

class DocentNode(Node):
    def __init__(self):
        super().__init__('docent_node')
        self.sub_course = self.create_subscription(String, '/course', self.on_course, 10)
        self.sub_qr = self.create_subscription(String, '/exhibit_seen', self.on_qr, 10)
        self.sub_tts = self.create_subscription(Bool, '/tts_done', self.on_tts_done, 10)
        self.sub_face = self.create_subscription(Bool, '/audience', self.on_audience, 10)
        self.sub_phase = self.create_subscription(String, '/set_phase', self.on_set_phase, 10)

        self.pub_vel = self.create_publisher(Twist, '/cmd_vel', 10)
        self.pub_tts = self.create_publisher(String, '/tts_text', 10)
        self.pub_state = self.create_publisher(String, '/tour_state', 10)
        self.pub_stats = self.create_publisher(String, '/tour_stats', 10)

        self.course = []
        self.idx = 0
        self.phase = 'IDLE'
        self.audience = False
        self.state_since = time.time()
        self.arrive_time = 0.0
        self.tour_stats = []
        self.last_exhibit_id = ""
        self.macro_queue = []
        self.current_macro = None
        self.macro_start_time = 0.0
        self.last_cmd = Twist()

        self.timer = self.create_timer(0.1, self.tick)
        self.get_logger().info('🤖 도슨트 로봇 백엔드 시스템 구동 완료! 대기 중입니다.')

    def broadcast(self):
        msg = String()
        msg.data = json.dumps({
            'phase': self.phase,
            'idx': self.idx,
            'total': len(self.course),
            'current_exhibit': self.course[self.idx]['id'] if self.course and self.idx < len(self.course) else 'None',
            'current_title': self.course[self.idx]['title'] if self.course and self.idx < len(self.course) else 'None'
        }, ensure_ascii=False)
        self.pub_state.publish(msg)

    def on_set_phase(self, msg):
        self.phase = msg.data
        self.state_since = time.time()
        if self.phase == 'IDLE':
            self.pub_vel.publish(Twist())
            self.last_cmd = Twist()
        self.broadcast()

    def on_course(self, msg):
        self.course = json.loads(msg.data)
        self.idx = 0
        self.last_exhibit_id = ""
        self.tour_stats = []
        self.prepare_next_move()
        self.broadcast()

    def prepare_next_move(self):
        if self.course and self.idx < len(self.course):
            current_exhibit = self.course[self.idx]
            if 'macro' in current_exhibit and isinstance(current_exhibit['macro'], list) and len(current_exhibit['macro']) > 0:
                self.macro_queue = list(current_exhibit['macro'])
                self.current_macro = None
                self.phase = 'MACRO'
                self.get_logger().info(f"[{current_exhibit['id']}] 향해 매크로 주행 시작.")
            else:
                self.phase = 'MOVE'
                self.publish_twist(CRUISE, 0.0)
                self.get_logger().info(f"[{current_exhibit['id']}] 향해 일반 직진 주행 시작.")
        else:
            self.phase = 'IDLE'
            self.pub_vel.publish(Twist())
            self.last_cmd = Twist()
        self.state_since = time.time()

    def on_qr(self, msg):
        if self.phase in ['MOVE', 'MACRO'] and self.course:
            if msg.data == self.last_exhibit_id:
                return
            for i, exhibit in enumerate(self.course):
                if msg.data == exhibit['id']:
                    self.idx = i
                    self.phase = 'EXPLAIN'
                    self.arrive_time = time.time()
                    self.pub_vel.publish(Twist())
                    self.last_cmd = Twist()
                    tts = String()
                    tts.data = self.course[self.idx]['script']
                    self.pub_tts.publish(tts)
                    self.broadcast()
                    break

    def on_tts_done(self, msg):
        if self.phase == 'EXPLAIN' and msg.data:
            self.phase = 'CHECK'
            self.state_since = time.time()
            self.broadcast()

    def on_audience(self, msg):
        self.audience = bool(msg.data)

    def publish_twist(self, linear, angular):
        cmd = Twist()
        cmd.linear.x = float(linear)
        cmd.angular.z = float(angular)
        if cmd.linear.x != self.last_cmd.linear.x or cmd.angular.z != self.last_cmd.angular.z:
            self.pub_vel.publish(cmd)
            self.last_cmd = cmd

    def tick(self):
        now = time.time()
        elapsed = now - self.state_since

        if self.phase == 'MACRO':
            if self.current_macro is None:
                if len(self.macro_queue) > 0:
                    self.current_macro = self.macro_queue.pop(0)
                    self.macro_start_time = now
                else:
                    self.phase = 'MOVE'
                    self.state_since = time.time()
                    self.publish_twist(CRUISE, 0.0)
                    self.broadcast()
                    return
            macro_elapsed = now - self.macro_start_time
            if macro_elapsed < self.current_macro['duration']:
                self.publish_twist(self.current_macro['linear'], self.current_macro['angular'])
            else:
                self.current_macro = None

        elif self.phase == 'MOVE':
            if elapsed > MOVE_TIMEOUT:
                self.phase = 'IDLE'
                self.pub_vel.publish(Twist())
                self.last_cmd = Twist()
                self.broadcast()
            else:
                self.publish_twist(CRUISE, 0.0)

        elif self.phase == 'CHECK':
            if self.audience or elapsed > WAIT_AUDIENCE:
                duration = time.time() - self.arrive_time
                self.tour_stats.append({
                    'id': self.course[self.idx]['id'],
                    'title': self.course[self.idx]['title'],
                    'duration': round(duration, 1)
                })
                stats_msg = String()
                stats_msg.data = json.dumps(self.tour_stats, ensure_ascii=False)
                self.pub_stats.publish(stats_msg)

                self.last_exhibit_id = self.course[self.idx]['id']
                self.idx += 1
                self.prepare_next_move()
                self.broadcast()

def main():
    rclpy.init()
    node = DocentNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
```

### setup.py 수정 및 패키지 빌드

명령어 실행 경로를 등록하기 위해 `setup.py`를 수정합니다.

```bash
cd ~/project-root/ros2_ws/src/docent_robot
nano setup.py

```

`entry_points` 부분을 찾아 아래와 같이 수정하고 저장합니다.

```python
    entry_points={
        'console_scripts': [
            'docent_node = docent_robot.docent_node:main'
        ],
    },

```

수정이 완료되면 워크스페이스를 빌드합니다.

```bash
cd ~/project-root/ros2_ws
colcon build --symlink-install
source install/setup.bash

```

---

## 💻 3. 노트북(관제탑) 웹 서버 세팅

노트북 터미널에서 웹 파일용 디렉터리를 만들고 이동합니다.

```bash
mkdir -p ~/project-root/docent_web
cd ~/project-root/docent_web

```

### robot.html (스마트폰 뷰어) 생성

```bash
nano robot.html

```

아래 HTML 코드를 붙여넣고 저장합니다.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>로봇 센서 통합 인터페이스</title>
    <script src="https://cdn.jsdelivr.net/npm/roslib@1/build/roslib.min.js"></script>
    <script src="https://unpkg.com/html5-qrcode"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/tracking.js/1.1.3/tracking-min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/tracking.js/1.1.3/data/face-min.js"></script>
    <style>
        body { font-family: sans-serif; text-align: center; padding: 20px; background-color: #222; color: white;}
        #reader { width: 100%; max-width: 400px; margin: 0 auto; border-radius: 10px; overflow: hidden; background: #000; }
        button { padding: 15px 30px; font-size: 20px; margin: 20px; background-color: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer;}
        .status { margin-top: 20px; padding: 10px; background: #333; border-radius: 5px; }
        #exhibitDisplay {
            margin: 15px auto;
            padding: 15px;
            max-width: 370px;
            background-color: #111;
            border: 3px solid #4CAF50;
            border-radius: 8px;
            font-size: 26px;
            font-weight: bold;
            color: #2ecc71;
            box-shadow: 0 0 10px rgba(76, 175, 80, 0.5);
        }
    </style>
</head>
<body>
    <h1>🤖 도슨트 센서 모듈</h1>
    <button id="startBtn">투어 준비 (클릭 필수)</button>

    <div id="reader"></div>

    <div id="exhibitDisplay">📢 안내 대기 중</div>

    <div class="status">
        <p>ROS 연결 상태: <span id="ros_status" style="color:red;">끊김</span></p>
        <p>최근 본 QR: <span id="last_qr">-</span></p>
        <button id="faceBtn" style="background-color: #008CBA; pointer-events: none;">👤 관람객 대기 중...</button>

        <hr style="border-color: #555; margin: 15px 0;">
        <p>🗣️ <strong>TTS 재생 설정</strong></p>
        <label for="rateSlider">재생 속도: <span id="rateValue">1.0</span>x</label><br>
        <input type="range" id="rateSlider" min="0.5" max="2.0" step="0.1" value="1.0" style="width: 80%;">
    </div>

    <script>
        const ros = new ROSLIB.Ros({ url: 'ws://' + window.location.hostname + ':9090' });

        ros.on('connection', () => { document.getElementById('ros_status').innerText = '연결됨'; document.getElementById('ros_status').style.color = 'lime'; });
        ros.on('error', () => { document.getElementById('ros_status').innerText = '에러'; });
        ros.on('close', () => { document.getElementById('ros_status').innerText = '끊김'; document.getElementById('ros_status').style.color = 'red'; });

        const ttsTextTopic = new ROSLIB.Topic({ ros: ros, name: '/tts_text', messageType: 'std_msgs/String' });
        const ttsDoneTopic = new ROSLIB.Topic({ ros: ros, name: '/tts_done', messageType: 'std_msgs/Bool' });
        const qrTopic = new ROSLIB.Topic({ ros: ros, name: '/exhibit_seen', messageType: 'std_msgs/String' });
        const audienceTopic = new ROSLIB.Topic({ ros: ros, name: '/audience', messageType: 'std_msgs/Bool' });
        const cameraStreamTopic = new ROSLIB.Topic({ ros: ros, name: '/camera_stream', messageType: 'std_msgs/String' });
        const stateTopic = new ROSLIB.Topic({ ros: ros, name: '/tour_state', messageType: 'std_msgs/String' });

        let currentPhase = 'IDLE';
        let ttsEnabled = false;
        const rateSlider = document.getElementById('rateSlider');
        const rateValue = document.getElementById('rateValue');

        window.utterances = [];

        rateSlider.oninput = function() { rateValue.innerText = this.value; }

        document.getElementById('startBtn').addEventListener('click', () => {
            ttsEnabled = true;
            document.getElementById('startBtn').innerText = "준비 완료 (재생 대기중)";
            document.getElementById('startBtn').style.backgroundColor = "#555";

            const emptyUtterance = new SpeechSynthesisUtterance("");
            window.speechSynthesis.speak(emptyUtterance);
        });

        ttsTextTopic.subscribe((msg) => {
            if(!ttsEnabled) return alert("투어 준비 버튼을 먼저 눌러주세요!");

            window.speechSynthesis.cancel();

            const u = new SpeechSynthesisUtterance(msg.data);
            window.utterances.push(u);

            u.lang = 'ko-KR';
            u.rate = parseFloat(rateSlider.value);

            u.onend = () => {
                ttsDoneTopic.publish(new ROSLIB.Message({ data: true }));
            };

            u.onerror = (e) => {
                ttsDoneTopic.publish(new ROSLIB.Message({ data: true }));
            };

            window.speechSynthesis.speak(u);
        });

        stateTopic.subscribe((msg) => {
            const state = JSON.parse(msg.data);
            currentPhase = state.phase;
            const display = document.getElementById('exhibitDisplay');

            if (state.phase === 'MOVE') {
                display.innerText = "🏃 목적지로 이동 중...";
                display.style.color = "#3498db";
                display.style.borderColor = "#3498db";
            } else if (state.phase === 'EXPLAIN') {
                display.innerText = `🎨 전시물: ${state.current_title}`;
                display.style.color = "#2ecc71";
                display.style.borderColor = "#2ecc71";
            } else if (state.phase === 'CHECK') {
                display.innerText = "👤 관람객 확인 중...";
                display.style.color = "#f1c40f";
                display.style.borderColor = "#f1c40f";
            } else if (state.phase === 'MANUAL') {
                display.innerText = "🚨 수동 제어 모드";
                display.style.color = "#e74c3c";
                display.style.borderColor = "#e74c3c";
            } else {
                display.innerText = "📢 안내 대기 중";
                display.style.color = "#ffffff";
                display.style.borderColor = "#ffffff";
            }
        });

        const html5QrCode = new Html5Qrcode("reader");
        const qrCodeSuccessCallback = (decodedText, decodedResult) => {
            document.getElementById('last_qr').innerText = decodedText;
            qrTopic.publish(new ROSLIB.Message({ data: decodedText }));
        };
        const config = { fps: 10, qrbox: { width: 250, height: 250 } };
        html5QrCode.start({ facingMode: "environment" }, config, qrCodeSuccessCallback).catch(err => console.log(err));

        let hasAudience = false;
        
        // --- 업그레이드된 모션 감지 변수 ---
        let previousImageData = null;
        let consecutiveMotion = 0; // 찰나의 흔들림을 거르기 위한 연속 카운터

        function triggerAudienceDetected(methodInfo) {
            if (!hasAudience) {
                hasAudience = true;
                document.getElementById('faceBtn').innerText = `👤 관람객 인식 완료! (${methodInfo})`;
                document.getElementById('faceBtn').style.backgroundColor = "#4CAF50";
                audienceTopic.publish(new ROSLIB.Message({ data: true }));

                setTimeout(() => {
                    hasAudience = false;
                    document.getElementById('faceBtn').innerText = "👤 관람객 대기 중...";
                    document.getElementById('faceBtn').style.backgroundColor = "#555";
                    audienceTopic.publish(new ROSLIB.Message({ data: false }));
                }, 5000);
            }
        }

        setTimeout(() => {
            const videoElement = document.querySelector('#reader video');

            if (videoElement) {
                // 1. 얼굴 인식 (그대로 유지)
                const tracker = new tracking.ObjectTracker('face');
                tracker.setInitialScale(4);
                tracker.setStepSize(2);
                tracker.setEdgesDensity(0.1);
                tracking.track(videoElement, tracker);

                tracker.on('track', function(event) {
                    if (currentPhase !== 'CHECK') return;
                    if (event.data.length > 0) {
                        triggerAudienceDetected("얼굴");
                    }
                });

                const canvas = document.createElement('canvas');
                const context = canvas.getContext('2d');
                canvas.width = 320;
                canvas.height = 240;

                // 2. 고도화된 모션 감지 로직
                setInterval(() => {
                    if (videoElement.readyState === videoElement.HAVE_ENOUGH_DATA) {
                        context.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
                        
                        if (currentPhase === 'CHECK') {
                            const currentImageData = context.getImageData(0, 0, canvas.width, canvas.height);
                            let motionScore = 0;

                            if (previousImageData) {
                                // i += 16: 픽셀을 4칸씩 건너뛰며 검사 (미세 노이즈 방어 및 CPU 최적화)
                                for (let i = 0; i < currentImageData.data.length; i += 16) {
                                    const rDiff = Math.abs(currentImageData.data[i] - previousImageData.data[i]);
                                    const gDiff = Math.abs(currentImageData.data[i+1] - previousImageData.data[i+1]);
                                    const bDiff = Math.abs(currentImageData.data[i+2] - previousImageData.data[i+2]);
                                    
                                    // RGB 차이 합이 150 이상일 때만 유의미한 변화로 인정 (빛 반사 무시)
                                    if (rDiff + gDiff + bDiff > 150) {
                                        motionScore++;
                                    }
                                }
                            }
                            
                            previousImageData = currentImageData;

                            // 화면 픽셀 중 약 5% 이상 크게 바뀌었을 때
                            if (motionScore > 800) {
                                consecutiveMotion++; // 연속 카운트 증가
                                
                                // 3번 연속 (약 0.75초간) 계속 움직임이 감지되어야 찐 관람객으로 인정
                                if (consecutiveMotion >= 3) {
                                    triggerAudienceDetected("모션");
                                    consecutiveMotion = 0; // 발동 후 리셋
                                }
                            } else {
                                // 잠깐 흔들린 거면 가차 없이 카운터 리셋
                                consecutiveMotion = 0; 
                            }
                        } else {
                            previousImageData = null; 
                            consecutiveMotion = 0;
                        }

                        // CCTV 데이터 전송
                        const frameData = canvas.toDataURL('image/jpeg', 0.3);
                        cameraStreamTopic.publish(new ROSLIB.Message({ data: frameData }));
                    }
                }, 250); // 0.25초마다 실행
            }
        }, 3000);
    </script>
</body>
</html>
```

### admin.html (관리자 관제탑) 생성

```bash
nano admin.html

```

아래 HTML 코드를 붙여넣고 저장합니다.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>도슨트 로봇 관리자 관제탑</title>
    <script src="https://cdn.jsdelivr.net/npm/roslib@1/build/roslib.min.js"></script>
    <style>
        body { font-family: sans-serif; margin: 20px; background-color: #f4f4f9; }
        .panel { background: #fff; border: 1px solid #ddd; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        textarea { width: 100%; height: 120px; font-family: monospace; }
        .btn { padding: 10px 20px; background: #333; color: #fff; border: none; cursor: pointer; border-radius: 4px; font-weight: bold; margin: 5px;}
        .btn:hover { background: #555; }
        .btn-red { background: #e74c3c; }
        .btn-green { background: #2ecc71; }
        .btn-orange { background: #f39c12; }
        .btn-purple { background: #9b59b6; font-size: 18px; padding: 15px 30px; }
        
        .macro-box { background: #fff3cd; border: 2px solid #ffeeba; padding: 20px; border-radius: 8px; margin-bottom: 20px; text-align: center; }
        
        .d-pad { display: grid; grid-template-columns: repeat(3, 70px); grid-gap: 10px; justify-content: center; margin-top: 20px; }
        .d-pad button { padding: 20px 10px; font-size: 16px; cursor: pointer; background: #ddd; border: none; border-radius: 5px; user-select: none; font-weight: bold;}
        .d-pad button:active { background: #bbb; }
        .btn-up { grid-column: 2; grid-row: 1; }
        .btn-left { grid-column: 1; grid-row: 2; }
        .btn-right { grid-column: 3; grid-row: 2; }
        .btn-down { grid-column: 2; grid-row: 3; }
        
        .cctv-container { text-align: center; margin-bottom: 20px; }
        #cctv { width: 100%; max-width: 400px; height: auto; background: #000; border: 3px solid #333; border-radius: 8px; min-height: 200px; }
    </style>
</head>
<body>
    <h1>🌐 로봇 원격 관제탑 시스템</h1>

    <div class="macro-box">
        <h3 style="margin: 0 0 10px 0; color: #856404;">🎙️ 곡선 주행 매크로 생성기 (Teach & Play)</h3>
        <p style="margin: 0 0 15px 0; color: #666; font-size: 14px;">
            [녹화 시작]을 누른 후 아래 조이패드로 전진/회전을 조작하면 시간과 궤적이 기록됩니다.<br>
            조작을 마치고 [녹화 종료]를 누르면 자동으로 주행 코드가 복사됩니다.
        </p>
        <button id="recordBtn" class="btn btn-purple" onclick="toggleRecord()">🔴 매크로 녹화 시작</button>
        <div id="recordStatus" style="font-weight: bold; margin-top: 10px; color: #856404;">상태: 대기 중</div>
    </div>

    <div style="display: flex; gap: 20px; flex-wrap: wrap; justify-content: center;">
        
        <div class="panel" style="flex: 1; min-width: 350px; max-width: 500px;">
            <h3>📷 원격 조종 & 카메라 뷰</h3>
            <div class="cctv-container">
                <img id="cctv" src="" alt="로봇 카메라 연결 대기 중...">
            </div>
            
            <div style="text-align: center; margin-bottom: 15px;">
                <button class="btn btn-red" onclick="setPhase('MANUAL')">🚨 수동 모드 전환</button>
                <button class="btn btn-green" onclick="setPhase('MOVE')">✅ 자동 투어 복귀</button><br>
                <button class="btn btn-orange" onclick="forceSkip()">⏭️ 20초 대기 강제 스킵</button>
            </div>

            <div class="d-pad">
                <button class="btn-up" onmousedown="moveRobot(0.1, 0)" onmouseup="stopRobot()">전진</button>
                <button class="btn-left" onmousedown="moveRobot(0, 0.5)" onmouseup="stopRobot()">좌회전</button>
                <button class="btn-right" onmousedown="moveRobot(0, -0.5)" onmouseup="stopRobot()">우회전</button>
                <button class="btn-down" onmousedown="moveRobot(-0.1, 0)" onmouseup="stopRobot()">후진</button>
            </div>
        </div>

        <div style="flex: 1; min-width: 350px; max-width: 500px;">
            <div class="panel">
                <h3>📊 투어 상태 데이터</h3>
                <p>현재 상태: <strong id="phase" style="color:blue; font-size:20px;">IDLE</strong></p>
                <p>진행 상황: <span id="progress">0 / 0</span> (타겟 QR: <span id="current">None</span>)</p>
                
                <hr style="border-color: #ddd;">
                <h4>⏱️ 실시간 관람 체류 통계</h4>
                <div id="statsList" style="text-align: left; font-size: 15px; color: #333; background: #f9f9f9; padding: 15px; border-radius: 5px; max-height: 150px; overflow-y: auto;">
                    기록된 통계가 없습니다.
                </div>
            </div>

            <div class="panel">
                <h3>📝 코스 데이터 및 매크로 주입 (JSON)</h3>
                <textarea id="courseJson">
[
    {
        "id": "E1", 
        "title": "별이 빛나는 밤", 
        "script": "첫 번째 전시물은 빈센트 반 고흐의 대표작인 별이 빛나는 밤입니다. 이 작품은 고흐가 프랑스 생레미의 요양원에 머물던 시절, 방 창문 너머로 바라본 새벽하늘을 그린 것입니다. 화면을 가득 채운 소용돌이치는 밤하늘과 거대하게 타오르는 사이프러스 나무는 당시 고흐가 느꼈던 격정적인 감정과 내면의 불안을 시각적으로 강렬하게 전달합니다. 짙은 파란색과 대조를 이루는 황금빛 별들은 어둠 속에서도 빛을 잃지 않으려는 그의 예술적 열망을 보여줍니다. 차분히 감상하시며 고흐가 마주했던 새벽하늘의 깊은 감동을 느껴보시기 바랍니다.",
        "macro": [] 
    },
    {
        "id": "E2", 
        "title": "모나리자", 
        "script": "두 번째 전시물은 레오나르도 다 빈치의 걸작인 모나리자입니다. 이 작품은 전 세계에서 가장 유명한 초상화로, 주인공의 신비로운 미소로 잘 알려져 있습니다. 다 빈치는 윤곽선을 부드럽게 흐리는 스푸마토 기법을 사용하여 인물의 표정과 배경을 자연스럽고 입체적으로 표현해 냈습니다. 눈썹이 없는 독특한 모습과 보는 각도에 따라 미묘하게 변하는 듯한 입꼬리는 작품에 신비감을 더해줍니다. 또한 인물 뒤로 펼쳐진 정교한 풍경은 르네상스 시대의 이상적인 미학을 완벽하게 보여줍니다. 시대를 초월한 모나리자의 은은한 미소를 가까이서 느껴보시기 바랍니다.",
        "macro": []
    },
    {
        "id": "E3", 
        "title": "해바라기", 
        "script": "마지막 전시물은 불타오르는 태양을 닮은 해바라기입니다. 고흐는 동료 화가 고갱과 함께할 아를의 작업실을 장식하기 위해 이 연작을 그렸습니다. 화면을 가득 채운 화사한 노란색은 고흐에게 있어 순수한 기쁨과 희망, 그리고 생명의 에너지를 상징하는 색이었습니다. 붓을 두껍게 칠하는 임파스토 기법을 사용해 해바라기 씨앗과 꽃잎의 강인한 생명력을 입체적으로 살려냈습니다. 시들어가는 꽃과 활짝 피어난 꽃을 한 화폭에 담아내어 삶과 죽음의 순환을 예술적으로 승화시켰습니다. 고흐의 뜨거운 예술적 영혼과 고갱을 향한 환대의 마음을 느껴보시기 바랍니다.",
        "macro": []
    }
]
                </textarea><br><br>
                <button class="btn" onclick="sendCourse()" style="width: 100%; padding: 12px; font-size: 16px;">🚀 로봇에 코스 전송 (투어 시작)</button>
            </div>
        </div>
    </div>

    <script>
        const ros = new ROSLIB.Ros({ url: 'ws://' + window.location.hostname + ':9090' });
        
        const courseTopic = new ROSLIB.Topic({ ros: ros, name: '/course', messageType: 'std_msgs/String' });
        const stateTopic = new ROSLIB.Topic({ ros: ros, name: '/tour_state', messageType: 'std_msgs/String' });
        const cmdVelTopic = new ROSLIB.Topic({ ros: ros, name: '/cmd_vel', messageType: 'geometry_msgs/Twist' });
        const setPhaseTopic = new ROSLIB.Topic({ ros: ros, name: '/set_phase', messageType: 'std_msgs/String' });
        const cameraStreamTopic = new ROSLIB.Topic({ ros: ros, name: '/camera_stream', messageType: 'std_msgs/String' });
        const statsTopic = new ROSLIB.Topic({ ros: ros, name: '/tour_stats', messageType: 'std_msgs/String' });
        const audienceTopic = new ROSLIB.Topic({ ros: ros, name: '/audience', messageType: 'std_msgs/Bool' });

        let isRecording = false;
        let recordedMacro = [];
        let currentMoveStartTime = 0;
        let activeTwist = { linear: 0, angular: 0 };

        stateTopic.subscribe((msg) => {
            const state = JSON.parse(msg.data);
            document.getElementById('phase').innerText = state.phase;
            if(state.phase === 'MANUAL') document.getElementById('phase').style.color = 'red';
            else if(state.phase === 'MACRO') document.getElementById('phase').style.color = 'purple';
            else document.getElementById('phase').style.color = 'blue';
            
            document.getElementById('progress').innerText = `${state.idx + 1} / ${state.total}`;
            document.getElementById('current').innerText = state.current_exhibit;
        });

        cameraStreamTopic.subscribe((msg) => {
            document.getElementById('cctv').src = msg.data;
        });

        statsTopic.subscribe((msg) => {
            try {
                const statsData = JSON.parse(msg.data);
                // [방법 2 적용 완료] 예쁜 UI 리스트 형태로 출력
                let htmlContent = '<ul style="margin: 0; padding-left: 20px;">';
                statsData.forEach(item => {
                    htmlContent += `<li style="margin-bottom: 8px;"><strong>${item.title} (${item.id})</strong>: <span style="color: #e74c3c; font-weight: bold;">${item.duration}초</span> 체류</li>`;
                });
                htmlContent += '</ul>';
                document.getElementById('statsList').innerHTML = htmlContent;
            } catch (e) {
                console.error("통계 파싱 에러:", e);
            }
        });

        function sendCourse() {
            const data = document.getElementById('courseJson').value;
            try {
                const cleanData = JSON.stringify(JSON.parse(data));
                courseTopic.publish(new ROSLIB.Message({ data: cleanData }));
                alert("코스가 주입되었습니다!");
            } catch (e) {
                alert("JSON 형식이 올바르지 않습니다: " + e.message);
            }
        }

        function setPhase(newPhase) {
            setPhaseTopic.publish(new ROSLIB.Message({ data: newPhase }));
        }

        function forceSkip() {
            audienceTopic.publish(new ROSLIB.Message({ data: true }));
        }

        function moveRobot(linear, angular) {
            const twist = new ROSLIB.Message({
                linear: { x: linear, y: 0.0, z: 0.0 },
                angular: { x: 0.0, y: 0.0, z: angular }
            });
            cmdVelTopic.publish(twist);

            if (isRecording) {
                const now = Date.now();
                if ((activeTwist.linear !== 0 || activeTwist.angular !== 0) && 
                    (activeTwist.linear !== linear || activeTwist.angular !== angular)) {
                    const duration = (now - currentMoveStartTime) / 1000.0;
                    recordedMacro.push({ 
                        linear: activeTwist.linear, 
                        angular: activeTwist.angular, 
                        duration: parseFloat(duration.toFixed(2)) 
                    });
                }
                if (activeTwist.linear !== linear || activeTwist.angular !== angular) {
                    activeTwist = { linear: linear, angular: angular };
                    currentMoveStartTime = now;
                }
            }
        }

        function stopRobot() {
            moveRobot(0.0, 0.0);
        }

        function toggleRecord() {
            const btn = document.getElementById('recordBtn');
            const status = document.getElementById('recordStatus');
            
            if (!isRecording) {
                isRecording = true;
                recordedMacro = [];
                activeTwist = { linear: 0, angular: 0 };
                setPhase('MANUAL');
                
                btn.innerText = "⏹️ 녹화 종료 및 코드 생성";
                btn.style.backgroundColor = "#e74c3c";
                status.innerText = "상태: 🔴 녹화 중... 조이패드로 움직이세요.";
            } else {
                isRecording = false;
                btn.innerText = "🔴 매크로 녹화 시작";
                btn.style.backgroundColor = "#9b59b6";
                
                if (recordedMacro.length > 0) {
                    const macroString = JSON.stringify(recordedMacro);
                    navigator.clipboard.writeText(`"macro": ${macroString}`).then(() => {
                        status.innerText = "상태: ✅ 복사 완료! 코스 편집 창의 macro: [] 내부에 넣으세요.";
                        alert("주행 코드가 복사되었습니다!\n\n코스 편집창의 주행 데이터 내부의 [] 안에 붙여넣기(Ctrl+V) 하세요.");
                    }).catch(() => {
                        status.innerText = "상태: 녹화 완료";
                        prompt("아래 코드를 복사해서 붙여넣으세요:", `"macro": ${macroString}`);
                    });
                } else {
                    status.innerText = "상태: 녹화된 데이터가 없습니다.";
                }
            }
        }
    </script>
</body>
</html>
```

---

## 📱 4. 스마트폰 카메라 권한 설정 (사전 준비)

스마트폰 브라우저에서 카메라를 웹 서버로 허용하기 위한 작업입니다.

1. 스마트폰 크롬 브라우저 주소창에 `chrome://flags` 입력 후 접속
2. 검색창에 `insecure` 검색
3. **Insecure origins treated as secure** 항목 하단 빈칸에 노트북 주소(`http://노트북IP:8000`) 입력
4. 버튼을 [Enabled]로 변경 후 하단의 파란색 **[Relaunch]** 버튼 클릭

---

## 🚀 5. 최종 실행 가이드 (터미널 4개 구동)

터미널 4개를 열고 아래 순서대로 실행합니다.

### 🍓 [터미널 1] 라즈베리파이: 로봇 하드웨어 구동

가장 먼저 로봇의 모터와 센서를 깨우는 작업입니다.

```bash
ros2 launch turtlebot3_bringup robot.launch.py

```

*(실행 후 여러 로그가 올라가면 성공입니다. 창을 그대로 둡니다.)*

### 💻 [터미널 2] 노트북: ROS-Web 통신 브릿지 연결

로봇과 웹 브라우저가 대화할 수 있게 통신망을 엽니다.

```bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml

```

*(`Rosbridge WebSocket server started on port 9090` 문구가 뜨면 성공)*

### 💻 [터미널 3] 노트북: 로컬 웹 서버 구동

우리가 만든 HTML 파일들을 스마트폰에서 접속할 수 있게 서버를 엽니다.

```bash
cd ~/project-root/docent_web
python3 -m http.server 8000

```

*(`Serving HTTP on 0.0.0.0 port 8000`이 뜨면 성공)*

### 🍓 [터미널 4] 라즈베리파이: 도슨트 메인 노드(두뇌) 구동

로봇의 주행과 AI를 통제하는 메인 파이썬 코드를 실행합니다.

```bash
cd ~/project-root/ros2_ws
source install/setup.bash
ros2 run docent_robot docent_node

```

*(`[INFO] [docent_node]: 도슨트 로봇 백엔드 시스템 구동 완료`가 뜨면 성공)*

---

## 🎮 6. 접속 및 시스템 운영

* **스마트폰 (로봇 거치용):** `http://<노트북IP>:8000/robot.html`
접속 후 카메라 권한을 허용하고 **[투어 준비]** 버튼을 반드시 클릭해야 합니다. 이 스마트폰이 로봇의 '눈(카메라)'과 '입(TTS 음성)' 역할을 합니다.
* **노트북 (관리자용):** `http://localhost:8000/admin.html`
노트북 화면에 띄워두고 코스를 주입하거나 수동으로 로봇을 제어하는 관제탑입니다.
* **투어 코스용 QR 생성:**
`qr-code-generator.com` 등의 사이트에서 텍스트(Text) 모드로 `E1`, `E2` 값을 가진 QR코드를 생성하여 전시장(벽면)에 부착합니다.
