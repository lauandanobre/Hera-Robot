from setuptools import find_packages, setup

package_name = 'hera_speech'

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
    description='TODO: Um pacote de fala offline usando o fast-whisper',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'hear = hera_speech.hear:main',
            'speak = hera_speech.speak:main',
        ],
    },
)
