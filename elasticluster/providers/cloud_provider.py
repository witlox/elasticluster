#! /usr/bin/env python
#
#   Copyright (C) 2013-2017 S3IT, University of Zurich
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import abc
import os
from tempfile import NamedTemporaryFile

import paramiko
from libcloud.compute.base import NodeAuthSSHKey, NodeAuthPassword
from libcloud.compute.types import NodeState
from paramiko import SSHException

from elasticluster import log
from elasticluster.exceptions import ConfigurationError, KeypairError

Driver = None

EXPLICIT_CONFIG = [
    'floating_ip'
]


class CloudProvider(object):
    __metaclass__ = abc.ABCMeta

    driver = None
    project_name = None
    floating_ip = False
    rules = None
    auth = None

    @abc.abstractmethod
    def __init__(self, storage_path=None, **config):
        self.storage_path = storage_path
        self.project_name = config.get('project_name')
        self.key_name = config.get('user_key_name')

    @abc.abstractmethod
    def allocate_floating_ip(self, node):
        pass

    @abc.abstractmethod
    def deallocate_floating_ip(self, node):
        pass

    @abc.abstractmethod
    def start_instance(self, **config):
        self._prepare_key_pair(config.get('user_key_name'),
                               config.get('user_key_private'),
                               config.get('user_key_public'),
                               config.get('image_user_password'))
        if self.driver.get_key_pair(config.get('user_key_name')):
            config['auth'] = NodeAuthSSHKey(self.driver.get_key_pair(config.get('user_key_name')).public_key)
        else:
            config['auth'] = NodeAuthPassword(config.get('image_user_password'))

        for key in [k for k in config.keys() if k not in EXPLICIT_CONFIG]:
            list_function = next(self.__check_list_function(key), None)
            if list_function:
                populated_list = self.__check_name_or_id(config[key], list_function())
                if populated_list and len(populated_list) > 0:
                    if key.endswith('s'):
                        config[key] = populated_list
                    else:
                        config[key] = populated_list[0]
        if log.very_verbose:
            log.debug(dict(config))
        return config

    def list_nodes(self):
        return self.driver.list_nodes()

    def stop_instance(self, node):
        node = self._get_node(node)
        if node:
            self.deallocate_floating_ip(node)
            node.destroy()

    def start_node(self, config):
        print(config)
        node = self.driver.create_node(**config)
        if self.floating_ip:
            self.allocate_floating_ip(node)
        return node

    def is_instance_running(self, node):
        node = self._get_node(node)
        if node:
            return node.state == NodeState.RUNNING
        return False

    def get_ips(self, node):
        node = self._get_node(node)
        if node:
            return node.public_ips + node.private_ips
        return list()

    def _get_node(self, node):
        return next(iter([n for n in self.driver.list_nodes() if n.id == node.id]), None)

    def __import_pem(self, kf, key_name, pem_file_path, password):
        try:
            pem = paramiko.RSAKey.from_private_key_file(os.path.expandvars(os.path.expanduser(pem_file_path)),
                                                        password)
        except SSHException:
            try:
                pem = paramiko.DSSKey.from_private_key_file(os.path.expandvars(os.path.expanduser(pem_file_path)),
                                                            password)
            except SSHException:
                raise KeypairError('could not import %s in rsa or dss format', pem_file_path)
        if not pem:
            raise KeypairError('could not import %s', pem_file_path)
        else:
            f = NamedTemporaryFile('w+t')
            f.write('{} {}'.format(pem.get_name(), pem.get_base64()))
            kf(name=key_name, key_file_path=f.name)
            f.close()

    def _prepare_key_pair(self, key_name, private_key_path, public_key_path, password):
        list_keys = next(self.__check_list_function('key_pairs'), None)
        if not list_keys:
            log.warn('key management not supported by provider')
            return
        if not key_name:
            log.warn('user_key_name has not been defined, assuming password based authentication')
            return
        log.debug("Checking key pair `%s` ...", key_name)
        if key_name in [k.name for k in list_keys()]:
            log.debug('Key pair is already installed.')
            return
        log.debug("Key pair `%s` not found, installing it.", key_name)
        kf, _ = self.__function_or_ex_function('import_key_pair_from_file')
        if not kf:
            log.warn('key import not supported by provider')
            return
        if public_key_path:
            log.debug("importing public key from path %s", public_key_path)
            if not kf(name=key_name, key_file_path=os.path.expandvars(os.path.expanduser(public_key_path))):
                log.error('cannot import public key')
        elif private_key_path:
            if not private_key_path.endswith('.pem'):
                raise ConfigurationError('can only work with .pem private keys, '
                                         'derive public key and set user_key_public')
            log.debug("deriving and importing public key from private key")
            self.__import_pem(kf, key_name, private_key_path, password)
        elif os.path.exists(os.path.join(self.storage_path, '{}.pem'.format(key_name))):
            self.__import_pem(kf, key_name, os.path.join(self.storage_path, '{}.pem'.format(key_name)), password)
        else:
            key_pair = self.driver.create_key_pair(name=key_name)
            with open(os.path.join(self.storage_path, '{}.pem'.format(key_name)), 'w') as new_key_file:
                new_key_file.write(key_pair)
            self.__import_pem(kf, key_name, os.path.join(self.storage_path, '{}.pem'.format(key_name)), password)

    """
    Check if a list function exists for a key on a driver
    """
    def __check_list_function(self, func):
        for lf in [getattr(self.driver, c, None) for c in dir(self.driver) if 'list_{}'.format(func) in c]:
            yield lf

    """
    Check if a function exists for a key on a driver, or if it is an 'extended' function.
    :returns tuple of callable and key name
    """
    def __function_or_ex_function(self, func):
        if func in dir(self.driver):
            return getattr(self.driver, func, None), func
        elif 'ex_{}'.format(func) in dir(self.driver):
            return getattr(self.driver, 'ex_'.format(func), None), 'ex_'.format(func)
        return None, None

    """
    Check if a value chain (ex. 'a,b,c') exists in our list of known items
    """
    @staticmethod
    def __check_name_or_id(values, known):
        result = []
        for element in [e.strip() for e in values.split(',')]:
            for item in [i for i in known if i.name == element or i.id == element]:
                    result.append(item)
        return result
