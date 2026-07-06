# um service de transcrição de fala para texto usando o modelo Vosk (offline)

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
import os
import json
import pyaudio
from vosk import Model, KaldiRecognizer

class TranscreverService(Node):
    def __init__(self):
        super().__init__("transcrever_service") # nome do nó 
        
        # Caminho do modelo Vosk - usar caminho absoluto
        model_path = "/home/robofei/LN/Ros2/lau_ws/src/hera_robot/model/vosk-model-small-pt-0.3"
        
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
            
            # Abrir stream de áudio
            '''stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=4096
            )
            '''
                        # Abrir stream de áudio apontando direto para o hardware analógico da Intel
            stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=11,
                frames_per_buffer=4096
            )

            stream.start_stream()
            texto_final = ""
            
            while True:
                data = stream.read(4096, exception_on_overflow=False)
                
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    # CORREÇÃO: Pegar o campo 'text' que traz a frase inteira processada
                    if 'text' in result and result['text'].strip():
                        texto_final = result['text']
                        break # Encerra o loop assim que detectar o fim de uma frase estruturada
                else:
                    partial = json.loads(self.recognizer.PartialResult())
                    if 'partial' in partial and partial['partial']:
                        self.get_logger().debug(f"Parcial: {partial['partial']}")
            
            # Garante o fechamento seguro do hardware de áudio
            stream.stop_stream()
            stream.close()
            stream = None
            
            # Fazer reconhecimento final dos dados restantes no buffer do Vosk
            final_result = json.loads(self.recognizer.FinalResult())
            if 'text' in final_result and final_result['text'].strip():
                # Se já pegamos texto no loop, junta. Se não, assume o final.
                if texto_final:
                    texto_final = f"{texto_final} {final_result['text']}".strip()
                else:
                    texto_final = final_result['text']
            
            # Tratamento da resposta para o ROS 2
            if texto_final:
                response.success = True
                response.message = texto_final
                self.get_logger().info(f"Transcrição enviada: {texto_final}")
            else:
                response.success = False
                response.message = "Não consegui reconhecer nada"
                self.get_logger().warn(response.message)
                
        except Exception as e:
            response.success = False
            response.message = f"Erro: {str(e)}"
            self.get_logger().error(response.message)
            
            # Limpeza emergencial do microfone se houver crash
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
    rclpy.init(args=args)
    node = TranscreverService()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.shutdown()

if __name__ == '__main__':
    main()
