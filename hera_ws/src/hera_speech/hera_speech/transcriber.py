"""
Transcrição com faster-whisper, sem ROS.

O que este módulo faz por você:
utiliza a GPU ou CPU e o tipo de cálculo sozinho (cuda int8_float16 -> float16 
-> int8 -> cpu int8), caso coloque auto o nó não quebra em máquina sem GPU ou sem VRAM;
aceita idioma fixo ('pt'), automático ('auto') ou uma lista ('pt,en');
filtra alucinações típicas do Whisper em silêncio/ruído;
devolve tempo gasto e RTF para você medir a performance.
"""

import gc
import re
import time
import unicodedata
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000

# algumas frases que o faster-whisper "inventa" em silêncio/ruído (comparadas já normalizadas).
HALLUCINATIONS = (
    'obrigado por assistir',
    'obrigada por assistir',
    'legendas pela comunidade amara org',
    'inscreva se no canal',
    'thanks for watching',
    'thank you for watching',
    'subtitles by',
)


@dataclass
class TranscriberConfig:
    model_size: str = 'medium'        # tiny/base/small/medium/large-v3/large-v3-turbo ou pasta
    device: str = 'auto'              # auto | cuda | cpu
    compute_type: str = 'auto'        # auto | int8_float16 | float16 | int8 ...
    language: str = 'pt'              # 'pt', 'en', 'auto' ou 'pt,en'
    beam_size: int = 2
    vad_filter: bool = True           # VAD Silero embutido no faster-whisper
    vad_min_silence_ms: int = 500
    initial_prompt: str = ''          # vocabulário esperado (nomes, comandos)
    local_files_only: bool = False    # True = nunca tenta baixar (robô offline)
    download_root: str = ''
    cpu_threads: int = 0
    no_speech_threshold: float = 0.6
    warmup: bool = True
    hallucination_filter: bool = True


@dataclass
class TranscriptionResult:
    text: str = ''
    language: str = ''
    language_prob: float = 0.0
    audio_s: float = 0.0
    seconds: float = 0.0
    dropped: int = 0                  # segmentos descartados pelo filtro

    @property
    def rtf(self):
        """Real-time factor: segundos de processamento por segundo de áudio."""
        return self.seconds / self.audio_s if self.audio_s > 0 else 0.0


def normalize_for_match(text):
    """minúsculas, sem acento, sem pontuação (bom para comparar/casar texto)."""
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^a-zA-Z0-9]+', ' ', text).lower().strip()


def apply_text_mode(text, mode):
    """raw = como veio | lower = minúsculas | match = sem acento/pontuação."""
    if mode == 'lower':
        return text.lower()
    if mode == 'match':
        return normalize_for_match(text)
    return text


def is_hallucination(text):
    norm = normalize_for_match(text)
    return any(norm == h or norm.startswith(h + ' ') for h in HALLUCINATIONS)


def cuda_available():
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001
        return False


def device_chain(device, compute_type):
    """Lista de (device, compute_type) para tentar, do melhor ao último recurso."""
    dev = device
    if device == 'auto':
        dev = 'cuda' if cuda_available() else 'cpu'
    if compute_type != 'auto':
        chain = [(dev, compute_type)]
    elif dev == 'cuda':
        chain = [('cuda', 'int8_float16'), ('cuda', 'float16'), ('cuda', 'int8')]
    else:
        chain = [('cpu', 'int8')]
    if dev == 'cuda':
        chain.append(('cpu', 'int8'))
    return chain


def parse_languages(value):
    value = (value or '').strip().lower()
    if value in ('', 'auto'):
        return []
    return [v.strip() for v in value.split(',') if v.strip()]


class Transcriber:
    def __init__(self, cfg=None, log=None):
        self.cfg = cfg or TranscriberConfig()
        self.log = log or (lambda msg: None)
        self.languages = parse_languages(self.cfg.language)
        self.model = None
        self.device = None
        self.compute_type = None
        self._load()
        if self.cfg.warmup:
            self.warmup()

    def _load(self):
        from faster_whisper import WhisperModel
        cfg = self.cfg
        last_error = None
        for dev, comp in device_chain(cfg.device, cfg.compute_type):
            kwargs = dict(device=dev, compute_type=comp,
                          local_files_only=cfg.local_files_only)
            if cfg.download_root:
                kwargs['download_root'] = cfg.download_root
            if cfg.cpu_threads:
                kwargs['cpu_threads'] = cfg.cpu_threads
            try:
                self.log(f'Carregando "{cfg.model_size}" em {dev}/{comp}...')
                self.model = WhisperModel(cfg.model_size, **kwargs)
                self.device, self.compute_type = dev, comp
                self.log(f'Modelo pronto em {dev}/{comp}.')
                return
            except Exception as e:  # noqa: BLE001
                last_error = e
                self.log(f'Falhou em {dev}/{comp}: {e}')
                self.model = None
                gc.collect()
        hint = ' (com local_files_only=True o modelo precisa já estar baixado)' \
            if cfg.local_files_only else ''
        raise RuntimeError(f'Não foi possível carregar o modelo{hint}: {last_error}')

    def warmup(self):
        """Primeira inferência é lenta (inicializa kernels); faz isso no boot."""
        t0 = time.perf_counter()
        try:
            lang = self.languages[0] if self.languages else 'pt'
            segments, _ = self.model.transcribe(
                np.zeros(SAMPLE_RATE, dtype=np.float32), language=lang,
                beam_size=1, vad_filter=False, without_timestamps=True)
            for _ in segments:
                pass
            self.log(f'Aquecimento concluído em {time.perf_counter() - t0:.2f}s.')
        except Exception as e:  # noqa: BLE001
            self.log(f'Aquecimento ignorado: {e}')

    def _pick_language(self, audio):
        if not self.languages:
            return None                        # deixa o Whisper detectar
        if len(self.languages) == 1:
            return self.languages[0]
        try:                                   # lista: escolhe só entre as permitidas
            out = self.model.detect_language(audio)
            probs = dict(out[2]) if len(out) > 2 else {}
            if probs:
                return max(self.languages, key=lambda lang: probs.get(lang, 0.0))
        except Exception as e:  # noqa: BLE001
            self.log(f'Detecção de idioma falhou ({e}); usando "{self.languages[0]}"')
        return self.languages[0]

    def transcribe(self, audio, language=None):
        """audio: float32 mono 16 kHz em [-1, 1]. Devolve TranscriptionResult."""
        cfg = self.cfg
        t0 = time.perf_counter()
        lang = language or self._pick_language(audio)
        kwargs = dict(
            language=lang,
            beam_size=cfg.beam_size,
            condition_on_previous_text=False,   # evita repetição em cadeia
            temperature=[0.0, 0.4],             # no máx. 2 tentativas (latência limitada)
            no_speech_threshold=cfg.no_speech_threshold,
            vad_filter=cfg.vad_filter,
        )
        if cfg.vad_filter:
            kwargs['vad_parameters'] = dict(min_silence_duration_ms=cfg.vad_min_silence_ms)
        if cfg.initial_prompt:
            kwargs['initial_prompt'] = cfg.initial_prompt

        segments, info = self.model.transcribe(audio, **kwargs)
        parts, dropped = [], 0
        for seg in segments:                   # gerador: a decodificação roda aqui
            if (cfg.hallucination_filter and seg.no_speech_prob > cfg.no_speech_threshold
                    and seg.avg_logprob < -1.0):
                dropped += 1
                continue
            piece = seg.text.strip()
            if piece:
                parts.append(piece)
        text = ' '.join(parts).strip()
        if cfg.hallucination_filter and text and is_hallucination(text):
            text, dropped = '', dropped + 1

        return TranscriptionResult(
            text=text,
            language=getattr(info, 'language', lang or ''),
            language_prob=float(getattr(info, 'language_probability', 0.0) or 0.0),
            audio_s=len(audio) / SAMPLE_RATE,
            seconds=time.perf_counter() - t0,
            dropped=dropped,
        )

if __name__ == "__main__":
    import os

    # 1. Configura um logger simples para ver o que está acontecendo no terminal
    def simple_log(msg):
        print(f"[Transcriber] {msg}")

    # 2. Instancia o configurador (pode mudar para 'tiny' se quiser testar rápido)
    config = TranscriberConfig(
        model_size='tiny',# Usando tiny para baixar e testar mais rápido
        device='cpu',# auto, cuda ou cpu
        language='en',# en, pt...
        warmup=True    
    )

    # 3. Inicializa o Transcritor (vai disparar o download e o warmup)
    print("--- Inicializando o Transcriber ---")
    transcriber = Transcriber(cfg=config, log=simple_log)
    print("-----------------------------------\n")

    # --- OPÇÃO A: Teste rápido com 3 segundos de SILÊNCIO absoluto ---
    print("--- Teste 1: Enviando 3 segundos de silêncio (deve filtrar alucinações) ---")
    audio_silencio = np.zeros(SAMPLE_RATE * 3, dtype=np.float32)
    
    resultado_silencio = transcriber.transcribe(audio_silencio)
    print(f"Texto transcrito: '{resultado_silencio.text}'")
    print(f"Idioma detectado: {resultado_silencio.language} ({resultado_silencio.language_prob:.2f})")
    print(f"Tempo de processamento: {resultado_silencio.seconds:.2f}s | RTF: {resultado_silencio.rtf:.4f}")
    print(f"Segmentos descartados pelo filtro: {resultado_silencio.dropped}")
    print("-----------------------------------------------------------------------\n")

    # --- OPÇÃO B: Teste com um arquivo .wav real (Opcional) ---
    # Substitua pelo caminho de um arquivo real se quiser testar a voz
    caminho_audio_real = "seu_audio.wav" 

    if os.path.exists(caminho_audio_real):
        print(f"--- Teste 2: Transcrevendo arquivo real: {caminho_audio_real} ---")
        try:
            import soundfile as sf
            
            # Carrega o áudio usando a biblioteca soundfile
            data, samplerate = sf.read(caminho_audio_real)
            
            # Garante que o áudio seja convertido para Mono se for Estéreo
            if len(data.shape) > 1:
                data = np.mean(data, axis=1)
                
            # Verifica se o sample rate está correto
            if samplerate != SAMPLE_RATE:
                print(f"Aviso: O áudio está em {samplerate}Hz, mas o Whisper espera {SAMPLE_RATE}Hz.")
            
            # Converte explicitamente para float32
            audio_real = data.astype(np.float32)
            
            # Executa a transcrição do áudio real
            resultado_real = transcriber.transcribe(audio_real)
            print(f"Texto final: \"{resultado_real.text}\"")
            print(f"Tempo de processamento: {resultado_real.seconds:.2f}s | RTF: {resultado_real.rtf:.4f}")
            
        except ImportError:
            print("Para testar arquivos .wav reais, instale a biblioteca: pip install soundfile")
        except Exception as e:
            print(f"Erro ao ler o arquivo de áudio: {e}")
        print("-----------------------------------------------------------------------")
    else:
        print(f"Dica: Se quiser testar voz real, coloque um arquivo em '{os.path.abspath(caminho_audio_real)}'")
