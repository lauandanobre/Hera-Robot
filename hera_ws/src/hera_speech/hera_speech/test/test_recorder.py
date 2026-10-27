"""Testes do gravador (VAD) com áudio sintético. Rodam sem ROS/GPU/microfone."""
import unittest

import numpy as np

from hera_ws.src.hera_speech.hera_speech.recorder import RecorderConfig, UtteranceRecorder

SR = 16000


def synth(segments, seed=0):
    """segments: lista de (segundos, nível). Nível >= 1000 = voz; abaixo = ruído."""
    rng = np.random.default_rng(seed)
    parts = []
    for sec, level in segments:
        n = int(SR * sec)
        t = np.arange(n) / SR
        if level >= 1000:
            x = level * 0.7 * (np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 440 * t))
            x = x + rng.normal(0, 40, n)
        else:
            x = rng.normal(0, level, n)
        parts.append(x)
    return np.concatenate(parts).clip(-32768, 32767).astype(np.int16).tobytes()


class FakeStream:
    def __init__(self, data, fill_level=30):
        self.data, self.pos, self.reads = data, 0, 0
        self.fill = np.random.default_rng(1).normal(0, fill_level, SR * 60)

    def read(self, n):
        self.reads += 1
        chunk = self.data[self.pos * 2:(self.pos + n) * 2]
        self.pos += n
        if len(chunk) < n * 2:                # acabou: continua com ruído baixo
            pad = self.fill[:n - len(chunk) // 2].astype(np.int16).tobytes()
            chunk += pad
        return chunk


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.rec = UtteranceRecorder(RecorderConfig())

    def test_detects_speech_and_stops_fast(self):
        s = FakeStream(synth([(1.2, 30), (1.0, 3000), (3.0, 30)]))
        r = self.rec.record(s.read)
        self.assertEqual(r.reason, 'speech')
        self.assertIsNotNone(r.audio)
        # silêncio cortado: ≈ pre-roll 0,3 + fala 1,0 + folga 0,3
        self.assertAlmostEqual(r.duration_s, 1.6, delta=0.25)
        # o laço antigo só encerrava depois de ~10 s; aqui ≈ 3,6 s
        self.assertLess(r.waited_s, 4.0)
        self.assertEqual(r.audio.dtype, np.float32)
        self.assertLessEqual(float(np.abs(r.audio).max()), 1.0)

    def test_no_speech_returns_none(self):
        s = FakeStream(synth([(6.0, 30)]))
        r = UtteranceRecorder(RecorderConfig(max_wait_speech_s=2.0)).record(s.read)
        self.assertEqual(r.reason, 'no_speech')
        self.assertIsNone(r.audio)

    def test_click_is_ignored(self):
        s = FakeStream(synth([(1.0, 30), (0.1, 6000), (5.0, 30)]))
        r = UtteranceRecorder(RecorderConfig(max_wait_speech_s=3.0)).record(s.read)
        self.assertEqual(r.reason, 'no_speech')

    def test_short_word_is_still_detected(self):
        # uma palavra curta como "sim"/"não" (~0,3 s) precisa ser captada
        s = FakeStream(synth([(1.0, 30), (0.3, 4000), (3.0, 30)]))
        r = self.rec.record(s.read)
        self.assertEqual(r.reason, 'speech')
        self.assertIsNotNone(r.audio)

    def test_noisy_room_speech_detected(self):
        s = FakeStream(synth([(1.5, 800), (1.2, 5000), (3.0, 800)]))
        r = self.rec.record(s.read)
        self.assertEqual(r.reason, 'speech')
        self.assertGreater(r.threshold, 2000)   # limiar subiu junto com o ruído

    def test_noise_only_is_not_speech(self):
        s = FakeStream(synth([(6.0, 800)]))
        r = UtteranceRecorder(RecorderConfig(max_wait_speech_s=3.0)).record(s.read)
        self.assertEqual(r.reason, 'no_speech')

    def test_max_duration(self):
        s = FakeStream(synth([(0.6, 30), (10.0, 3000)]))
        r = UtteranceRecorder(RecorderConfig(max_record_s=2.0)).record(s.read)
        self.assertEqual(r.reason, 'max_duration')
        self.assertIsNotNone(r.audio)

    def test_should_stop(self):
        s = FakeStream(synth([(5.0, 30)]))
        r = self.rec.record(s.read, should_stop=lambda: s.reads >= 3)
        self.assertEqual(r.reason, 'stopped')
        self.assertIsNone(r.audio)


if __name__ == '__main__':
    unittest.main()
