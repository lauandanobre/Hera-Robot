# Hera-Robot

Esse é um repositório que contém os pacotes de código para robôs que utilizam o ecossistema ROS2 (Robot Operating System 2). Os algoritmos criados foram projetados para utilização na robô Hera.

## 1. Estrutura do Projeto

O workspace de desenvolvimento principal está localizado no diretório `hera_ws`.

Os códigos-fonte dos pacotes ROS2 estão localizados no diretório `src/`.
* **Nó de exemplo:** `src/my_robot_controller/my_robot_controller/my_first_node.py`


## 2. Instruções

Os códigos-fonte dos pacotes ROS2 estão localizados no diretório `src/`.

Já o Nó de exemplo está em: `src/my_robot_controller/my_robot_controller/my_first_node.py`.

> Observação: este fluxo foi pensado para Ubuntu 24.04 com ROS 2 Humble instalado. Ele não foi validado para outros sistemas operacionais ou distribuições.

## 2.1 Forma tradicional de rodar:

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

## 2.2 Uma outra forma de rodar rapidamente:

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
```
