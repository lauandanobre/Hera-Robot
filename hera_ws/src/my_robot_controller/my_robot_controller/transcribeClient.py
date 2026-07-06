import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

class TranscreverClient(Node):
    def __init__(self):
        super().__init__('transcrever_client_node')
        self.cli = self.create_client(Trigger, '/transcrever_fala')
        
        # Espera o servidor ficar online
        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Serviço não disponível, aguardando...')
        
        self.req = Trigger.Request()

    def send_request(self):
        self.get_logger().info('Solicitando transcrição...')
        self.future = self.cli.call_async(self.req)
        rclpy.spin_until_future_complete(self, self.future)
        return self.future.result()

def main(args=None):
    rclpy.init(args=args)
    client = TranscreverClient()
    
    # Exemplo de loop de chamadas
    try:
        while rclpy.ok():
            response = client.send_request()
            if response.success:
                print(f"Sucesso: {response.message}")
            else:
                print(f"Falha: {response.message}")
            
            # Pausa curta entre tentativas
            import time
            time.sleep(1)
            
    except KeyboardInterrupt:
        pass

    client.destroy_node()
    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()
