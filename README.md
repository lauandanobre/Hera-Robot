# Hera-Robot

Esse repositório contém os pacotes ROS 2 usados para desenvolver a robô Hera, uma plataforma de pesquisa e prototipagem focada em interação por voz. A ideia central é permitir que a robô escute comandos e frases em português, transforme o áudio em texto e use esse texto para decidir ações, responder ou continuar um fluxo de comunicação com o usuário.

A Hera não é apenas um robô que “ouve”; ela integra microfone, reconhecimento de fala, nós ROS e lógica de controle em um fluxo orientado a robótica. Em termos práticos, o sistema captura áudio, reconhece o que foi falado e entrega esse resultado para outros nós que podem acionar motores, validar comandos ou responder ao usuário.

## 1. O que a Hera faz

A proposta da Hera é tornar a interação com o robô mais natural e menos dependente de teclado, interface gráfica ou botões físicos. O fluxo geral é:

- o microfone capta a fala do usuário;
- um nó de transcrição converte áudio em texto;
- a mensagem reconhecida é tratada como comando, frase livre ou confirmação;
- a lógica do robô decide a ação ou resposta correspondente;
- o sistema pode repetir a resposta em texto ou direcionar a ação para outros componentes do robô.

Na prática, isso permite coisas como:

- reconhecer comandos curtos e específicos, como “avançar”, “parar” ou “direita”;
- transcrever fala em linguagem natural em português;
- permitir protótipos de robótica assistida por voz;
- testar diferentes modelos de reconhecimento em uma mesma base ROS 2.

## 2. Visão geral da arquitetura

A estrutura de comunicação é simples e modular. Os nós principais do projeto se conectam por serviços ROS 2 para ouvir e processar a fala.

```text
Usuário / microfone
        |
        v
   [nó de captura]
        |
        v
   [hear / transcrever_fala]
      /                  \
     /                    \
    v                      v
Vosk (comandos)         Whisper / Faster-Whisper
    |                      |
    v                      v
 texto reconhecido  ->  texto reconhecido
        \                 /
         \               /
          `--> lógica da robô / ação / resposta
```

Assim, a fala entra no sistema por um serviço ROS, é processada por um modelo de reconhecimento e o texto resultante alimenta a lógica da robô. O pacote `hera_speech` usa a abordagem mais moderna com Whisper/Faster-Whisper, enquanto o pacote `vosk_speech` explora um fluxo mais orientado a comandos, com regras e limitação de comandos.

## 3. Estrutura do Projeto

O workspace de desenvolvimento principal está localizado no diretório `hera_ws`.

Os códigos-fonte dos pacotes ROS2 estão localizados em `src/`.

- pacote principal de fala: `src/hera_speech`
- pacote de interação e teste: `src/my_robot_controller`
- pacote de referência com Vosk: `src/vosk_speech`
- exemplo básico: `src/my_robot_controller/my_robot_controller/my_first_node.py`

## 4. Vosk x Whisper

As duas versões existentes no repositório não são redundantes: elas representam duas fases e objetivos diferentes do mesmo problema.

O pacote `vosk_speech` foi usado para focar em reconhecimento offline, leve e orientado a comandos. Ele funciona bem quando a robô precisa decidir rapidamente entre um conjunto limitado de ações, como “avançar”, “parar”, “esquerda” e “direita”. Esse fluxo foi especialmente útil para protótipos de robótica em tempo real, onde a velocidade, a confiabilidade e a validação de comandos são mais importantes do que a liberdade de linguagem.

Já o pacote `hera_speech` usa Whisper via `faster-whisper`, com foco em transcrição mais natural e robusta de fala contínua em português. Ele entrega melhor resultado para frases abertas, texto mais longo e contexto geral da fala do usuário. Em outras palavras, o Vosk entregou a “camada de comando” da Hera; o Whisper entregou a “camada de transcrição livre e mais rica”.

Essa separação faz sentido em um projeto de robótica: primeiro se valida a operação por comando, depois se expande para linguagem mais natural e menos rígida. Por isso, o repositório guarda as duas versões: uma para controle operacional e outra para compreensão mais ampla da fala.

## 5. Instruções de compilação

Os códigos-fonte dos pacotes ROS2 estão localizados no diretório `src/`.

> Observação: este fluxo foi pensado para Ubuntu 22.04 com ROS 2 Humble instalado. Ele não foi validado para outros sistemas operacionais ou distribuições.

### 5.1 Forma tradicional de rodar:

Entre no workspace:
```bash
cd hera_ws
```
Ative o ambiente Ros2:
```bash
source /opt/ros/humble/setup.bash
```
Compile o projeto:
```bash
colcon build
```
Ative o setup.bash:
```bash
source install/setup.bash
```
Rode o projeto de exemplo:
```bash
ros2 run my_robot_controller my_first_node
```

### 5.2 Uma outra forma de rodar rapidamente:

Na raiz do repositório, execute:

```bash
chmod +x build.sh
./build.sh
```

### Esse script automaticamente:

- carrega o ambiente do ROS 2 com `source /opt/ros/humble/setup.bash`
- compila o workspace com `colcon build --symlink-install`
- carrega o ambiente de instalação com `source install/setup.bash`
- executa o nó `my_first_node` do pacote `my_robot_controller`

Você também pode passar o pacote e o nó desejados:

```bash
./build.sh my_publisher
./build.sh my_robot_controller my_first_node
./build.sh hera_robot transcribe_service
./build.sh hera_robot transcribe_client
./build.sh hera_speech hear
./build.sh hera_speech speak
```

## 6. Próximos passos sugeridos

- conectar o texto reconhecido diretamente a ações do robô;
- criar um pipeline de comandos e confirmação de segurança;
- avaliar qualidade do reconhecimento em diferentes ambientes sonoros;
- desenvolver uma camada de resposta em voz, além da transcrição.

Essa base já deixa a arquitetura pronta para evoluir do reconhecimento de comando para uma interação mais natural com a Hera.
