from setuptools import find_packages, setup

package_name = 'my_robot_controller'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'vosk', 'pyaudio'],
    zip_safe=True,
    maintainer='lauanda nobre',
    maintainer_email='hello-nobre@outlook.com',
    description='Esse é um repositório de estudos do ROS2 Humble',
    license='Unlicensed',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            "my_first_node = my_robot_controller.my_first_node:main",
            "my_publisher = my_robot_controller.my_publisher:main",
            "my_subscriber = my_robot_controller.my_subscriber:main",
            "transcrever = my_robot_controller.transcribe:main",
            "transcrever_service = my_robot_controller.transcribeService:main",
            "transcrever_client = my_robot_controller.transcribeClient:main",
        ],
    },
)
