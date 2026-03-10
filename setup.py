from setuptools import setup, find_packages

setup(
    name='helloagi',
    version='0.1.0',
    description='Governed AGI-like local agent runtime with SRG and ALE',
    package_dir={'': 'src'},
    packages=find_packages(where='src'),
    entry_points={'console_scripts': ['helloagi=agi_runtime.cli:main']},
)
