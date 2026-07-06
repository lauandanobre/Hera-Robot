#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$SCRIPT_DIR/hera_ws"
ROS_SETUP="/opt/ros/humble/setup.bash"

# Evita falhas ao sourcear o ambiente do ROS 2 em shells com nounset habilitado.
set +u

if [ ! -f "$ROS_SETUP" ]; then
  echo "Arquivo de ambiente do ROS 2 não encontrado em $ROS_SETUP"
  exit 1
fi

source "$ROS_SETUP"

cd "$WORKSPACE_DIR"

echo "Compilando o workspace..."
colcon build --symlink-install

source install/setup.bash

if [ "$#" -eq 0 ]; then
  PACKAGE="my_robot_controller"
  NODE="my_first_node"
elif [ "$#" -eq 1 ]; then
  case "$1" in
    my_robot_controller)
      PACKAGE="my_robot_controller"
      NODE="my_first_node"
      ;;
    hera_robot)
      PACKAGE="hera_robot"
      NODE="transcribe_service"
      ;;
    *)
      PACKAGE="my_robot_controller"
      NODE="$1"
      ;;
  esac
else
  PACKAGE="$1"
  NODE="$2"
fi

echo "Executando: ros2 run $PACKAGE $NODE"
exec ros2 run "$PACKAGE" "$NODE"
