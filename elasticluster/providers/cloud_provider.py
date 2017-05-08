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
from elasticluster.exceptions import SecurityGroupError, ConfigurationError, KeypairError

Driver = None


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
    def resolve_network(self, network_id):
        pass

    @abc.abstractmethod
    def allocate_floating_ip(self, node):
        pass

    @abc.abstractmethod
    def deallocate_floating_ip(self, node):
        pass

    @abc.abstractmethod
    def resolve_security_group(self, security_group_name):
        pass

    @abc.abstractmethod
    def list_security_groups(self):
        pass

    @abc.abstractmethod
    def start_instance(self, **config):
        self.prepare_key_pair(config.get('user_key_name'),
                              config.get('user_key_private'),
                              config.get('user_key_public'),
                              config.get('image_user_password'))
        if self.driver.get_key_pair(config.get('user_key_name')):
            self.auth = NodeAuthSSHKey(self.driver.get_key_pair(config.get('user_key_name')).public_key)
        else:
            self.auth = NodeAuthPassword(config.get('image_user_password'))

    def list_nodes(self):
        return self.driver.list_nodes()

    def stop_instance(self, node):
        node = self._get_node(node)
        if node:
            self.deallocate_floating_ip(node)
            node.destroy()

    def start_node(self, config):
        config['auth'] = self.auth
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

    def check_security_groups(self, security_groups):
        for g in security_groups:
            if g not in self.list_security_groups():
                raise SecurityGroupError("the specified security group %s does not exist" % g)
        return security_groups

    def check_flavor(self, flavor):
        return next(iter([fl for fl in self.driver.list_sizes() if fl.name == flavor]), None)

    def check_image(self, image_id):
        return next(iter([i for i in self.driver.list_images() if i.id == image_id]), None)

    def list_key_pairs(self):
        try:
            key_pairs = self.driver.list_keypairs()
        except AttributeError:
            key_pairs = self.driver.ex_list_keypairs()
        for kp in key_pairs:
            yield kp.name

    def import_key_from_file(self, name, public_key):
        try:
            self.driver.import_key_pair_from_file(name, public_key)
        except AttributeError:
            self.driver.ex_import_key_pair_from_file(name, public_key)

    def __import_pem(self, key_name, pem_file_path, password):
        try:
            pem = paramiko.RSAKey.from_private_key_file(os.path.expandvars(os.path.expanduser(pem_file_path)), password)
        except SSHException:
            try:
                pem = paramiko.DSSKey.from_private_key_file(os.path.expandvars(os.path.expanduser(pem_file_path)), password)
            except SSHException:
                raise KeypairError('could not import %s in rsa or dss format', pem_file_path)
        if not pem:
            raise KeypairError('could not import %s', pem_file_path)
        else:
            f = NamedTemporaryFile('w+t')
            f.write('{} {}'.format(pem.get_name(), pem.get_base64()))
            self.import_key_from_file(key_name, f.name)
            f.close()

    def prepare_key_pair(self, key_name, private_key_path, public_key_path, password):
        if not key_name:
            log.warn('user_key_name has not been defined, assuming password based authentication')
            return
        log.debug("Checking key pair `%s` ...", key_name)
        if key_name in self.list_key_pairs():
            log.debug('Key pair is already installed.')
            return
        log.debug("Key pair `%s` not found, installing it.", key_name)
        if public_key_path:
            log.debug("importing public key from path %s", public_key_path)
            self.import_key_from_file(key_name, os.path.expandvars(os.path.expanduser(public_key_path)))
        elif private_key_path:
            if not private_key_path.endswith('.pem'):
                raise ConfigurationError('can only work with .pem private keys, '
                                         'derive public key and set user_key_public')
            log.debug("deriving and importing public key from private key")
            self.__import_pem(key_name, private_key_path, password)
        elif os.path.exists(os.path.join(self.storage_path, '{}.pem'.format(key_name))):
            self.__import_pem(key_name, os.path.join(self.storage_path, '{}.pem'.format(key_name)), password)
        else:
            key_pair = self.driver.create_key_pair(name=key_name)
            with open(os.path.join(self.storage_path, '{}.pem'.format(key_name)), 'w') as new_key_file:
                new_key_file.write(key_pair)
            self.__import_pem(key_name, os.path.join(self.storage_path, '{}.pem'.format(key_name)), password)

    def _get_node(self, node):
        return next(iter([n for n in self.driver.list_nodes() if n.id == node.id]), None)

    def _get_networks(self, config):
        networks = []
        if 'network_ids' in config:
            network_ids = [net_id.strip() for net_id in config['network_ids'].split(',')]
            for network_id in network_ids:
                network = self.resolve_network(network_id)
                log.debug('attaching network (%s) as %s', network_id, network)
                networks.append(network)
        return networks

    def _get_security_groups(self, config):
        sgs = []
        if config.get('security_group'):
            for sg in config.get('security_group').split(','):
                sgs.append(sg.strip())
        if config.get('security_groups'):
            for sg in config.get('security_groups').split(','):
                sgs.append(sg.strip())
        for g in self.check_security_groups(set(sgs)):
            yield self.resolve_security_group(g)

