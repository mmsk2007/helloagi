from setuptools import setup, find_packages

setup(
    name='helloagi',
    version='0.3.0',
    description='HelloAGI local-first runtime with governed autonomy, evolving identity, and low-latency response engine',
    package_dir={'': 'src'},
    packages=find_packages(where='src'),
    install_requires=[
        'anthropic',
        'claude-agent-sdk',
        'anyio',
        'google-genai',
    ],
    entry_points={'console_scripts': ['helloagi=agi_runtime.cli:main']},
)
