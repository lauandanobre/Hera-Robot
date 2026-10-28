#!/usr/bin/env python3
"""
Microfone → audio_io.py → recorder.py → transcriber.py → ROS service/topic


esse é o novo nó de escuta, ele segue esse fluxo: microfone -> faster-whisper -> texto.
ele agora usa VAD para detectar quando a pessoa parou de falar em vez de 10s de silÊncio
e tem um bipe para avisar que começou a escuta. Ele também é capaz de atender a multiplos
services sem travar o microfone, ou seja, se você chamar o hear_v2 enquanto esta processando
ele vai avisar que esta ocupado. Ele também publica o texto no tópico 'transcription' 
(std_msgs/String) para quem quiser ouvir a transcrição sem chamar o serviço.


Funciona com ou sem o pacote `hera_msgs`:
  * COM hera_msgs: o serviço `hear` usa hera_msgs/Hear (response.text), como no
    projeto oficial, e o bipe usa o serviço `beep` (hera_msgs/Beep) se ele existir;
  * SEM hera_msgs: o serviço `hear` vira std_srvs/Trigger (texto em `message`)
    e o bipe é tocado localmente. O nó nunca trava esperando pelo `beep`.
Em qualquer modo o texto também sai no tópico `transcription` (std_msgs/String).

Tudo é configurável por parâmetros ROS (veja DEFAULTS abaixo).
"""

import sys
import threading
import time

import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

from . import perf
from .audio_io import Microphone
from .recorder import RecorderConfig, UtteranceRecorder
from .transcriber import Transcriber, TranscriberConfig, apply_text_mode

# para verificar se existe o std_msgs e beep, se não existir funciona do mesmo jeito, mas sem bipe e com service TRigger
try:                                   
    from hera_msgs.srv import Hear as HearSrv
except Exception:                       # noqa: BLE001
    HearSrv = None
try:
    from hera_msgs.srv import Beep as BeepSrv
except Exception:                       # noqa: BLE001
    BeepSrv = None

# o DEFAULTS abaixo é usado para declarar parâmetros ROS, 
# e também como fallback caso algum parâmetro não seja declarado.
DEFAULTS = {
    # modelo
    'model_size': 'medium', 'device': 'auto', 'compute_type': 'auto',
    'language': 'pt', 'beam_size': 2, 'vad_filter': True, 'initial_prompt': '',
    'local_files_only': False, 'model_dir': '', 'cpu_threads': 0,
    'warmup': True, 'hallucination_filter': True,
    'text_mode': 'raw',                 # raw | lower | match (sem acento/pontuação)
    # microfone / gravação
    'input_device_index': -1, 'max_wait_speech_s': 8.0, 'max_record_s': 20.0,
    'silence_end_s': 1.0, 'min_rms': 200.0, 'vad_mode': 'energy',
    # bipe
    'beep': True, 'beep_freq': 700, 'beep_duration_ms': 300, 'local_beep': True,
    # interface ROS
    'service_name': 'hear', 'service_type': 'auto', 'topic': 'transcription',
}

def _coerce(value, default):
    # essa função converte o valor recebido nos DEFALTS para o tipo do padrão (ex.: 1 -> 1.0).
    # garante a compatibilidade com parâmetros antigos que eu usava como float e agora são qualquer outro
    try:
        if isinstance(default, bool): # se for bool, aceita 1, true, yes...
            if isinstance(value, str):
                return value.strip().lower() in ('1', 'true', 'yes', 'sim', 'on')
            return bool(value)
        if isinstance(default, int):# se for int, aceita 1.0 e converte para int
            return int(value)
        if isinstance(default, float):# se for float, aceita 1 e converte para float
            return float(value)
        return str(value)
    except (TypeError, ValueError): # caso falhe, apenas devolve o padrão
        return default

# Nó de escuta, ele pode atender a multiplos services já que usa MultiThreadedExecutor
# para não travar o microfone enquanto processa a transcrição
class HearNode(Node):
    def __init__(self): # construtor, inicializa o microfone, o service transcriber e bipe
        super().__init__('hear_node')
        log = self.get_logger().info
        self.p = {k: self._declare(k, v) for k, v in DEFAULTS.items()} # declara os parametros lá de cima
        p = self.p

        self.recorder = UtteranceRecorder(RecorderConfig( # inicializa o gravador de fala, que usa VAD para detectar quando a pessoa parou de falar
            max_wait_speech_s=p['max_wait_speech_s'], max_record_s=p['max_record_s'],
            silence_end_s=p['silence_end_s'], min_rms=p['min_rms'],
            vad_mode=p['vad_mode']), log=log)
        self.mic = Microphone(chunk=self.recorder.chunk,
                              device_index=p['input_device_index'], log=log)

        log('Carregando o modelo de fala (pode demorar)...')
        self.transcriber = Transcriber(TranscriberConfig(
            model_size=p['model_size'], device=p['device'], compute_type=p['compute_type'],
            language=p['language'], beam_size=p['beam_size'], vad_filter=p['vad_filter'],
            initial_prompt=p['initial_prompt'], local_files_only=p['local_files_only'],
            download_root=p['model_dir'], cpu_threads=p['cpu_threads'],
            warmup=p['warmup'], hallucination_filter=p['hallucination_filter']), log=log)
        log(f'Memória após carregar: {perf.describe()}')

        self.group = ReentrantCallbackGroup()
        self._lock = threading.Lock()
        self._warned_beep = False
        self.pub = self.create_publisher(String, p['topic'], 10)

        want = p['service_type']
        self.hera_mode = HearSrv is not None and want in ('auto', 'hera')
        if want == 'hera' and HearSrv is None:
            self.get_logger().warn('hera_msgs não encontrado: usando std_srvs/Trigger.')
        srv_type = HearSrv if self.hera_mode else Trigger
        self.srv = self.create_service(srv_type, p['service_name'], self._on_hear,
                                       callback_group=self.group)
        self.beep_client = None
        if p['beep'] and BeepSrv is not None:
            self.beep_client = self.create_client(BeepSrv, 'beep', callback_group=self.group)

        modo = 'hera_msgs/Hear' if self.hera_mode else 'std_srvs/Trigger'
        log(f'Pronto. Serviço "{p["service_name"]}" ({modo}), tópico "{p["topic"]}".')

    # ---------- parâmetros ----------
    def _declare(self, name, default):
        try:                            # aceita "-p x:=1" mesmo para parâmetro float
            desc = ParameterDescriptor(dynamic_typing=True)
            value = self.declare_parameter(name, default, desc).value
        except Exception:               # noqa: BLE001  (Humble antigo sem dynamic_typing)
            value = self.declare_parameter(name, default).value
        return _coerce(value, default)

    # ---------- bipe ----------
    def _beep(self):
        p = self.p
        if not p['beep']:
            return
        if self.beep_client is not None and self.beep_client.service_is_ready():
            req = BeepSrv.Request()
            req.frequency = int(p['beep_freq'])
            req.duration = int(p['beep_duration_ms'])
            self.beep_client.call_async(req)         # não bloqueia
            time.sleep(p['beep_duration_ms'] / 1000.0 + 0.15)   # bipe não vaza no microfone
            return
        if self.beep_client is not None and not self._warned_beep:
            self.get_logger().warn('Serviço "beep" indisponível; usando bipe local.')
            self._warned_beep = True
        if p['local_beep']:
            try:
                self.mic.play_tone(p['beep_freq'], p['beep_duration_ms'])
                time.sleep(0.1)
            except Exception as e:  # noqa: BLE001
                self.get_logger().warn(f'Bipe local falhou ({e}); seguindo sem bipe.')

    # ---------- núcleo ----------
    def _record(self):
        self.mic.start()
        try:
            return self.recorder.record(self.mic.read,
                                        should_stop=lambda: not rclpy.ok())
        finally:
            self.mic.stop()

    def _listen_once(self):# devolve o texto transcrito ou uma mensagem de erro, se 
        # estiver processando outra escuta, devolve mensagem de ocupado
        """Devolve (texto, mensagem). Texto vazio = falha; a mensagem explica."""
        if not self._lock.acquire(blocking=False):
            return '', 'ocupado: já existe uma escuta em andamento'
        log = self.get_logger()
        try:
            self._beep()
            log.info('Ouvindo...')
            try:
                rec = self._record()
            except Exception as e:      # noqa: BLE001  (ex.: microfone USB reconectado)
                log.warn(f'Falha no microfone ({e}); reabrindo...')
                self.mic.reopen()
                rec = self._record()

            if rec.audio is None:
                msg = {'no_speech': 'ninguém falou no tempo limite',
                       'stopped': 'escuta cancelada'}.get(rec.reason, rec.reason)
                log.warn(msg)
                return '', msg

            log.info(f'Áudio: {rec.duration_s:.1f}s (fala {rec.speech_s:.1f}s, '
                     f'ruído≈{rec.noise_floor:.0f}, limiar≈{rec.threshold:.0f}, '
                     f'fim: {rec.reason})')
            res = self.transcriber.transcribe(rec.audio)
            text = apply_text_mode(res.text, self.p['text_mode'])
            log.info(f'Transcrição em {res.seconds:.2f}s (RTF {res.rtf:.2f}, '
                     f'idioma {res.language}): "{text}"')
            if not text:
                return '', 'não reconheci nada'
            self.pub.publish(String(data=text))
            return text, 'ok'
        except Exception as e:          # noqa: BLE001
            msg = f'erro no processamento: {e}'
            log.error(msg)
            return '', msg
        finally:
            self._lock.release()

    def _on_hear(self, request, response): # service ros, ele devolve hera_msgs/Hear ou /Trigger dependendo do que escolheu nos parâmetros
        text, msg = self._listen_once()
        if self.hera_mode:
            response.text = text
        else:
            response.success = bool(text)
            response.message = text if text else msg
        return response

    def destroy_node(self):
        self.get_logger().info('Fechando o microfone...')
        self.mic.close()
        super().destroy_node()


def main(args=None): 
    rclpy.init(args=args)
    node = None
    code = 0
    try:
        node = HearNode()
        executor = MultiThreadedExecutor() # permite atender a multiplos services sem travar o microfone
        executor.add_node(node)
        executor.spin()
    except KeyboardInterrupt:
        pass
    except Exception as e:              # noqa: BLE001, deu erro no nó
        print(f'[hear_v2] erro fatal: {e}', file=sys.stderr)
        code = 1 # o retorno 1 indica que deu erro
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return code


if __name__ == '__main__':# caso queira rodar o nó hear_v2 sem ros2, só para testar mesmo
    sys.exit(main())
