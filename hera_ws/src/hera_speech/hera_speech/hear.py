import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
import os
import pyaudio
import time 
import sys 
import numpy as np
from faster_whisper import WhisperModel
from ament_index_python.packages import get_package_share_directory

LANG = "en"

class TranscreverService(Node):
    def __init__(self):
        super().__init__("hear") 
        
        # O faster-whisper baixa automaticamente ou luma pasta local.
        model_path = "medium" # Exemplo com modelo grande local ou string ("large-v3", "medium", "small")
        
        self.get_logger().info("Carregando o modelo do Faster-Whisper... Por favor, tenha paciência...")
        
        # Escolha "cuda" se tiver GPU Nvidia ou "cpu" para rodar no processador.
        # float16 é ideal para GPU. Para CPU use "int8".
        self.model = WhisperModel(model_path, device="cpu", compute_type="int8")
        
        self.p = pyaudio.PyAudio()
        
        self.srv = self.create_service(Trigger, 'hear', self.transcrever_callback)
        self.get_logger().info("Serviço de transcrição pronto e pronto para chamadas.")

    def transcrever_callback(self, request, response):
        #print(request);
        #print("-------------------------------------------")
        stream = None
        try:
            self.get_logger().info("Ouvindo para o serviço...")
            
            # configurações do microfone
            stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=8192
            )

            stream.start_stream()
            audio_frames = []
            noise_background = 500 # nível minimo de ruido de fundo para começar a gravar o aúdio
            init_time = time.time()
            timeout = 15
            silence_threshold = 2.0 # Tempo sem áudio significativo para encerrar a gravação
            last_voice_time = time.time()
            
            while rclpy.ok():
                current_time = time.time()
                
                if (current_time - init_time) > timeout:  # tempo limite para esperar algúem falar
                    #self.get_logger().warn("Ninguém falou nada dentro do tempo limite.")
                    break
                
                data = stream.read(8192, exception_on_overflow=False)# Leitura do buffer do microfone
                audio_frames.append(data)
                
                # Converte para verificar se há som (VAD simples baseado em amplitude)
                audio_data = np.frombuffer(data, dtype=np.int16)
                amplitude = np.abs(audio_data).mean()
                
                if amplitude > noise_background: # uma verificação para saber se há um som significativo no ambiente, acima do ruido de fundo
                    last_voice_time = current_time
                
                # Se esta gravando há mais de 20 frames e não houver um som significativo por mais de 2 segundos(silence_threshould)
                if len(audio_frames) > 20 and (current_time - last_voice_time) > silence_threshold:
                    self.get_logger().info("Silêncio detectado. Agora vou processar o áudio gravado...")
                    break
            
            # Para e fecha o áudio imediatamente
            stream.stop_stream()
            stream.close()
            stream = None
            
            if not audio_frames:
                raise ValueError("Nenhum dado de áudio foi capturado.")

            # Junta os frames e normaliza para float32, OBS: esse formato é exigido pelo Whisper
            audio_buffer = b"".join(audio_frames)
            audio_np = np.frombuffer(audio_buffer, dtype=np.int16).astype(np.float32) / 32768
            
            self.get_logger().info("Transcrevendo com Faster-Whisper...")
            
            segments, info = self.model.transcribe(audio_np, language=LANG, beam_size=5) # transcreve a gravação em texto e retorna segmentos
            text_transcribe = " ".join([segment.text for segment in segments]) # concatena todos os segmentos gerados
            text_transcribe = text_transcribe.strip() # remoção de espaços indesejaveis
            
            if text_transcribe: # se deu tudo certo
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
