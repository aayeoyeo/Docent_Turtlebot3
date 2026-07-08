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
WAIT_AUDIENCE = 20.0       # 관람객 미확인 최대 대기 (초)
MOVE_TIMEOUT = 30.0        # QR 미인식 시 최대 이동 시간 (초)

class DocentNode(Node):
    def __init__(self):
        super().__init__('docent_node')
        # Subscriber 등록
        self.sub_course = self.create_subscription(String, '/course', self.on_course, 10)
        self.sub_qr = self.create_subscription(String, '/exhibit_seen', self.on_qr, 10)
        self.sub_tts = self.create_subscription(Bool, '/tts_done', self.on_tts_done, 10)
        self.sub_face = self.create_subscription(Bool, '/audience', self.on_audience, 10)
        self.sub_phase = self.create_subscription(String, '/set_phase', self.on_set_phase, 10)

        # Publisher 등록
        self.pub_vel = self.create_publisher(Twist, '/cmd_vel', 10)
        self.pub_tts = self.create_publisher(String, '/tts_text', 10)
        self.pub_state = self.create_publisher(String, '/tour_state', 10)

        # 상태 변수 초기화
        self.course = []
        self.idx = 0
        self.phase = 'IDLE'
        self.audience = False
        self.state_since = time.time()

        # 10Hz 제어 타이머 주기 구동
        self.timer = self.create_timer(0.1, self.tick)
        self.get_logger().info('도슨트 로봇 백엔드 시스템 구동 완료')

    def broadcast(self):
        msg = String()
        msg.data = json.dumps({
            'phase': self.phase,
            'idx': self.idx,
            'total': len(self.course),
            'current_exhibit': self.course[self.idx]['id'] if self.course and self.idx < len(self.course) else 'None'
        }, ensure_ascii=False)
        self.pub_state.publish(msg)

    def on_set_phase(self, msg):
        self.get_logger().warn(f"관리자 개입: 상태가 {msg.data}(으)로 강제 전환됩니다.")
        stop_cmd = Twist()
        self.pub_vel.publish(stop_cmd)
        self.phase = msg.data
        self.state_since = time.time()
        self.broadcast()

    def on_course(self, msg):
        self.get_logger().info('새로운 코스가 할당되었습니다.')
        self.course = json.loads(msg.data)
        self.idx = 0
        self.phase = 'MOVE'
        self.state_since = time.time()
        self.broadcast()

    def on_qr(self, msg):
        if self.phase == 'MOVE' and self.course:
            if msg.data == self.course[self.idx]['id']:
                self.get_logger().info(f"전시물 {msg.data} 도착. 해설을 시작합니다.")
                stop_cmd = Twist()
                self.pub_vel.publish(stop_cmd)
                self.phase = 'EXPLAIN'
                tts = String()
                tts.data = self.course[self.idx]['script']
                self.pub_tts.publish(tts)
                self.broadcast()

    def on_tts_done(self, msg):
        if self.phase == 'EXPLAIN' and msg.data:
            self.get_logger().info("해설 완료. 관람객을 확인합니다.")
            self.phase = 'CHECK'
            self.state_since = time.time()
            self.broadcast()

    def on_audience(self, msg):
        self.audience = bool(msg.data)

    def tick(self):
        now = time.time()
        elapsed = now - self.state_since

        if self.phase == 'MOVE':
            if elapsed > MOVE_TIMEOUT:
                self.get_logger().warn("QR 미인식 타임아웃! 로봇을 정지합니다.")
                stop_cmd = Twist()
                self.pub_vel.publish(stop_cmd)
                self.phase = 'IDLE'
                self.broadcast()
            else:
                cmd = Twist()
                cmd.linear.x = CRUISE
                self.pub_vel.publish(cmd)

        elif self.phase == 'CHECK':
            if self.audience or elapsed > WAIT_AUDIENCE:
                if self.audience:
                    self.get_logger().info("관람객 확인됨. 다음 코스로 이동.")
                else:
                    self.get_logger().warn("관람객 부재. 20초 경과로 다음 코스로 강제 이동.")

                self.idx += 1
                if self.idx < len(self.course):
                    self.phase = 'MOVE'
                    self.state_since = time.time()
                else:
                    self.phase = 'IDLE'
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
    </style>
</head>
<body>
    <h1>🤖 도슨트 센서 모듈</h1>
    <button id="startBtn">투어 준비 (클릭 필수)</button>
    <div id="reader"></div>
    <div class="status">
        <p>ROS 연결 상태: <span id="ros_status" style="color:red;">끊김</span></p>
        <p>최근 본 QR: <span id="last_qr">-</span></p>
        <button id="faceBtn" style="background-color: #008CBA; pointer-events: none;">👤 관람객 대기 중...</button>
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

        let ttsEnabled = false;
        document.getElementById('startBtn').addEventListener('click', () => {
            ttsEnabled = true;
            document.getElementById('startBtn').innerText = "준비 완료 (재생 대기중)";
            document.getElementById('startBtn').style.backgroundColor = "#555";
            const u = new SpeechSynthesisUtterance("");
            window.speechSynthesis.speak(u);
        });

        ttsTextTopic.subscribe((msg) => {
            if(!ttsEnabled) return alert("투어 준비 버튼을 먼저 눌러주세요!");
            const u = new SpeechSynthesisUtterance(msg.data);
            u.lang = 'ko-KR';
            u.rate = 1.0;
            u.onend = () => {
                ttsDoneTopic.publish(new ROSLIB.Message({ data: true }));
            };
            window.speechSynthesis.speak(u);
        });

        const html5QrCode = new Html5Qrcode("reader");
        const qrCodeSuccessCallback = (decodedText, decodedResult) => {
            document.getElementById('last_qr').innerText = decodedText;
            qrTopic.publish(new ROSLIB.Message({ data: decodedText }));
        };
        const config = { fps: 10, qrbox: { width: 250, height: 250 } };
        html5QrCode.start({ facingMode: "environment" }, config, qrCodeSuccessCallback).catch(err => console.log(err));

        let hasAudience = false;
        setTimeout(() => {
            const videoElement = document.querySelector('#reader video');

            if (videoElement) {
                const tracker = new tracking.ObjectTracker('face');
                tracker.setInitialScale(4);
                tracker.setStepSize(2);
                tracker.setEdgesDensity(0.1);
                tracking.track(videoElement, tracker);

                tracker.on('track', function(event) {
                    if (event.data.length > 0 && !hasAudience) {
                        hasAudience = true;
                        document.getElementById('faceBtn').innerText = "👤 카메라 얼굴 인식 완료!";
                        document.getElementById('faceBtn').style.backgroundColor = "#4CAF50";
                        audienceTopic.publish(new ROSLIB.Message({ data: true }));

                        setTimeout(() => {
                            hasAudience = false;
                            document.getElementById('faceBtn').innerText = "👤 관람객 대기 중...";
                            document.getElementById('faceBtn').style.backgroundColor = "#555";
                            audienceTopic.publish(new ROSLIB.Message({ data: false }));
                        }, 5000);
                    }
                });

                const canvas = document.createElement('canvas');
                const context = canvas.getContext('2d');
                canvas.width = 320;
                canvas.height = 240;

                setInterval(() => {
                    if (videoElement.readyState === videoElement.HAVE_ENOUGH_DATA) {
                        context.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
                        const frameData = canvas.toDataURL('image/jpeg', 0.3);
                        cameraStreamTopic.publish(new ROSLIB.Message({ data: frameData }));
                    }
                }, 250);
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
    <title>도슨트 로봇 관리자</title>
    <script src="https://cdn.jsdelivr.net/npm/roslib@1/build/roslib.min.js"></script>
    <style>
        body { font-family: sans-serif; margin: 20px; background-color: #f4f4f9; }
        .panel { background: #fff; border: 1px solid #ddd; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        textarea { width: 100%; height: 150px; font-family: monospace; }
        .btn { padding: 10px 20px; background: #333; color: #fff; border: none; cursor: pointer; border-radius: 4px; font-weight: bold;}
        .btn:hover { background: #555; }
        .btn-red { background: #e74c3c; }
        .btn-green { background: #2ecc71; }

        .d-pad { display: grid; grid-template-columns: repeat(3, 60px); grid-gap: 10px; justify-content: center; margin-top: 20px; }
        .d-pad button { padding: 15px; font-size: 16px; cursor: pointer; background: #ddd; border: none; border-radius: 5px; user-select: none; font-weight: bold;}
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
    <h1>🌐 로봇 관제탑 & 원격 조종 모듈</h1>

    <div style="display: flex; gap: 20px; flex-wrap: wrap;">

        <div class="panel" style="flex: 1; min-width: 320px;">
            <h3>📷 실시간 CCTV & 수동 조종</h3>
            <div class="cctv-container">
                <img id="cctv" src="" alt="스마트폰 연결 대기중...">
            </div>

            <div style="text-align: center; margin-bottom: 15px;">
                <button class="btn btn-red" onclick="setPhase('MANUAL')">🚨 수동 모드 (강제정지)</button>
                <button class="btn btn-green" onclick="setPhase('IDLE')">✅ 자동 투어 복귀</button>
            </div>

            <div class="d-pad">
                <button class="btn-up" onmousedown="moveRobot(0.1, 0)" onmouseup="stopRobot()">전진</button>
                <button class="btn-left" onmousedown="moveRobot(0, 0.5)" onmouseup="stopRobot()">좌</button>
                <button class="btn-right" onmousedown="moveRobot(0, -0.5)" onmouseup="stopRobot()">우</button>
                <button class="btn-down" onmousedown="moveRobot(-0.1, 0)" onmouseup="stopRobot()">후진</button>
            </div>
            <p style="text-align:center; font-size: 13px; color: #666; margin-top:10px;">* 방향키를 마우스로 꾹 누르면 이동합니다.</p>
        </div>

        <div style="flex: 1; min-width: 320px;">
            <div class="panel">
                <h3>📊 투어 현황 모니터링</h3>
                <p>현재 상태: <strong id="phase" style="color:blue; font-size:20px;">IDLE</strong></p>
                <p>진행 상황: <span id="progress">0 / 0</span> (현재 타겟: <span id="current">None</span>)</p>
            </div>

            <div class="panel">
                <h3>📝 투어 코스 편집 (JSON)</h3>
                <textarea id="courseJson">
[
    {"id":"E1", "title":"별이 빛나는 밤", "script":"첫 번째 전시물, 별이 빛나는 밤입니다. 이 작품은 고흐의 대표작입니다."},
    {"id":"E2", "title":"모나리자", "script":"두 번째 전시물, 모나리자입니다. 신비로운 미소가 특징입니다."}
]
                </textarea><br><br>
                <button class="btn" onclick="sendCourse()" style="width: 100%;">🚀 코스 로봇에 주입 (투어 시작)</button>
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

        stateTopic.subscribe((msg) => {
            const state = JSON.parse(msg.data);
            document.getElementById('phase').innerText = state.phase;
            if(state.phase === 'MANUAL') document.getElementById('phase').style.color = 'red';
            else document.getElementById('phase').style.color = 'blue';

            document.getElementById('progress').innerText = `${state.idx + 1} / ${state.total}`;
            document.getElementById('current').innerText = state.current_exhibit;
        });

        cameraStreamTopic.subscribe((msg) => {
            document.getElementById('cctv').src = msg.data;
        });

        function sendCourse() {
            const data = document.getElementById('courseJson').value;
            try {
                JSON.parse(data);
                courseTopic.publish(new ROSLIB.Message({ data: data }));
                alert("코스가 성공적으로 전송되었습니다!");
            } catch (e) {
                alert("JSON 형식이 잘못되었습니다. 오타를 확인해주세요.");
            }
        }

        function setPhase(newPhase) {
            setPhaseTopic.publish(new ROSLIB.Message({ data: newPhase }));
        }

        function moveRobot(linear, angular) {
            const twist = new ROSLIB.Message({
                linear: { x: linear, y: 0.0, z: 0.0 },
                angular: { x: 0.0, y: 0.0, z: angular }
            });
            cmdVelTopic.publish(twist);
        }

        function stopRobot() {
            moveRobot(0.0, 0.0);
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
