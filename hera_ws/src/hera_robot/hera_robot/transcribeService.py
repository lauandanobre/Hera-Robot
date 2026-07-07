# esse é um nó de service ROS2 que utiliza o modelo grande do vosk para transcrever fala em português para texto
# nesse codigo foi melhorado em relação ao modelo pequeno o buffer de leitura do mic para 8192
# e recriado o recognizer a cada chamada para não correr o risco de acumular muito lixo de memória do modelo grandde

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
import os
import json
import pyaudio
import time 
import sys 
from vosk import Model, KaldiRecognizer
from ament_index_python.packages import get_package_share_directory

class TranscreverService(Node):
    def __init__(self):
        super().__init__("transcrever_service") 
        
        package_share = get_package_share_directory('hera_robot') # Pacote
        # caminho absoluto por enquanto....
        model_path = "/home/robofei/LN/Ros2/lau_ws/src/hera_robot/model/vosk-model-pt-fb-v0.1.1-20220516_2113"
        
        if not os.path.exists(model_path):
            self.get_logger().error(f"Modelo Vosk não encontrado em: {model_path}")
            raise RuntimeError(f"Modelo Vosk não encontrado em: {model_path}")
        
        self.get_logger().info("Carregando o modelo grande do Vosk... Por favor, tenha paciência...")
        self.model = Model(model_path)
        
        self.p = pyaudio.PyAudio()
        
        # criando um service do tipo trigger
        self.srv = self.create_service(Trigger, 'transcrever_fala', self.transcrever_callback)
        self.get_logger().info("Serviço de transcrição pronto e pronto para chamadas.")

    def transcrever_callback(self, request, response):
        stream = None
        try:
            self.get_logger().info("Ouvindo para o serviço...")
            
            recognizer = KaldiRecognizer(self.model, 16000)
            
            stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=8192
            )

            stream.start_stream()
            text_transcribe = ""
            
            init_time = time.time()
            timeout = 15
            
            while rclpy.ok():
                if (time.time() - init_time) > timeout:
                    self.get_logger().warn("Ninguém falou nada dentro do tempo limite.")
                    break

                # Leitura do buffer aumentado
                data = stream.read(8192, exception_on_overflow=False)
                
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    if 'text' in result and result['text'].strip():
                        text_transcribe = result['text']
                        break 
                else:
                    partial = json.loads(recognizer.PartialResult())
                    if 'partial' in partial and partial['partial']:
                        self.get_logger().debug(f"Parcial: {partial['partial']}")
                        init_time = time.time()
            
            # para o audio
            stream.stop_stream()
            stream.close()
            stream = None
            
            # uma forma de processar o buffer mais pesado do modelo
            final_result = json.loads(recognizer.FinalResult())
            if 'text' in final_result and final_result['text'].strip():
                if text_transcribe:
                    text_transcribe = f"{text_transcribe} {final_result['text']}".strip()
                else:
                    text_transcribe = final_result['text']
            
            if text_transcribe:
                response.success = True
                response.message = text_transcribe
                self.get_logger().info(f"Transcrição enviada: {text_transcribe}")
            else:
                response.success = False
                response.message = "Não consegui reconhecer nada"
                self.get_logger().warn(response.message)
                
        except Exception as e:
            response.success = False
            response.message = f"Erro no processamento: {str(e)}"
            self.get_logger().error(response.message)
            
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
        
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
