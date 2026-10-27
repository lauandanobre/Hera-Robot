"""
Entrada e saída de áudio com PyAudio (importado só quando necessário).
esse nó é usado pelo hear_v2, mas pode ser usado por outros nós caso precise
de capturar audio do microfone ou salvar/ler arquivos .wav
ele tem funções para listar os dispositivos de entrada disponiveis no robô,
e também tem algumas funcoes para escrever arquivos .wav
"""

import wave

import numpy as np


def list_input_devices():
    # lista os dispositivos de entrada de áudio disponíveis, devolve uma lista de tuplas
    # nesse formato: (index, name, max_input_channels,defaultSampleRate)
    import pyaudio
    pa = pyaudio.PyAudio()
    try:
        devices = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get('maxInputChannels', 0) > 0:
                devices.append((i, info['name'], int(info['maxInputChannels']),
                                int(info['defaultSampleRate'])))
        return devices
    finally:
        pa.terminate()


def write_wav(path, audio, sample_rate=16000): # escreve um arquivo .wav
    #.wav, áudio float32 [-1, 1] como WAV 16 bits mono.
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())


def read_wav(path, sample_rate=16000):
    #Lê um áudio qualquer como float32 mono 16 kHz.
    #Usa o decodificador do faster-whisper (qualquer formato) e, se ele não
    #estiver instalado, cai para o módulo wave (só WAV 16 bits mono 16 kHz).
    try:
        from faster_whisper.audio import decode_audio
        return decode_audio(str(path), sampling_rate=sample_rate)
    except ImportError:
        pass
    with wave.open(str(path), 'rb') as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (sample_rate, 1, 2):
            raise ValueError(
                f'{path}: use WAV 16 kHz mono 16 bits. Converta com: '
                f'ffmpeg -i entrada.ext -ar 16000 -ac 1 saida.wav')
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0


class Microphone:
    #Microfone mono 16 kHz. `read(n)` devolve n amostras int16 em bytes.

    def __init__(self, sample_rate=16000, chunk=1600, device_index=None, log=None):
        self.sample_rate = sample_rate
        self.chunk = chunk
        self.device_index = device_index if (device_index or 0) >= 0 else None
        self.log = log or (lambda msg: None)
        self._pa = None
        self._stream = None

    def open(self): #  abre o microfone, não inicia a captura do audio
        import pyaudio
        if self._pa is None:
            self._pa = pyaudio.PyAudio()
        kwargs = dict(format=pyaudio.paInt16, channels=1, rate=self.sample_rate,
                      input=True, frames_per_buffer=self.chunk, start=False)
        if self.device_index is not None:
            kwargs['input_device_index'] = self.device_index
        self._stream = self._pa.open(**kwargs)

    def start(self): # inicia a captura do audio, se o microfone não estiver aberto, ele abre sem problemas
        if self._stream is None:
            self.open()
        if not self._stream.is_active():
            self._stream.start_stream()

    def read(self, n): # lê as amostras do microfone, devolve em byter
        return self._stream.read(n, exception_on_overflow=False)

    def stop(self): # para a captura de audio, mas não fecha o microfone
        try:
            if self._stream is not None and self._stream.is_active():
                self._stream.stop_stream()
        except Exception:  # noqa: BLE001
            pass

    def reopen(self):
        # Recria o stream (útil se o microfone USB foi desconectado).
        try:
            if self._stream is not None:
                self._stream.close()
        except Exception:  # noqa: BLE001
            pass
        self._stream = None
        self.open()

    def play_tone(self, freq=700, ms=300, volume=0.4):
        # toca um bipe no microfone
        import pyaudio
        if self._pa is None:
            self._pa = pyaudio.PyAudio()
        rate = 44100
        t = np.arange(int(rate * ms / 1000.0)) / rate
        wave_i16 = (np.sin(2 * np.pi * freq * t) * volume * 32767).astype(np.int16)
        out = self._pa.open(format=pyaudio.paInt16, channels=1, rate=rate, output=True)
        try:
            out.write(wave_i16.tobytes())
        finally:
            out.stop_stream()
            out.close()

    def close(self): # fecha o microfone, liberando os recursos do pyaudio
        self.stop()
        try:
            if self._stream is not None:
                self._stream.close()
            if self._pa is not None:
                self._pa.terminate()
        except Exception:  # noqa: BLE001
            pass
        self._stream = None
        self._pa = None
