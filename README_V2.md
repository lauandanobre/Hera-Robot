# hera_speech v2 — guia rápido pra não me perder

Nada do que já existia foi alterado (`hear`, `hear_node`, `speak`, `speak_node` seguem funcionando).
Arquivos novos: `hear_v2`, `recorder`, `transcriber`, `audio_io`, `perf`, `cli`, `bench`.

### o que cada um faz:
hear_v2 : escuta e transcreve, com VAD, beam search, filtro de alucinação do microfone e onde configura o suporte a múltiplos modelos, idiomas e se ira rodar na CPU ou GPU
recorder: grava áudio em .wav e texto em .txt, para criar datasets para treinar ou testar o modelo
transcriber: transcreve áudio em .wav para texto, usando o modelo escolhido
audio_io: funções de baixo nível para lidar com o microfone, arquivos de áudio e buffers também de áudio
perf: mede a performance do modelo, com diferentes tamanhos, idiomas, beam search e VAD, e gera CSV com os resultados
cli: interface de linha de comando para testar o modelo
bench: mede a performance do modelo, com diferentes tamanhos, idiomas, beam search e VAD, e gera CSV com os resultados (igual ao perf, mas mais rápido e sem ROS)

## Instalar e compilar

```bash
pip install -r requirements-speech.txt          # antes: sudo apt install portaudio19-dev
cd ~/hera_ws && colcon build --symlink-install --packages-select hera_speech
source install/setup.bash
```

## Rodar

```bash
ros2 run hera_speech hear_v2                      # padrão: medium, idioma pt, GPU se houver
ros2 launch hera_speech hear_v2.launch.py         # usa config/hear_v2.yaml
ros2 run hera_speech hear_v2 --ros-args -p model_size:=small -p language:=en
```

Chamar o serviço e ver o resultado:

```bash
ros2 service type /hear                           # mostra se é Trigger ou hera_msgs/Hear
ros2 service call /hear std_srvs/srv/Trigger     # sem hera_msgs (texto em "message")
ros2 service call /hear hera_msgs/srv/Hear "{}"  # com hera_msgs (texto em "text")
ros2 topic echo /transcription                    # o texto também sai aqui, nos dois modos
ros2 param list /hear_node
```

Com `hera_msgs` instalado o serviço `hear` é `hera_msgs/Hear` (igual ao oficial). Sem ele, vira
`std_srvs/Trigger` e o bipe é tocado localmente. Para forçar: `-p service_type:=trigger`.

## Testar sem ROS

```bash
hera_cli devices                                  # índices dos microfones
hera_cli listen --model small --language pt       # escuta e mostra tempo e RTF
hera_cli record --out ~/hera_dataset              # grava frases de teste (.wav + .txt)
```

## Medir performance

```bash
hera_bench --data ~/hera_dataset \
           --models medium,small --compute int8_float16,float16 --beams 1,5 --vad on,off \
           --csv resultado.csv
```

Colunas: carga (s), RAM pico, VRAM, latência média/máxima, RTF (tempo ÷ duração do áudio;
menor que 1 = mais rápido que o tempo real) e WER (taxa de erro de palavras).

Monitorar o sistema enquanto o nó roda:

```bash
watch -n1 nvidia-smi                                                # VRAM e uso da GPU
nvidia-smi --query-compute-apps=pid,used_memory --format=csv        # VRAM por processo
ps -o pid,rss,cmd -p $(pgrep -f hear_v2)                            # RAM (rss em kB)
/usr/bin/time -v hera_cli listen --once 2>&1 | grep -E "Maximum resident|Elapsed"
ros2 run hera_speech hear_v2 --ros-args --log-level debug
arecord -l && arecord -f S16_LE -r 16000 -c 1 -d 5 teste.wav        # testa o microfone
```

## Testes automáticos (sem GPU nem ROS)

```bash
cd hera_ws/src/hera_speech && python3 -m unittest discover -s test -v
```

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| `ModuleNotFoundError: pyaudio` | `sudo apt install portaudio19-dev && pip install pyaudio` |
| Não acha o modelo offline | rode uma vez com internet, depois use `-p local_files_only:=true` |
| CUDA sem memória | o nó cai sozinho para outro `compute_type` e por fim CPU (veja o log) |
| Corta o início da fala | aumente `silence_end_s` e confira o microfone com `arecord` |
| Ruído demais dispara a gravação | suba `min_rms` ou use `vad_mode:=webrtc` |
| Texto estranho em silêncio | mantenha `vad_filter:=true` e `hallucination_filter:=true` |
