# execute o nó hear_node com o nó speak_node

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from std_srvs.srv import Trigger
from hera_msgs.srv import Beep
import time 
import sys 
import numpy as np
import pyaudio
from faster_whisper import WhisperModel

LANG = "pt"
DELAY_BIP = 0.3 # 0.3 segundos

class TranscreverService(Node):
    def __init__(self):
        super().__init__("hear_node")
        
        model = "medium"
        
        # Grupo reentrante para permitir concorrência interna segura
        self.group = ReentrantCallbackGroup()
        
        self.get_logger().info("Carregando o modelo do Faster-Whisper na GPU...")
        self.model = WhisperModel(model, device="cuda", compute_type="float16")
        
        # Inicializa o PyAudio e deixa o stream aberto em modo passivo
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=8192,
            start=False  
        )
        
        # service de beep
        self.beep_client = self.create_client(Beep, 'beep', callback_group=self.group)
        
        self.srv = self.create_service(Trigger, 'hear_node', self.transcrever_callback, callback_group=self.group)
        self.get_logger().info("Serviço de transcrição assíncrono pronto.")

    def emitir_beep_asincrono(self, freq=700, duration=300):
        # comando de beep sem travar o processamento local
        if not self.beep_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().warn("Serviço de beep indisponível. Continuando sem som.")
            return
            
        req = Beep.Request()
        req.frequency = freq
        req.duration = duration
        
        # call_async para não bloquear a execução deessa thread e abrir o microfone em seguida
        self.beep_client.call_async(req)

    def transcrever_callback(self, request, response):
        try:
            # aciona o bip antes de escutar (Feedback visual/auditivo para o usuário)
            self.emitir_beep_asincrono(freq=700, duration=300)

            time.sleep(DELAY_BIP) # um pequeno delay para o som do bip não vazar no próprio microfone

            self.get_logger().info("Ouvindo o microfone...")
            self.stream.start_stream()
            
            audio_frames = []
            noise_background = 500  # nível minimo de ruido de fundo do ambiente para começar a gravar o aúdio
            init_time = time.time()
            timeout = 60
            silence_threshold = 1.0 # Tempo sem áudio significativo para encerrar a gravação
            last_voice_time = time.time()
            
            while rclpy.ok():
                current_time = time.time()
                
                if (current_time - init_time) > timeout: # tempo limite para esperar algúem falar
                    #self.get_logger().warn("Ninguém falou nada dentro do tempo limite.")
                    break
                
                data = self.stream.read(8192, exception_on_overflow=False)
                audio_frames.append(data)
                
                audio_data = np.frombuffer(data, dtype=np.int16)
                amplitude = np.abs(audio_data).mean()
                
                if amplitude > noise_background:
                    last_voice_time = current_time
                
                # Se esta gravando há mais de 20 frames e não houver um som significativo por mais de 2 segundos(silence_threshould)
                if len(audio_frames) > 20 and (current_time - last_voice_time) > silence_threshold:
                    self.get_logger().info("Silêncio detectado. Agora vou processar o áudio gravado...")
                    break
            
            # encerra a gravação imediatamente
            self.stream.stop_stream()
            
            if not audio_frames:
                raise ValueError("Nenhum dado de áudio foi capturado.")

            # Junta os frames e normaliza para float32, OBS: esse formato é exigido pelo Whisper
            audio_buffer = b"".join(audio_frames)
            audio_np = np.frombuffer(audio_buffer, dtype=np.int16).astype(np.float32) / 32768
            
            segments, info = self.model.transcribe(audio_np, language=LANG, beam_size=5) # transcreve a gravação em texto e retorna segmentos
            text_transcribe = " ".join([segment.text for segment in segments]) # concatena todos os segmentos gerados
            text_transcribe = text_transcribe.strip() # remoção de espaços indesejaveis
            
            if text_transcribe: # se deu tudo certo
                response.success = True
                response.message = text_transcribe
                self.get_logger().info(f"Transcrito com sucesso: {text_transcribe}")
            else:
                response.success = False
                response.message = "Não consegui reconhecer o áudio."
                self.get_logger().warn(response.message)
                
        except Exception as e:
            response.success = False
            response.message = f"Erro no processamento: {str(e)}"
            self.get_logger().error(response.message)
            try:
                self.stream.stop_stream()
            except Exception:
                pass
        
        return response
    
    def destroy_node(self):
        self.get_logger().info("Fechando recursos de hardware...")
        try:
            self.stream.stop_stream()
            self.stream.close()
            self.p.terminate()
        except Exception:
            pass
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = TranscreverService()
    
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
