import os

from setuptools import setup, find_packages

import simple_action_server as sas


def short_description():
    return sas.__doc__.strip()


def long_description():
    if os.path.exists('README.md'):
        with open('README.md') as f:
            return f.read()
    else:
        return short_description()


if __name__ == '__main__':
    setup(
        name='simple_action_server',
        version=sas.__version__,
        description=short_description(),
        long_description=long_description(),
        url='https://github.com/bedezign/simple_action_server.git',
        download_url='https://github.com/bedezign/simple_action_server.git',
        author=sas.__author__,
        author_email='steve@bedezign.com',
        license=sas.__license__,
        packages=find_packages(),
        entry_points={
            'console_scripts': [
                'sas = simple_action_server.__main__:main',
            ],
        },
        classifiers=[
            'Development Status :: 3 - Alpha',
            'Intended Audience :: Developers',
            'Programming Language :: Python :: 3.6',
            'Programming Language :: Python :: 3.7',
            'Operating System :: OS Independent',
            'Environment :: Console',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: MIT License',
            'Topic :: Internet :: WWW/HTTP',
            'Topic :: Internet :: WWW/HTTP :: HTTP Servers',
            'Topic :: Software Development',
            'Topic :: System :: Networking',
            'Topic :: Utilities'
        ],
        python_requires='>=3.6'
    )
