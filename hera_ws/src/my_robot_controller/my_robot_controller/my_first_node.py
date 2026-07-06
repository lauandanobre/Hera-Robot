import rclpy
from rclpy.node import Node

class MyFirstNode(Node):

    def __init__(self) -> None:
        super().__init__("my_first_node")
        self.count = 0 # um simples contador para contar a quanntidade de vezes a mensagem foi mostrda
        self.create_timer(1.0, self.timer_callback) # temporizador de 1 segundo

    def timer_callback(self):
        self.get_logger().info("Hello World!!" + str(self.count))
        self.count += 1

def main(args = None):
    rclpy.init(args=args)
    # nó
    node = MyFirstNode()
    rclpy.spin(node) # manter em execução no terminal
    rclpy.shutdown()


if __name__ == "__main__":
    main()

