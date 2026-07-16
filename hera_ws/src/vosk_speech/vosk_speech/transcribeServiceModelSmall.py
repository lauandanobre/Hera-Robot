# um service de transcrição de fala para texto usando o modelo Vosk (offline)

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
import os
import json
import pyaudio
import time # Adicionado para controlar o tempo limite (timeout)
import sys # Importado para garantir o tratamento correto de argumentos de terminal
from vosk import Model, KaldiRecognizer

class TranscreverService(Node):
    def __init__(self):
        super().__init__("transcrever_service") # nome do nó 
        
        # modelo pequeno
        model_path = "" # caminho absoluto
        
        
        if not os.path.exists(model_path):
            self.get_logger().error(f"Modelo Vosk não encontrado em: {model_path}")
            raise RuntimeError(f"Modelo Vosk não encontrado em: {model_path}")
        
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, 16000)
        
        # Configurar áudio
        self.p = pyaudio.PyAudio()
        
        # service tipo trigger, nome: transcrever_fala, callback
        self.srv = self.create_service(Trigger, 'transcrever_fala', self.transcrever_callback)
        
        self.get_logger().info("Serviço de transcrição com Vosk iniciado. Aguardando alguém falar algo...")

    def transcrever_callback(self, request, response):
        stream = None
        try:
            self.get_logger().info("Ouvindo para o serviço...")
            
            # OBS: Não colocar input_device_index fpara usar o microfone padrão do sistema
            stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=4096
            )

            stream.start_stream()
            text_transcribe = ""
            
            # Configuração de timeout, para o robô não ficar esperando infinitamente se houver silêncio
            init_time = time.time()
            timeout = 15 # 10 segundos
            
            while rclpy.ok():
                # Verifica se estourou o tempo limite de espera por alguém falar algo
                if (time.time() - init_time) > timeout:
                    self.get_logger().warn("Ninguém falou nada dentro do tempo limite. Encerrando...")
                    break

                data = stream.read(4096, exception_on_overflow=False)
                
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    if 'text' in result and result['text'].strip():
                        text_transcribe = result['text']
                        break 
                else:
                    partial = json.loads(self.recognizer.PartialResult())
                    if 'partial' in partial and partial['partial']:
                        self.get_logger().debug(f"Parcial: {partial['partial']}")
                        # Reseta o timer se detectar que o usuário começou a falar algo
                        init_time = time.time()
            
            # uma ganrantia de fechamento seguro do hardware de áudio
            stream.stop_stream()
            stream.close()
            stream = None
            
            # Fazer reconhecimento final dos dados restantes no buffer do Vosk
            final_result = json.loads(self.recognizer.FinalResult())
            if 'text' in final_result and final_result['text'].strip():
                if text_transcribe:
                    text_transcribe = f"{text_transcribe} {final_result['text']}".strip()
                else:
                    text_transcribe = final_result['text']
            
            # Tratamento da resposta para o ROS 2
            if text_transcribe:
                response.success = True
                response.message = text_transcribe
                self.get_logger().info(f"Transcrição enviada: {text_transcribe}")
            else:
                response.success = False
                response.message = "Não consegui reconhecer nada. Talvez ninguém tenha falado ou o áudio estava muito baixo."
                self.get_logger().warn(response.message)
                
        except Exception as e:
            response.success = False
            response.message = f"Erro no hardware de áudio: {str(e)}"
            self.get_logger().error(response.message)
            
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            
            # Reiniciar o recognizer em caso de erro catastrófico
            self.recognizer = KaldiRecognizer(self.model, 16000)
        
        return response

def main(args=None):
    if args is None:
        args = sys.argv
        
    rclpy.init(args=args)
    node = TranscreverService()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.destroy_node()
            rclpy.shutdown()

if __name__ == '__main__':
    main()
