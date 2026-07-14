import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

class TranscreverClient(Node):
    def __init__(self):
        super().__init__('speak')
        self.client = self.create_client(Trigger, 'hear')
        self.get_logger().info('Inicializando cliente de transcrição...')

        if not self.client.wait_for_service(timeout_sec=5.0): # espera até 5 segundos para se conectar com o service
            self.get_logger().error('O serviço "hear" parece não estar disponível. Certifique-se de que o nó do servidor está rodando.')
            raise RuntimeError('Serviço "hear" não encontrado')

    def call_transcribe(self):
        request = Trigger.Request()
        self.get_logger().info('Solicitando transcrição para o client speak...')
        future = self.client.call_async(request)
        rclpy.spin_until_future_complete(self, future)

        if future.result() is not None:
            response = future.result()
            # print(response)
            self.get_logger().info(f'Resposta recebida: success={response.success}, message="{response.message}"')
        else:
            self.get_logger().error('Falha ao chamar o serviço de transcrição.')


def main(args=None):
    rclpy.init(args=args)
    node = None

    try:
        node = TranscreverClient()
        node.get_logger().info('Cliente em loop. Pressione Ctrl+C para sair.')
        while rclpy.ok():
            node.call_transcribe()
    except KeyboardInterrupt:
        if node is not None:
            node.get_logger().info('Cliente interrompido pelo usuário.')
    except Exception as e:
        if node is not None:
            node.get_logger().error(f'Erro no cliente de transcrição: {e}')
        else:
            print(f'Erro no cliente de transcrição: {e}')
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
