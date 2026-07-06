# um simples nó de transcrição de fala para texto usando a biblioteca speech_recognition e pyaudio
import rclpy
from rclpy.node import Node
import speech_recognition as sr

class Transcrever(Node):
    def __init__(self):
        super().__init__("transcrever")
        self.reconhecedor = sr.Recognizer()
        self.microfone = sr.Microphone()
        
        # inicicar a escuta em um loop
        self.get_logger().info("Nó de transcrição iniciado. Pode falar!")
        self.transcreverFalaEmTexto()

    def transcreverFalaEmTexto(self):
        with self.microfone as fonte:
            # ajustando o reconhecedor para o ruido de fundo
            self.reconhecedor.adjust_for_ambient_noise(fonte) 
            
            while rclpy.ok():
                try:
                    self.get_logger().info("Ouvindo...")
                    audio = self.reconhecedor.listen(fonte)
                    
                    # usar o speech recognition do google para transcrever o audio
                    texto = self.reconhecedor.recognize_google(audio, language="pt-BR")
                    self.get_logger().info(f"Você disse: {texto}")
                    
                except sr.UnknownValueError:
                    self.get_logger().warn("Não entendi o que você disse.")
                except sr.RequestError as e:
                    self.get_logger().error(f"Erro no serviço de transcrição: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = Transcrever()

    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == "__main__":
    main()
