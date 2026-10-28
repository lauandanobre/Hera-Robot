"""
esse arquivo implementa um micro gravador de fala com detecção de voz,
ele captura áudio do microfone em blocos curtos e decide quando
a pessoa começou a falar, quando está falando e quando parou.

Diferenças em relação ao laço antigo do hear_node:
  * blocos de 100 ms (antes 512 ms), então o fim da fala é detectado mais rápido;
  * o "silêncio para encerrar" só conta depois que a pessoa começou a falar;
  * o limiar de voz se adapta ao ruído do ambiente (calibração + ajuste lento);
  * se ninguém falar, devolve None e o Whisper nem é chamado;
  * corta o silêncio do começo/fim (mantendo uma folga), o que reduz
    alucinações do Whisper.
"""

from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np


@dataclass
class RecorderConfig:
    sample_rate: int = 16000
    chunk_ms: int = 100
    calibration_s: float = 0.4       # mede o ruído de fundo ao começar
    max_wait_speech_s: float = 8.0   # quanto esperar alguém começar a falar
    max_record_s: float = 20.0       # duração máxima da fala
    silence_end_s: float = 1.0       # silêncio que encerra a fala
    onset_s: float = 0.2             # voz contínua necessária p/ "começou"
    pre_roll_s: float = 0.3          # folga mantida antes do início da fala
    tail_pad_s: float = 0.3          # folga mantida depois do fim da fala
    min_speech_s: float = 0.2        # menos que isso conta como ruído (palavras curtas passam)
    on_factor: float = 3.0           # voz começa acima de ruído * on_factor
    off_factor: float = 1.8          # voz continua acima de ruído * off_factor
    min_rms: float = 200.0           # piso absoluto do limiar (RMS int16)
    vad_mode: str = 'energy'         # 'energy' ou 'webrtc' (opcional)
    webrtc_aggressiveness: int = 2   # 0..3


@dataclass
class RecordResult:
    audio: Optional[np.ndarray]      # float32 em [-1, 1], ou None
    reason: str                      # speech | max_duration | no_speech | stopped
    duration_s: float = 0.0          # duração do áudio devolvido
    speech_s: float = 0.0            # tempo com voz detectada
    waited_s: float = 0.0            # tempo total lido do microfone
    noise_floor: float = 0.0
    threshold: float = 0.0


class VoiceDetector:
    """Decide se um bloco tem voz: por energia, ou energia + webrtcvad."""

    def __init__(self, cfg, log=None):
        self.cfg = cfg
        self._webrtc = None
        if cfg.vad_mode == 'webrtc':
            try:
                import webrtcvad
                self._webrtc = webrtcvad.Vad(cfg.webrtc_aggressiveness)
            except Exception as e:  # noqa: BLE001
                if log:
                    log(f'webrtcvad indisponível ({e}); usando VAD por energia')

    def _webrtc_ratio(self, pcm):
        frame_bytes = int(self.cfg.sample_rate * 0.03) * 2   # 30 ms
        n = len(pcm) // frame_bytes
        if n == 0:
            return 0.0
        hits = 0
        for i in range(n):
            frame = pcm[i * frame_bytes:(i + 1) * frame_bytes]
            try:
                hits += bool(self._webrtc.is_speech(frame, self.cfg.sample_rate))
            except Exception:  # noqa: BLE001
                return 0.0
        return hits / n

    def is_voice(self, pcm, rms, threshold):
        if self._webrtc is None:
            return rms > threshold
        return rms > self.cfg.min_rms * 0.6 and self._webrtc_ratio(pcm) >= 0.5


class UtteranceRecorder:
    #Grava uma fala a partir de uma função `read(n_amostras) -> bytes`.

    def __init__(self, cfg=None, log=None):
        self.cfg = cfg or RecorderConfig()
        self.detector = VoiceDetector(self.cfg, log)
        self.chunk = int(self.cfg.sample_rate * self.cfg.chunk_ms / 1000)

    @staticmethod
    def rms(pcm):
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(x * x))) if x.size else 0.0

    def record(self, read: Callable[[int], bytes],
               should_stop: Optional[Callable[[], bool]] = None) -> RecordResult:
        cfg = self.cfg
        stop = should_stop or (lambda: False)
        chunk_s = self.chunk / cfg.sample_rate

        def n(sec):
            return max(1, int(round(sec / chunk_s)))

        calib_n, wait_n = n(cfg.calibration_s), n(cfg.max_wait_speech_s)
        max_n = n(cfg.max_record_s)
        sil_n, tail_n, onset_n = n(cfg.silence_end_s), n(cfg.tail_pad_s), n(cfg.onset_s)
        pre_n, min_speech_n = n(cfg.pre_roll_s), n(cfg.min_speech_s)

        pre = deque(maxlen=pre_n)
        total = 0
        calib = []
        for _ in range(calib_n):
            if stop():
                return RecordResult(None, 'stopped', waited_s=total * chunk_s)
            d = read(self.chunk)
            total += 1
            calib.append(self.rms(d))
            pre.append(d)
        floor = float(np.median(calib))

        frames = None          # lista de blocos da fala (None = ainda esperando)
        onset = []
        speech_chunks = quiet_run = start_total = 0
        reason = 'no_speech'
        thr_on = max(cfg.min_rms, floor * cfg.on_factor)

        while True:
            if stop():
                reason = 'stopped'
                break
            if frames is None and total - calib_n >= wait_n:
                reason = 'no_speech'
                break
            if frames is not None and total - start_total >= max_n:
                reason = 'max_duration'
                break

            d = read(self.chunk)
            total += 1
            r = self.rms(d)
            thr_on = max(cfg.min_rms, floor * cfg.on_factor)
            thr_off = max(cfg.min_rms * 0.6, floor * cfg.off_factor)

            if frames is None:
                if self.detector.is_voice(d, r, thr_on):
                    onset.append(d)
                else:
                    if onset:                       # falso alarme (estalo, porta)
                        pre.extend(onset)
                        onset = []
                    pre.append(d)
                    floor = 0.9 * floor + 0.1 * r   # ruído de fundo se adapta
                if len(onset) >= onset_n:
                    frames = list(pre) + onset
                    speech_chunks, onset = len(onset), []
                    quiet_run, start_total = 0, total
            else:
                frames.append(d)
                if self.detector.is_voice(d, r, thr_off):
                    speech_chunks += 1
                    quiet_run = 0
                else:
                    quiet_run += 1
                    if quiet_run >= sil_n:
                        if speech_chunks >= min_speech_n:
                            reason = 'speech'
                            break
                        # foi só um ruído curto: volta a esperar
                        pre.clear()
                        pre.extend(frames[-pre_n:])
                        frames, speech_chunks, quiet_run = None, 0, 0

        info = dict(waited_s=total * chunk_s, noise_floor=floor, threshold=thr_on)
        if frames is None or reason == 'stopped':
            return RecordResult(None, reason, **info)

        if reason == 'speech':
            drop = max(0, quiet_run - tail_n)
            if drop:
                frames = frames[:-drop]
        pcm = np.frombuffer(b''.join(frames), dtype=np.int16)
        audio = pcm.astype(np.float32) / 32768.0
        return RecordResult(audio, reason, duration_s=len(audio) / cfg.sample_rate,
                            speech_s=speech_chunks * chunk_s, **info)
