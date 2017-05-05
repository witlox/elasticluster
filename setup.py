#!/usr/bin/env python
# -*- coding: utf-8 -*-#
#
#
# Copyright (C) 2013-2017 University of Zurich. All rights reserved.
#
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

import sys
import pip

# fix Python issue 15881 (on Python <2.7.5)
try:
    import multiprocessing
except ImportError:
    pass


# requirements for latest versions of setuptools
def pip_upgrade(package):
    pip.main(['install', '--upgrade', package])


def pip_install(package):
    pip.main(['install', package])

pip_upgrade('pip')
pip_install('six')
pip_install('packaging')
pip_install('appdirs')
pip_install('tox')


## auxiliary functions
#
def read_whole_file(path):
    """
    Return file contents as a string.
    """
    with open(path, 'r') as stream:
        return stream.read()


## test runner setup
#
# See http://tox.readthedocs.org/en/latest/example/basic.html#integration-with-setuptools-distribute-test-commands
# on how to run tox when python setup.py test is run
#
from setuptools.command.test import test as TestCommand


class Tox(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import tox
        errno = tox.cmdline(self.test_args)
        sys.exit(errno)


## conditional dependencies
#
# Although PEP-508 and a number of predecessors specify a syntax for
# conditional dependencies in Python packages, support for it is inconsistent
# (at best) among the PyPA tools. An attempt to use the conditional syntax has
# already caused issues #308, #249, #227, and many more headaches to me while
# trying to find a combination of `pip`, `setuptools`, `wheel`, and dependency
# specification syntax that would work reliably across all supported Linux
# distributions. I give up, and revert to computing the dependencies via
# explicit Python code in `setup.py`; this will possibly break wheels but it's
# the least damage I can do ATM.

python_version = sys.version_info[:2]
if python_version == (2, 6):
    version_dependent_requires = [
        'configparser',
    ]
elif python_version == (2, 7):
    version_dependent_requires = [
        'configparser',
    ]
else:
    version_dependent_requires = [
        'urllib3',
    ]

## real setup description begins here
#
from setuptools import setup, find_packages

setup(
    name="elasticluster",
    version=read_whole_file("version.txt").strip(),
    description="A command line tool to create, manage and setup computing clusters hosted on a public or private cloud infrastructure.",
    long_description=read_whole_file('README.rst'),
    author="Services and Support for Science IT, University of Zurich",
    author_email="team@s3it.lists.uzh.ch",
    license="LGPL",
    keywords="cloud openstack amazon ec2 ssh hpc gridengine torque slurm batch job elastic",
    url="https://github.com/gc3-uzh-ch/elasticluster",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
        "License :: DFSG approved",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX :: Linux",
        "Operating System :: POSIX :: Other",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Topic :: System :: Clustering",
        "Topic :: Education",
        "Topic :: Scientific/Engineering",
        "Topic :: System :: Distributed Computing",
    ],
    packages=find_packages(),
    include_package_data=True,  # include files mentioned by MANIFEST.in
    entry_points={
        'console_scripts': [
            'elasticluster = elasticluster.__main__:main',
        ]
    },
    install_requires=([
                          'PyYAML',
                          'ansible>=2.2.1',  ## see: https://www.computest.nl/advisories/CT-2017-0109_Ansible.txt
                          'click>=4.0',  ## click.prompt() added in 4.0
                          'coloredlogs',
                          'netaddr',
                          'paramiko',
                          'schema',
                          'apache-libcloud==1.5.0',
                      ] + version_dependent_requires),
    tests_require=['tox', 'mock', 'pytest>=2.10'],  # read right-to-left
    cmdclass={'test': Tox},
)
