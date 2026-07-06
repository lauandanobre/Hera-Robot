from setuptools import find_packages, setup

package_name = 'hera_robot'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'vosk', 'pyaudio'],
    zip_safe=True,
    maintainer='lauanda nobre',
    maintainer_email='none',
    description='Pacote ROS 2 em Python para o robô Hera, incluindo nós de publicação, assinatura e serviços de transcrição.',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'transcribe_service = hera_robot.transcribeService:main',
            'transcribe_client = hera_robot.transcribeClient:main',
        ],
    },
)