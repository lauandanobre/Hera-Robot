"""Ferramentas de linha de comando (sem ROS) para testar o reconhecimento de fala.

  hera_cli devices                       lista microfones e seus índices
  hera_cli record --out ~/dataset        grava frases de teste (.wav + .txt)
  hera_cli listen --model small          escuta e transcreve em loop
"""

import argparse
import sys
from pathlib import Path

from . import perf
from .audio_io import Microphone, list_input_devices, write_wav
from .recorder import RecorderConfig, UtteranceRecorder
from .transcriber import Transcriber, TranscriberConfig


def add_model_args(ap):
    ap.add_argument('--model', default='medium',
                    help='tiny/base/small/medium/large-v3-turbo ou pasta local')
    ap.add_argument('--device', default='auto', help='auto | cuda | cpu')
    ap.add_argument('--compute', default='auto', help='auto | int8_float16 | float16 | int8')
    ap.add_argument('--language', default='pt', help="'pt', 'en', 'auto' ou 'pt,en'")
    ap.add_argument('--beam', type=int, default=2)
    ap.add_argument('--no-vad-filter', action='store_true')
    ap.add_argument('--prompt', default='', help='initial_prompt (vocabulário esperado)')
    ap.add_argument('--offline', action='store_true', help='local_files_only')


def add_mic_args(ap):
    ap.add_argument('--device-index', type=int, default=-1,
                    help='índice do microfone (veja "devices")')
    ap.add_argument('--vad', default='energy', choices=['energy', 'webrtc'])
    ap.add_argument('--max-wait', type=float, default=8.0)
    ap.add_argument('--silence', type=float, default=1.0)


def build_recorder(args):
    cfg = RecorderConfig(max_wait_speech_s=args.max_wait, silence_end_s=args.silence,
                         vad_mode=args.vad)
    return UtteranceRecorder(cfg, log=print)


def build_transcriber(args):
    return Transcriber(TranscriberConfig(
        model_size=args.model, device=args.device, compute_type=args.compute,
        language=args.language, beam_size=args.beam, vad_filter=not args.no_vad_filter,
        initial_prompt=args.prompt, local_files_only=args.offline), log=print)


def record_once(mic, recorder):
    mic.start()
    try:
        return recorder.record(mic.read)
    finally:
        mic.stop()


def cmd_devices(_args):
    for idx, name, ch, rate in list_input_devices():
        print(f'[{idx}] {name}  ({ch} canal(is), {rate} Hz)')
    return 0


def cmd_listen(args):
    recorder = build_recorder(args)
    mic = Microphone(chunk=recorder.chunk, device_index=args.device_index, log=print)
    tr = build_transcriber(args)
    print(f'Memória: {perf.describe()}')
    print('Fale após o bipe. Ctrl+C para sair.\n')
    try:
        while True:
            mic.play_tone()
            rec = record_once(mic, recorder)
            if rec.audio is None:
                print(f'(nada: {rec.reason}; ruído≈{rec.noise_floor:.0f})')
                continue
            res = tr.transcribe(rec.audio)
            print(f'[{res.audio_s:.1f}s áudio | {res.seconds:.2f}s | RTF {res.rtf:.2f} | '
                  f'{res.language}] {res.text or "(vazio)"}')
            if args.once:
                break
    except KeyboardInterrupt:
        print('\nEncerrado.')
    finally:
        mic.close()
    return 0


def cmd_record(args):
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    recorder = build_recorder(args)
    mic = Microphone(chunk=recorder.chunk, device_index=args.device_index, log=print)
    n = len(list(out.glob('*.wav')))
    print(f'Gravando em {out}. Enter vazio na referência encerra.\n')
    try:
        while True:
            ref = input('Frase que você vai dizer (referência): ').strip()
            if not ref:
                break
            mic.play_tone()
            rec = record_once(mic, recorder)
            if rec.audio is None:
                print(f'  não captei fala ({rec.reason}); tente de novo.')
                continue
            n += 1
            name = out / f'frase_{n:03d}'
            write_wav(f'{name}.wav', rec.audio)
            Path(f'{name}.txt').write_text(ref + '\n', encoding='utf-8')
            print(f'  salvo: {name}.wav ({rec.duration_s:.1f}s)')
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        mic.close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='hera_cli', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('devices', help='lista microfones').set_defaults(fn=cmd_devices)

    p_listen = sub.add_parser('listen', help='escuta e transcreve em loop')
    add_model_args(p_listen)
    add_mic_args(p_listen)
    p_listen.add_argument('--once', action='store_true', help='só uma fala')
    p_listen.set_defaults(fn=cmd_listen)

    p_rec = sub.add_parser('record', help='grava frases de teste com referência')
    add_mic_args(p_rec)
    p_rec.add_argument('--out', default='~/hera_dataset')
    p_rec.set_defaults(fn=cmd_record)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except ImportError as e:
        print(f'Dependência ausente: {e.name or e}. Instale com:\n'
              '  sudo apt install portaudio19-dev && pip install -r requirements-speech.txt')
        return 1


if __name__ == '__main__':
    sys.exit(main())
