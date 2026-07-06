# um service de transcrição de fala para texto usando a biblioteca speech_recognition e pyaudio

import rclpy
from rclpy.node import Node
import speech_recognition as sr
from std_srvs.srv import Trigger # importando o service tipo trigger, já que não preciso de dados de entrada, apenas a fala transcrevida

class TranscreverService(Node):
    def __init__(self):
        super().__init__("transcrever_service")
        
        # service tipo trigger, nome: transcrever_fala, callback
        self.srv = self.create_service(Trigger, 'transcrever_fala', self.transcrever_callback)
        
        self.reconhecedor = sr.Recognizer()
        self.microfone = sr.Microphone()
        
        self.get_logger().info("Serviço de transcrição pronto. Chame o serviço 'transcrever_fala'")

    def transcrever_callback(self, request, response):# roda toda vez que o service é chamado
        with self.microfone as fonte:
            try:
                self.get_logger().info("Ouvindo para o serviço...")
                self.reconhecedor.adjust_for_ambient_noise(fonte, duration=0.5)
                audio = self.reconhecedor.listen(fonte, timeout=2.0) # um tempo limite para ouvir
                
                texto = self.reconhecedor.recognize_google(audio, language="pt-BR")
                
                response.success = True
                response.message = texto
                self.get_logger().info(f"Transcrição enviada: {texto}")
                
            except sr.UnknownValueError:
                response.success = False
                response.message = "Não entendi o que você disse"
                self.get_logger().warn(response.message)
                
            except Exception as e:
                response.success = False
                response.message = f"Erro: {str(e)}"
                self.get_logger().error(response.message)
            
            return response

def main(args=None):
    rclpy.init(args=args)
    node = TranscreverService()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == "__main__":
    main()
