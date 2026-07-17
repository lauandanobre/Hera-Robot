from setuptools import find_packages, setup

package_name = 'vosk_speech'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='lauanda nobre',
    maintainer_email='none',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'transcribe_service = vosk_speech.transcribeService:main',
            'transcribe_client = vosk_speech.transcribeClient:main',
            'transcribe_service_model_small = vosk_speech.transcribeServiceModelSmall:main',
            'hear = vosk_speech.hear:main', 
        ],
    },
)
