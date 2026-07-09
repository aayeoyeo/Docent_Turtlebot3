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
