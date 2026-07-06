# Hera-Robot

Esse é um repositório que contém os pacotes de código para robôs que utilizam o ecossistema ROS2 (Robot Operating System 2). Os algoritmos criados foram projetados para utilização na robô Hera.

## Estrutura do Projeto

O workspace de desenvolvimento principal está localizado no diretório `hera_ws`.

Os códigos-fonte dos pacotes ROS2 estão localizados no diretório `src/`.
* **Nó de exemplo:** `src/my_robot_controller/my_robot_controller/my_first_node.py`


# Instruções

Os códigos-fonte dos pacotes ROS2 estão localizados no diretório `src/`.

Já o Nó de exemplo está em: `src/my_robot_controller/my_robot_controller/my_first_node.py`

Para usar, deve-se construir o workspace no diretório raiz `hera_ws`:

```bash
source /opt/ros/humble/setup.bash
```

```
colcon build
```

Depois deve-se carregar o ambiente de instalação e em seguida executar o nó:

```bash
source install/setup.bash

```
ros2 run my_robot_controller my_first_node
```

Comandos principais usados:

- `source /opt/ros/humble/setup.bash`
- `colcon build`
- `source install/setup.bash`
- `ros2 run my_robot_controller my_first_node`

O workspace está em `hera_ws`.
