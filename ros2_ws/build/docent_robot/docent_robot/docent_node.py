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
        self.pub_stats = self.create_publisher(String, '/tour_stats', 10)
        
        # 상태 변수 초기화
        self.course = []          
        self.idx = 0
        self.phase = 'IDLE'       
        self.audience = False
        self.state_since = time.time()
        
        # [S3] 도착 시간 및 통계 리스트 초기화
        self.arrive_time = 0.0
        self.tour_stats = []
        
        # 10Hz 제어 타이머 주기 구동
        self.timer = self.create_timer(0.1, self.tick)
        self.get_logger().info('도슨트 로봇 백엔드 시스템 구동 완료')

    def broadcast(self):
        msg = String()
        msg.data = json.dumps({
            'phase': self.phase, 
            'idx': self.idx,
            'total': len(self.course),
            'current_exhibit': self.course[self.idx]['id'] if self.course and self.idx < len(self.course) else 'None',
            # [LCD 대체] 현재 전시물의 실제 제목 전송
            'current_title': self.course[self.idx]['title'] if self.course and self.idx < len(self.course) else 'None'
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
                
                # [S3] 도착 시간 기록
                self.arrive_time = time.time()
                
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
                
                # [S3] 체류 시간 계산 및 발행
                dwell_time = time.time() - self.arrive_time
                stat_msg = f"{self.course[self.idx]['title']} - 체류시간: {dwell_time:.1f}초"
                self.tour_stats.append(stat_msg)
                
                stats_json = String()
                stats_json.data = json.dumps(self.tour_stats, ensure_ascii=False)
                self.pub_stats.publish(stats_json)

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
