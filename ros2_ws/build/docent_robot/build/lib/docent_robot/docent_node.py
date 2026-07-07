#!/usr/bin/env python3
import json, time
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
        self.sub_course = self.create_subscription(String, '/course', self.on_course, 10)
        self.sub_qr = self.create_subscription(String, '/exhibit_seen', self.on_qr, 10)
        self.sub_tts = self.create_subscription(Bool, '/tts_done', self.on_tts_done, 10)
        self.sub_face = self.create_subscription(Bool, '/audience', self.on_audience, 10)
        
        # 🚨 수동 모드 강제 전환을 위한 토픽 추가
        self.sub_mode = self.create_subscription(String, '/set_phase', self.on_set_phase, 10)

        self.pub_vel = self.create_publisher(Twist, '/cmd_vel', 10)
        self.pub_tts = self.create_publisher(String, '/tts_text', 10)
        self.pub_state = self.create_publisher(String, '/tour_state', 10)

        self.course = []
        self.idx = 0
        self.phase = 'IDLE'       # IDLE -> MOVE -> EXPLAIN -> CHECK -> MANUAL
        self.audience = False
        self.state_since = time.time()

        self.timer = self.create_timer(0.1, self.tick)
        self.get_logger().info('도슨트 로봇 백엔드 시스템(수동조작 지원) 구동 완료')

    def broadcast(self):
        msg = String()
        msg.data = json.dumps({
            'phase': self.phase,
            'idx': self.idx,
            'total': len(self.course),
            'current_exhibit': self.course[self.idx]['id'] if self.course and self.idx < len(self.course) else 'None'
        }, ensure_ascii=False)
        self.pub_state.publish(msg)

    def on_course(self, msg):
        self.get_logger().info('새로운 코스가 할당되었습니다.')
        self.course = json.loads(msg.data)
        self.idx = 0
        self.phase = 'MOVE'
        self.state_since = time.time()
        self.broadcast()

    # 🚨 관리자 웹에서 상태(MANUAL/IDLE)를 쐈을 때 강제 변경하는 함수
    def on_set_phase(self, msg):
        self.get_logger().info(f"로봇 상태 강제 변경: {msg.data}")
        self.phase = msg.data
        self.broadcast()

    def on_qr(self, msg):
        if self.phase == 'MOVE' and self.course:
            if msg.data == self.course[self.idx]['id']:
                self.get_logger().info(f"전시물 {msg.data} 도착. 해설을 시작합니다.")
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
        cmd = Twist()
        now = time.time()
        elapsed = now - self.state_since

        # 🚨 핵심: MANUAL 모드일 땐 자동 주행 로직을 아예 무시 (노트북 조이패드가 통제함)
        if self.phase == 'MANUAL':
            return 

        if self.phase == 'MOVE':
            if elapsed > MOVE_TIMEOUT:
                self.get_logger().warn("QR 미인식 타임아웃! 로봇을 정지합니다.")
                self.phase = 'IDLE'
                self.broadcast()
            else:
                cmd.linear.x = CRUISE

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

        # EXPLAIN이나 IDLE 상태일 때는 cmd.linear.x = 0.0 이므로 정지
        self.pub_vel.publish(cmd)

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
