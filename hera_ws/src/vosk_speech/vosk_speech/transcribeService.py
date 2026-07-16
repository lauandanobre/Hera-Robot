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
        
        # cpu ou cuda
        self.declare_parameter('use_cuda', False)
        use_cuda = self.get_parameter('use_cuda').get_parameter_value().bool_value
        
        # Captura o caminho absoluto a partir do momento que esse script é executado e a partir dai encontra a pasta build para apontar para o verdadeiro caminho do modelo dentro do src
        path = os.path.dirname(os.path.abspath(__file__))

        workspace = path.split('/build/')[0]

        model_path = os.path.join(
            workspace, 
            "src", 
            "vosk_speech", 
            "model", 
            "vosk-model-pt-fb-v0.1.1-20220516_2113" # nome do modelo vosk que esta dentro da pasta model
        )
        
        print("------------------------------------")
        print("Caminho do modelo Vosk: ")
        print(f"{model_path}")
        print("------------------------------------")

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Modelo nao encontrado no share do ROS 2. Verifique o seu setup.py: {model_path}")

        
        self.get_logger().info(f"Carregando o modelo grande do Vosk (CUDA={use_cuda})... Por favor, tenha paciência...")
        
        # 3. Inicialização do modelo aplicando a flag de hardware se CUDA for True
        if use_cuda:
            # Configura o Vosk/Kaldi para usar o dispositivo GPU 0
            self.model = Model(model_path, "cuda:0")
        else:
            self.model = Model(model_path)
        
        self.p = pyaudio.PyAudio()
        
        # Criando um service do tipo trigger
        self.srv = self.create_service(Trigger, 'transcrever_fala', self.transcrever_callback)
        self.get_logger().info("Serviço de transcrição pronto e aguardando chamadas.")

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
            
            # Para o audio
            stream.stop_stream()
            stream.close()
            stream = None
            
            # Uma forma de processar o buffer mais pesado do modelo
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
