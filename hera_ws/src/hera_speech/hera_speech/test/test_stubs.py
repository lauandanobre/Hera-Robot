"""Testes com módulos simulados (faster_whisper, rclpy, hera_msgs).

Servem para validar a lógica sem GPU nem ROS. Se o ROS 2 de verdade estiver
instalado, os testes do nó são pulados (use o robô para testar de verdade).
"""
import importlib
import sys
import types
import unittest
from types import SimpleNamespace

import numpy as np

AUDIO = (np.random.default_rng(0).normal(0, 0.05, 16000)).astype(np.float32)


# ---------------------------------------------------------------- faster_whisper
def install_fake_faster_whisper(fail_cuda=False, segments=None):
    calls = []

    class FakeModel:
        def __init__(self, size, device='cpu', compute_type='int8', **kw):
            calls.append((device, compute_type))
            if fail_cuda and device == 'cuda':
                raise RuntimeError('CUDA out of memory')

        def transcribe(self, audio, **kw):
            self.kw = kw
            segs = segments if segments is not None else [
                SimpleNamespace(text=' vá para a cozinha ', no_speech_prob=0.01,
                                avg_logprob=-0.2)]
            return iter(segs), SimpleNamespace(language=kw.get('language') or 'pt',
                                               language_probability=1.0)

        def detect_language(self, audio):
            return 'en', 0.9, [('en', 0.9), ('pt', 0.05)]

    mod = types.ModuleType('faster_whisper')
    mod.WhisperModel = FakeModel
    sys.modules['faster_whisper'] = mod
    return calls


class TranscriberTests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop('faster_whisper', None)

    def test_fallback_cuda_to_cpu(self):
        calls = install_fake_faster_whisper(fail_cuda=True)
        from hera_ws.src.hera_speech.hera_speech.transcriber import Transcriber, TranscriberConfig
        tr = Transcriber(TranscriberConfig(device='cuda', warmup=False))
        self.assertEqual((tr.device, tr.compute_type), ('cpu', 'int8'))
        self.assertEqual(calls[0], ('cuda', 'int8_float16'))   # tentou o melhor primeiro
        res = tr.transcribe(AUDIO)
        self.assertEqual(res.text, 'vá para a cozinha')
        self.assertEqual(res.language, 'pt')
        self.assertFalse(tr.model.kw['condition_on_previous_text'])
        self.assertTrue(tr.model.kw['vad_filter'])

    def test_hallucination_filtered(self):
        install_fake_faster_whisper(segments=[SimpleNamespace(
            text=' Obrigado por assistir! ', no_speech_prob=0.2, avg_logprob=-0.3)])
        from hera_ws.src.hera_speech.hera_speech.transcriber import Transcriber, TranscriberConfig
        tr = Transcriber(TranscriberConfig(device='cpu', warmup=False))
        res = tr.transcribe(AUDIO)
        self.assertEqual(res.text, '')
        self.assertEqual(res.dropped, 1)

    def test_no_speech_segment_dropped(self):
        install_fake_faster_whisper(segments=[
            SimpleNamespace(text=' ruído ', no_speech_prob=0.9, avg_logprob=-1.5),
            SimpleNamespace(text=' avance ', no_speech_prob=0.05, avg_logprob=-0.2)])
        from hera_ws.src.hera_speech.hera_speech.transcriber import Transcriber, TranscriberConfig
        res = Transcriber(TranscriberConfig(device='cpu', warmup=False)).transcribe(AUDIO)
        self.assertEqual(res.text, 'avance')
        self.assertEqual(res.dropped, 1)

    def test_language_list_picks_best(self):
        install_fake_faster_whisper()
        from hera_ws.src.hera_speech.hera_speech.transcriber import Transcriber, TranscriberConfig
        tr = Transcriber(TranscriberConfig(device='cpu', language='pt,en', warmup=False))
        self.assertEqual(tr.transcribe(AUDIO).language, 'en')

    def test_load_failure_raises_clear_error(self):
        mod = types.ModuleType('faster_whisper')

        class Broken:
            def __init__(self, *a, **k):
                raise OSError('sem rede')
        mod.WhisperModel = Broken
        sys.modules['faster_whisper'] = mod
        from hera_ws.src.hera_speech.hera_speech.transcriber import Transcriber, TranscriberConfig
        with self.assertRaises(RuntimeError) as ctx:
            Transcriber(TranscriberConfig(device='cpu', local_files_only=True))
        self.assertIn('local_files_only', str(ctx.exception))


# ---------------------------------------------------------------- nó ROS (simulado)
def _real_rclpy():
    try:
        import rclpy  # noqa: F401
        return not getattr(sys.modules['rclpy'], '_is_stub', False)
    except ImportError:
        return False


def install_fake_ros(with_hera_msgs):
    for name in list(sys.modules):
        if name.startswith(('rclpy', 'rcl_interfaces', 'std_srvs', 'std_msgs', 'hera_msgs',
                            'hera_speech.hear_v2')):
            sys.modules.pop(name)

    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        sys.modules[name] = m
        return m

    class Logger:
        def __init__(self):
            self.lines = []

        def info(self, m): self.lines.append(('info', m))
        def warn(self, m): self.lines.append(('warn', m))
        def error(self, m): self.lines.append(('error', m))

    class Client:
        def __init__(self, ready=False):
            self.ready, self.sent = ready, []

        def service_is_ready(self): return self.ready
        def call_async(self, req): self.sent.append(req)

    class Pub:
        def __init__(self): self.sent = []
        def publish(self, msg): self.sent.append(msg)

    class Node:
        overrides = {}

        def __init__(self, name):
            self.logger, self.services, self.clients = Logger(), {}, {}
            self.pubs = {}

        def get_logger(self): return self.logger

        def declare_parameter(self, name, default, descriptor=None):
            return SimpleNamespace(value=self.overrides.get(name, default))

        def create_service(self, t, name, cb, callback_group=None):
            self.services[name] = (t, cb)

        def create_client(self, t, name, callback_group=None):
            self.clients[name] = Client()
            return self.clients[name]

        def create_publisher(self, t, topic, depth):
            self.pubs[topic] = Pub()
            return self.pubs[topic]

        def destroy_node(self): pass

    mod('rclpy', ok=lambda: True, init=lambda args=None: None, shutdown=lambda: None,
        _is_stub=True)
    mod('rclpy.node', Node=Node)
    mod('rclpy.callback_groups', ReentrantCallbackGroup=type('G', (), {}))
    mod('rclpy.executors', MultiThreadedExecutor=type('E', (), {}))
    mod('rcl_interfaces')
    mod('rcl_interfaces.msg', ParameterDescriptor=lambda **kw: SimpleNamespace(**kw))
    mod('std_msgs')
    mod('std_msgs.msg', String=lambda data='': SimpleNamespace(data=data))
    mod('std_srvs')
    trig = type('Trigger', (), {
        'Request': type('Req', (), {}),
        'Response': type('Resp', (), {'__init__': lambda s: setattr(s, 'success', False)
                                      or setattr(s, 'message', '')})})
    mod('std_srvs.srv', Trigger=trig)
    if with_hera_msgs:
        hear = type('Hear', (), {
            'Request': type('Req', (), {}),
            'Response': type('Resp', (), {'__init__': lambda s: setattr(s, 'text', '')})})
        beep = type('Beep', (), {'Request': type('BReq', (), {}), 'Response': type('BR', (), {})})
        mod('hera_msgs')
        mod('hera_msgs.srv', Hear=hear, Beep=beep)
    return Node


class FakeMic:
    def __init__(self, *a, **k): self.tones, self.closed = [], False
    chunk = 1600
    def start(self): pass
    def stop(self): pass
    def close(self): self.closed = True
    def reopen(self): pass
    def play_tone(self, f, ms): self.tones.append((f, ms))
    def read(self, n): return b'\0' * (n * 2)


class FakeTranscriber:
    def __init__(self, *a, **k): self.text = 'vá para a cozinha'
    def transcribe(self, audio):
        from hera_ws.src.hera_speech.hera_speech.transcriber import TranscriptionResult
        return TranscriptionResult(text=self.text, language='pt', audio_s=1.0, seconds=0.2)


class FakeRecorder:
    def __init__(self, audio=AUDIO): self.audio, self.chunk = audio, 1600
    def record(self, read, should_stop=None):
        from hera_ws.src.hera_speech.hera_speech.recorder import RecordResult
        if self.audio is None:
            return RecordResult(None, 'no_speech')
        return RecordResult(self.audio, 'speech', duration_s=1.0, speech_s=0.8)


@unittest.skipIf(_real_rclpy(), 'ROS 2 real instalado: teste o nó no robô')
class NodeTests(unittest.TestCase):
    def build(self, with_hera_msgs, **overrides):
        Node = install_fake_ros(with_hera_msgs)
        Node.overrides = overrides
        install_fake_faster_whisper()
        hv2 = importlib.import_module('hera_speech.hear_v2')
        hv2.Microphone, hv2.Transcriber = FakeMic, FakeTranscriber
        node = hv2.HearNode()
        node.recorder = FakeRecorder()
        return hv2, node

    def tearDown(self):
        sys.modules.pop('faster_whisper', None)

    def test_without_hera_msgs_uses_trigger_and_never_blocks(self):
        hv2, node = self.build(False, beep_duration_ms=10)
        self.assertFalse(node.hera_mode)
        srv_type, cb = node.services['hear']
        resp = cb(srv_type.Request(), srv_type.Response())
        self.assertTrue(resp.success)
        self.assertEqual(resp.message, 'vá para a cozinha')
        self.assertEqual(node.mic.tones, [(700, 10)])           # bipe local
        self.assertEqual(node.pubs['transcription'].sent[0].data, 'vá para a cozinha')

    def test_with_hera_msgs_uses_hear_text(self):
        hv2, node = self.build(True)
        self.assertTrue(node.hera_mode)
        srv_type, cb = node.services['hear']
        resp = cb(srv_type.Request(), srv_type.Response())
        self.assertEqual(resp.text, 'vá para a cozinha')
        self.assertIn('beep', node.clients)

    def test_beep_service_used_when_ready(self):
        hv2, node = self.build(True, beep_duration_ms=10)
        node.clients['beep'].ready = True
        srv_type, cb = node.services['hear']
        cb(srv_type.Request(), srv_type.Response())
        sent = node.clients['beep'].sent[0]
        self.assertEqual((sent.frequency, sent.duration), (700, 10))
        self.assertEqual(node.mic.tones, [])                    # não tocou local

    def test_service_type_trigger_forced(self):
        hv2, node = self.build(True, service_type='trigger')
        self.assertFalse(node.hera_mode)

    def test_no_speech_reports_message(self):
        hv2, node = self.build(False, beep=False)
        node.recorder = FakeRecorder(audio=None)
        srv_type, cb = node.services['hear']
        resp = cb(srv_type.Request(), srv_type.Response())
        self.assertFalse(resp.success)
        self.assertIn('ninguém falou', resp.message)

    def test_empty_transcription_is_failure(self):
        hv2, node = self.build(False, beep=False)
        node.transcriber.text = ''
        srv_type, cb = node.services['hear']
        resp = cb(srv_type.Request(), srv_type.Response())
        self.assertFalse(resp.success)

    def test_float_param_given_as_int(self):
        hv2, node = self.build(False, silence_end_s=2, beep=False)   # "-p silence_end_s:=2"
        self.assertEqual(node.p['silence_end_s'], 2.0)
        self.assertIsInstance(node.p['silence_end_s'], float)

    def test_text_mode_match(self):
        hv2, node = self.build(False, text_mode='match', beep=False)
        node.transcriber.text = 'Vá para a Cozinha!'
        srv_type, cb = node.services['hear']
        resp = cb(srv_type.Request(), srv_type.Response())
        self.assertEqual(resp.message, 'va para a cozinha')

    def test_busy_lock(self):
        hv2, node = self.build(False, beep=False)
        node._lock.acquire()
        srv_type, cb = node.services['hear']
        resp = cb(srv_type.Request(), srv_type.Response())
        self.assertFalse(resp.success)
        self.assertIn('ocupado', resp.message)


if __name__ == '__main__':
    unittest.main()
