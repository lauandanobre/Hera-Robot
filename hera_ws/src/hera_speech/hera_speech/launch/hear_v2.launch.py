import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    config = os.path.join(get_package_share_directory('hera_speech'), 'config', 'hear_v2.yaml')
    return LaunchDescription([
        Node(
            package='hera_speech',
            executable='hear_v2',
            name='hear_node',
            output='screen',
            parameters=[config],
        ),
    ])
