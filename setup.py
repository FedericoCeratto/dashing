"""Setup.py."""
import datetime
from codecs import open
from os import path
from setuptools import setup, find_packages
from dashing import __version__

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

install_requires = [
    "blessed"
]

if 'dev' in __version__:
    now = datetime.datetime.now()
    release_number = (now - datetime.datetime(2018, 2, 22)
                      ).total_seconds() / 60
    version = "{}{}".format(__version__, int(release_number))
else:
    version = __version__

setup(
    name='dashing',
    version=version,
    description="High-level terminal-based dashboard",
    long_description=long_description,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6'
    ],
    keywords='dashboard terminal',
    author='Chris Maillefaud',
    author_email='chris@megalus.com.br',
    url='https://github.com/chrismaille/dashing',
    license='LGPL',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    include_package_data=True,
    install_requires=install_requires,
)
