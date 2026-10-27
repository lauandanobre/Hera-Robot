import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'hera_speech'

setup(
    name=package_name,
    version='1.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='lauanda nobre',
    maintainer_email='none',
    description='Fala offline para a Hera: faster-whisper (hear_v2) e ferramentas de teste',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # versões antigas (continuam funcionando)
            'hear = hera_speech.hear:main',
            'speak = hera_speech.speak:main',
            'hear_node = hera_speech.hear_node:main',
            'speak_node = hera_speech.speak_node:main',
            
            # versão nova
            'hear_v2 = hera_speech.hear_v2:main',
            'hera_cli = hera_speech.cli:main',
            'hera_bench = hera_speech.bench:main',
        ],
    },
)
