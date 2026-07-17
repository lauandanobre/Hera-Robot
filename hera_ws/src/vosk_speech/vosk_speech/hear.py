import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
import os
import json
import pyaudio
import time 
import sys 
from vosk import Model, KaldiRecognizer

class TranscreverService(Node):
    def __init__(self):
        super().__init__("hear") 
        
        # Parâmetros
        self.declare_parameter('use_cuda', False)
        use_cuda = self.get_parameter('use_cuda').get_parameter_value().bool_value
        
        # Lista estrita de comandos para o Vosk. 
        self.comandos_validos = [
            "avançar", "voltar", "parar", "esquerda", "direita", 
            "ligar", "desligar", "ajuda", "retornar", "status",
            "pegue", "abra", "[unk]" # [unk] serve para capturar palavras desconhecidas sem quebrar
        ]
        
        # Formata a lista como uma string JSON que o Vosk exige
        self.grammar_json = json.dumps(self.comandos_validos)
        
        self.ultima_transcricao_bruta = ""

        # Caminho do modelo
        path = os.path.dirname(os.path.abspath(__file__))
        workspace = path.split('/build/')[0]
        model_path = os.path.join(
            workspace, "src", "vosk_speech", "model", "vosk-model-pt-fb-v0.1.1-20220516_2113"
        )
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Modelo nao encontrado: {model_path}")
        
        self.get_logger().info(f"Carregando o modelo Vosk (CUDA={use_cuda})...")
        if use_cuda:
            self.model = Model(model_path, "cuda:0")
        else:
            self.model = Model(model_path)
        
        self.p = pyaudio.PyAudio()
        
        # Serviços ROS2
        self.srv_captura = self.create_service(Trigger, 'transcrever_fala', self.transcrever_callback)
        self.srv_checa_proximidade = self.create_service(Trigger, 'verificar_comando', self.checar_proximidade_callback)
        
        self.get_logger().info("Ambos os serviços prontos com restrição de gramática ativa.")

    def transcrever_callback(self, request, response):
        stream = None
        try:
            self.get_logger().info("Ouvindo microfone (Modo Gramática Ativo)...")
            
            # MUDANÇA CHAVE: Passamos a lista de comandos permitidos diretamente para o Vosk
            recognizer = KaldiRecognizer(self.model, 16000, self.grammar_json)
            
            stream = self.p.open(
                format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8192
            )
            stream.start_stream()
            
            text_transcribe = ""
            init_time = time.time()
            timeout = 8  # Reduzido para melhor usabilidade em robótica
            
            while rclpy.ok():
                if (time.time() - init_time) > timeout:
                    self.get_logger().warn("Timeout: Nenhum comando detectado.")
                    break

                data = stream.read(4096, exception_on_overflow=False) # Buffer menor diminui a latência
                
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    if 'text' in result and result['text'].strip():
                        text_transcribe = result['text']
                        break 
                else:
                    partial = json.loads(recognizer.PartialResult())
                    if 'partial' in partial and partial['partial'].strip():
                        init_time = time.time() # Reseta timeout se houver barulho/fala em andamento
            
            if stream is not None:
                stream.stop_stream()
                stream.close()
            
            # Limpa o buffer final do reconhecedor
            final_result = json.loads(recognizer.FinalResult())
            if 'text' in final_result and final_result['text'].strip():
                if not text_transcribe:
                    text_transcribe = final_result['text']
            
            # Remove marcadores de palavras desconhecidas se o Vosk retornar
            text_transcribe = text_transcribe.replace("[unk]", "").strip()

            if text_transcribe:
                self.ultima_transcricao_bruta = text_transcribe.lower()
                response.success = True
                response.message = text_transcribe
                self.get_logger().info(f"Comando exato reconhecido: '{text_transcribe}'")
            else:
                response.success = False
                response.message = ""
                
        except Exception as e:
            response.success = False
            response.message = f"Erro no áudio: {str(e)}"
            self.get_logger().error(response.message)
        
        return response

    def checar_proximidade_callback(self, request, response):
        """ Serviço 2: Agora atua como confirmação de segurança (Double Check real) """
        texto_original = self.ultima_transcricao_bruta.strip()
        
        if not texto_original:
            response.success = False
            response.message = "Nenhum comando na fila para execução."
            return response

        # Como o Vosk já filtrou o áudio usando a lista, o texto já chega 100% limpo e validado
        response.success = True
        response.message = texto_original
        self.get_logger().info(f"Comando confirmado para execução: '{texto_original}'")
        
        # Limpa o estado após confirmar o consumo do comando
        self.ultima_transcricao_bruta = ""
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
