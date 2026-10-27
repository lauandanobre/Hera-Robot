"""
Benchmark do reconhecimento de fala: memória, latência, RTF e erro (WER).
possue funções para avaliar o uso de RAM e VRAM, e um cronometro para medir latência de transcrição

Pasta de dados: pares `frase.wav` + `frase.txt` (texto de referência).
Grave com `hera_cli record` ou use áudios seus (qualquer formato se o
faster-whisper estiver instalado).

Exemplos:
  hera_bench --data ~/hera_dataset
  hera_bench --data ~/hera_dataset --models medium,small --compute int8_float16,float16 \\
             --beams 1,5 --vad on,off --csv resultado.csv

Cada combinação roda em um processo separado, para o pico de RAM de uma
não contaminar a outra.
"""

import argparse
import csv
import itertools
import json
import statistics
import subprocess
import sys
from pathlib import Path

from . import perf
from .audio_io import read_wav
from .transcriber import Transcriber, TranscriberConfig, normalize_for_match

AUDIO_EXT = ('.wav', '.mp3', '.m4a', '.flac', '.ogg')


def wer(ref, hyp):
    # Taxa de erro de palavras (distância de edição / nº de palavras da referência).
    r, h = normalize_for_match(ref).split(), normalize_for_match(hyp).split()
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i]
        for j, hw in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw)))
        prev = cur
    return prev[-1] / len(r)


def load_dataset(folder):
    # carrega o conjunto de dados .txt
    items = []
    for audio in sorted(Path(folder).expanduser().iterdir()):
        if audio.suffix.lower() not in AUDIO_EXT:
            continue
        ref_file = audio.with_suffix('.txt')
        ref = ref_file.read_text(encoding='utf-8').strip() if ref_file.exists() else None
        items.append((audio, ref))
    return items


def run_single(args, model, compute, beam, vad):
    #Roda uma configuração e devolve um dicionário de métricas.
    items = load_dataset(args.data)
    if not items:
        raise SystemExit(f'Nenhum áudio em {args.data}')
    audios = [(p, read_wav(p), ref) for p, ref in items]

    with perf.Stopwatch() as load:
        tr = Transcriber(TranscriberConfig(
            model_size=model, device=args.device, compute_type=compute,
            language=args.language, beam_size=beam, vad_filter=vad,
            initial_prompt=args.prompt, local_files_only=args.offline),
            log=lambda m: print(m, file=sys.stderr))
    ram_loaded, vram_loaded = perf.ram_mb(), perf.gpu_mb()
    if vram_loaded is None:
        vram_loaded = perf.gpu_total_mb()

    lat, rtf, wers = [], [], []
    for path, audio, ref in audios:
        for _ in range(args.runs):
            res = tr.transcribe(audio)
            lat.append(res.seconds)
            rtf.append(res.rtf)
        if ref is not None:
            wers.append(wer(ref, res.text))
        print(f'  {path.name}: {res.seconds:.2f}s | "{res.text}"'
              + (f' | ref: "{ref}"' if ref else ''), file=sys.stderr)

    return dict(
        model=model, compute_req=compute, device=tr.device, compute=tr.compute_type,
        beam=beam, vad='on' if vad else 'off', load_s=round(load.seconds, 1),
        ram_mb=round(ram_loaded or 0), ram_peak_mb=round(perf.ram_peak_mb() or 0),
        vram_mb=round(vram_loaded) if vram_loaded is not None else None,
        lat_mean=round(statistics.mean(lat), 3), lat_max=round(max(lat), 3),
        rtf=round(statistics.mean(rtf), 3),
        wer=round(statistics.mean(wers), 3) if wers else None,
        files=len(audios))


def fmt(v):
    return '-' if v is None else str(v)


def print_table(rows):
    cols = [('model', 'modelo'), ('device', 'disp'), ('compute', 'compute'), ('beam', 'beam'),
            ('vad', 'vad'), ('load_s', 'carga(s)'), ('ram_peak_mb', 'RAM pico MB'),
            ('vram_mb', 'VRAM MB'), ('lat_mean', 'lat média(s)'), ('lat_max', 'lat máx(s)'),
            ('rtf', 'RTF'), ('wer', 'WER')]
    table = [[h for _, h in cols]] + [[fmt(r.get(k)) for k, _ in cols] for r in rows]
    widths = [max(len(row[i]) for row in table) for i in range(len(cols))]
    for n, row in enumerate(table):
        print('  '.join(c.ljust(widths[i]) for i, c in enumerate(row)))
        if n == 0:
            print('  '.join('-' * w for w in widths))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='hera_bench', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data', required=True, help='pasta com .wav + .txt')
    ap.add_argument('--models', default='medium')
    ap.add_argument('--compute', default='int8_float16,float16')
    ap.add_argument('--beams', default='2')
    ap.add_argument('--vad', default='on', help='on, off ou on,off')
    ap.add_argument('--device', default='auto')
    ap.add_argument('--language', default='pt')
    ap.add_argument('--prompt', default='')
    ap.add_argument('--runs', type=int, default=2, help='repetições por arquivo')
    ap.add_argument('--offline', action='store_true')
    ap.add_argument('--csv', default='', help='salvar resultados em CSV')
    ap.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    models = args.models.split(',')
    computes = args.compute.split(',')
    beams = [int(b) for b in args.beams.split(',')]
    vads = [v.strip().lower() in ('on', 'true', '1') for v in args.vad.split(',')]

    if args.child:                      # um processo = uma configuração
        res = run_single(args, models[0], computes[0], beams[0], vads[0])
        print('RESULT ' + json.dumps(res))
        return 0

    rows = []
    for model, comp, beam, vad in itertools.product(models, computes, beams, vads):
        print(f'\n=== {model} | {comp} | beam {beam} | vad {"on" if vad else "off"} ===',
              file=sys.stderr)
        cmd = [sys.executable, '-m', 'hera_speech.bench', '--child', '--data', args.data,
               '--models', model, '--compute', comp, '--beams', str(beam),
               '--vad', 'on' if vad else 'off', '--device', args.device,
               '--language', args.language, '--prompt', args.prompt,
               '--runs', str(args.runs)] + (['--offline'] if args.offline else [])
        out = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
        line = next((ln for ln in out.stdout.splitlines() if ln.startswith('RESULT ')), None)
        if out.returncode != 0 or line is None:
            print('  (falhou; veja as mensagens acima)', file=sys.stderr)
            continue
        rows.append(json.loads(line[len('RESULT '):]))

    if not rows:
        print('Nenhum resultado.')
        return 1
    print()
    print_table(rows)
    if args.csv:
        with open(args.csv, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f'\nSalvo em {args.csv}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
