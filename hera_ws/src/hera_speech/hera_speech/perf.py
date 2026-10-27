# Medição simples de memória e tempo (sem dependências extras, Linux).

import os
import subprocess
import time


def _status_kb(field):
    #lê um campo (em kB) de /proc/self/status; None se não existir.
    try:
        with open('/proc/self/status') as f:
            for line in f:
                if line.startswith(field + ':'):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def ram_mb():
    #RAM atual do processo (RSS) em MB.
    kb = _status_kb('VmRSS')
    return None if kb is None else kb / 1024.0


def ram_peak_mb():
    #pico de RAM do processo (VmHWM) em MB.
    kb = _status_kb('VmHWM')
    return None if kb is None else kb / 1024.0


def _nvidia_smi(query, extra=()):
    try:
        out = subprocess.run(
            ['nvidia-smi', query, '--format=csv,noheader,nounits', *extra],
            capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def gpu_mb(pid=None):
    # essa função retorna a vram para o processo atual
    text = _nvidia_smi('--query-compute-apps=pid,used_memory')
    if text is None:
        return None
    pid = str(pid or os.getpid())
    total, found = 0.0, False
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) == 2 and parts[0] == pid:
            try:
                total += float(parts[1])
                found = True
            except ValueError:
                pass
    return total if found else None


def gpu_total_mb():
    #RRAM total em uso na GPU 0 (MB), de todos os processos.
    text = _nvidia_smi('--query-gpu=memory.used')
    if not text:
        return None
    try:
        return float(text.splitlines()[0].strip())
    except (ValueError, IndexError):
        return None


def describe():
    #Texto curto com a memória atual, para logs
    parts = []
    ram = ram_mb()
    if ram is not None:
        parts.append(f'RAM {ram:.0f} MB')
    vram = gpu_mb()
    if vram is None:
        vram = gpu_total_mb()
        label = 'VRAM (GPU toda)'
    else:
        label = 'VRAM (processo)'
    if vram is not None:
        parts.append(f'{label} {vram:.0f} MB')
    return ' | '.join(parts) if parts else 'memória indisponível'


class Stopwatch:
    #Cronômetro: `with Stopwatch() as sw: ...; sw.seconds`.

    def __enter__(self):
        self._t0 = time.perf_counter()
        self.seconds = 0.0
        return self

    def __exit__(self, *exc):
        self.seconds = time.perf_counter() - self._t0
        return False
