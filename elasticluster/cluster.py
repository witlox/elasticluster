import glob
import json
import os
import pickle
import socket
import time
from collections import defaultdict

import paramiko
import yaml

from libcloud.compute.base import Node
from libcloud.compute.types import NodeState
from schema import Schema, Optional

from elasticluster import log
from elasticluster.exceptions import TimeoutError, NodeNotFound
from elasticluster.utils import timeout, update_options
from elasticluster.validate import nonempty_str, boolean


def raise_timeout_error(signum, frame):
    raise TimeoutError('Could not initialize all nodes')


KEY_RENAMES = [(r'([0-9a-z_-]+)_min_nodes', r'\1_nodes_min'),
               ('setup_provider', 'setup')]


class Cluster(object):
    rules = {'cloud': str,
             'setup': str,
             'login': str,
             'flavor': nonempty_str,
             'image_id': nonempty_str,
             Optional('floating_ip', default=False): boolean,
             Optional('security_group'): str,
             Optional('security_groups'): str,
             Optional('image_userdata', default=''): str,
             Optional('network_ids'): str,
             # allow other keys w/out restrictions
             Optional(str): str}
    nodes = []
    startup_timeout = 60 * 10
    polling_interval = 10
    ssh_port = 22

    """
    Initialization automatically tries to load any previous state
    """
    def __init__(self, storage_path, storage_type, template, name=None, cloud_instance=None, login_instance=None,
                 setup_instance=None, group_specific_options=None, **options):
        self.storage_path = storage_path
        self.storage_type = storage_type
        self.template = template
        if name:
            self.name = name
        else:
            self.name = template
        self.known_host_file = os.path.expandvars(os.path.expanduser(os.path.join(self.storage_path,
                                                                                  '{}.known_hosts'.format(self.name))))
        self.options = update_options(KEY_RENAMES, Schema(self.rules).validate(options))
        if log.very_verbose:
            log.debug('%s options: %s', self.name, dict(self.options))
        self.cloud = cloud_instance
        self.login = login_instance
        self.setup = setup_instance
        self.group_specific_options = group_specific_options
        if os.path.exists(self.__storage_file_path()):
            self.__load(True)

    def __get_cloud(self):
        return self.__cloud

    def __set_cloud(self, value):
        self.__cloud = value

    cloud = property(__get_cloud, __set_cloud)

    def __get_login(self):
        return self.__login

    def __set_login(self, value):
        self.__login = value

    login = property(__get_login, __set_login)

    def __get_setup(self):
        return self.__setup

    def __set_setup(self, value):
        self.__setup = value

    setup = property(__get_setup, __set_setup)

    def __storage_file_path(self):
        if self.template == self.name:
            return os.path.join(self.storage_path, '{}.{}'.format(self.template, self.storage_type))
        return os.path.join(self.storage_path, '{}.{}'.format(self.name, self.storage_type))

    def __update_node_states(self):
        if self.cloud and self.cloud.provider:
            previous_state = list(self.nodes)
            self.nodes = [pn for pn in self.cloud.provider(storage_path=self.storage_path,
                                                           **dict(self.cloud.options, **self.login.options))
                          .list_nodes() if pn.name in [n.name for n in self.nodes]]
            for node in self.nodes:
                log.debug('got node %s', node)
            # sanity check
            for node in previous_state:
                if node.name not in [n.name for n in self.nodes]:
                    log.warn('inconsistency detected, node %s (id: %s, state: %s) '
                             'not detected on cloud!', node.name, node.id, node.state)

    def __load(self, state_update=False):
        with open(self.__storage_file_path(), 'r') as sf:
            if self.storage_type == 'yaml':
                data = yaml.load(sf)
            elif self.storage_type == 'json':
                data = json.loads(sf)
            else:
                data = pickle.loads(sf)
        self.template = data.get('template')
        self.name = data.get('name')
        if not self.options:
            self.options = data.get('options')
        self.nodes = []
        for node in data.get('nodes'):
            try:
                self.nodes.append(Node(node.get('id'), node.get('name'), node.get('state'), node.get('public_ips'),
                                       node.get('private_ips'), node.get('size'), node.get('created_at'),
                                       node.get('image'), node.get('extra')))
            except AttributeError:
                for active in data['nodes'][node]:
                    node_name = '{}-{}'.format(active['cluster_name'], active['name'])
                    node_known = next(iter(n for n in self.nodes if n.name == node_name), None)
                    if not node_known:
                        self.nodes.append(Node(active['instance_id'], node_name, None, [], [], None))
        if state_update:
            self.__update_node_states()

    def __dump(self, state_update=True):
        with open(self.__storage_file_path(), 'w') as sf:
            storage_buffer = {'template': self.template,
                              'name': self.name,
                              'options': self.options}
            if state_update:
                self.__update_node_states()
            data = []
            for node in self.nodes:
                data.append({'id': node.id,
                             'name': node.name,
                             'state': node.state,
                             'public_ips': node.public_ips,
                             'private_ips': node.private_ips,
                             'size': node.size,
                             'created_at': node.created_at,
                             'image': node.image,
                             'extra': node.extra})
            storage_buffer['nodes'] = data
            if self.storage_type == 'yaml':
                yaml.dump(storage_buffer, sf)
            elif self.storage_type == 'json':
                json.dumps(storage_buffer, sf)
            else:
                pickle.dumps(storage_buffer, sf)

    def node_types(self):
        if self.options:
            for k in [n for n in self.options.keys() if 'nodes' in n]:
                yield k.split('_')[0], int(self.options[k]), [n for n in self.nodes if k.split('_')[0] in n.name]

    def start(self):
        for node_type, amount, _ in self.node_types():
            self.add(node_type, amount)
        log.info('%s nodes initialization started, waiting for steady state...', self.name)
        try:
            with timeout(self.startup_timeout, raise_timeout_error):
                while len([n for n in self.nodes if n.state == NodeState.RUNNING]) != len(self.nodes):
                    self.__update_node_states()
                    for node in self.nodes:
                        log.debug('%s status: %s', node.name, node.state)
                    time.sleep(self.polling_interval)
        except TimeoutError:
            log.error('could not initialize all nodes, destroying cluster %s', self.name)
            for node in self.nodes:
                log.debug('terminating %s', node.name)
                self.remove_by_name(node.name)
        self.__dump()

    def stop(self):
        self.__load()
        for node in self.nodes:
            self.remove_by_name(node.name)
        file_root = os.path.splitext(self.__storage_file_path())[0]
        for cluster_file in glob.glob('{}.*'.format(file_root)):
            os.remove(cluster_file)

    def __last_allocated_node_index(self, node_type):
        node_index = 0
        for node in [n for n in self.nodes if n.name and node_type in n.name]:
            ni = int(node.name.split(node_type)[1])
            if ni > node_index:
                node_index = ni
        return node_index

    def add(self, node_type, count=1, wait=False):
        node_index = self.__last_allocated_node_index(node_type)
        provider = self.cloud.provider(storage_path=self.storage_path, **dict(self.cloud.options, **self.login.options))
        for x in range(node_index + 1, node_index + count + 1):
            node_config = dict(self.options, **self.login.options)
            if node_type in self.group_specific_options.keys():
                for k, v in self.group_specific_options[node_type].items():
                    node_config[k] = v
            if self.template == self.name:
                node_config['node_name'] = '{}-{}{:03}'.format(self.template, node_type, x)
            else:
                node_config['node_name'] = '{}-{}{:03}'.format(self.name, node_type, x)
            log.info('adding node %s to cluster %s', node_config['node_name'], self.name)
            self.nodes.append(provider.start_instance(**node_config))
            if wait:
                try:
                    with timeout(self.startup_timeout, raise_timeout_error):
                        node_up = False
                        while not node_up:
                            self.__update_node_states()
                            node = next(iter([n for n in self.nodes if n.name == node_config['node_name']]), None)
                            if not node:
                                log.error('something went wrong while trying to start %s!', node_config['node_name'])
                                raise NodeNotFound
                            else:
                                log.debug('%s status: %s', node.name, node.state)
                                if node.state != NodeState.RUNNING:
                                    time.sleep(self.polling_interval)
                                else:
                                    node_up = True
                except TimeoutError:
                    node = next(iter([n for n in self.nodes if n.name == node_config['node_name']]), None)
                    if node:
                        log.error('could not initialize node %s, terminating it', node.name)
                        self.remove_by_name(node.name)
                    else:
                        raise NodeNotFound('could not find the node we tried to start, check the console')
        self.__dump()

    def remove(self, node_type, count=1):
        node_index = self.__last_allocated_node_index(node_type)
        for x in range(node_index, node_index - count, -1):
            if self.template == self.name:
                self.remove_by_name('{}-{}{:03}'.format(self.template, node_type, x))
            else:
                self.remove_by_name('{}-{}{:03}'.format(self.name, node_type, x))

    def remove_by_name(self, name):
        self.__update_node_states()
        provider = self.cloud.provider(storage_path=self.storage_path, **dict(self.cloud.options, **self.login.options))
        node = next(iter([n for n in self.nodes if n.name == name]), None)
        if not node:
            log.error('node %s not found as part of the current cluster (%s)', name, self.name)
            return
        log.debug('removing node %s from cluster %s', node.name, self.name)
        provider.stop_instance(node)
        self.nodes.remove(node)
        self.__dump(False)

    def configure(self, extra_args=tuple()):
        local_options = dict(self.setup.options)
        node_types = []
        for node_type, _, _ in self.node_types():
            node_types.append(node_type)
        groups = defaultdict(list)
        for node_type in node_types:
            for group in self.setup.node_groups(node_type):
                groups[node_type].append(group)
        log.debug('going to deploy groups: %s', dict(groups))
        environment_vars = {}
        for group in node_types:
            environment_vars[group] = {}
            for key, value in local_options.items():
                for prefix in ['{}_var_'.format(group), 'global_var_']:
                    if key.startswith(prefix):
                        var = key.replace(prefix, '')
                        log.debug("setting variable %s=%s for node type %s", var, value, group)
                        environment_vars[group][var] = value
                        local_options.pop(key)
        playbook_path = local_options.pop('playbook_path')
        sudo = True
        if self.login.options.get('image_sudo'):
            sudo = self.login.options.get('image_sudo')
        sudo_user = 'root'
        if self.login.options.get('image_user_sudo'):
            sudo_user = self.login.options.get('image_user_sudo')
        provider = self.setup.provider(groups,
                                       playbook_path,
                                       environment_vars,
                                       self.storage_path,
                                       sudo,
                                       sudo_user,
                                       **local_options)
        return provider.setup_cluster(self, extra_args)

    def ssh_node(self):
        ssh_to = None
        if self.options:
            ssh_to = self.options.get('ssh_to')
        if not ssh_to:
            log.info('no ssh_to specified in configuration for cluster %s (%s)', self.name, self.template)
            return None
        for node in sorted(self.nodes, key=lambda n: n.name):
            if ssh_to in node.name:
                return node
        log.warn('no %s found cluster %s active state', ssh_to, self.name)
        return None

    def node_ssh_address_and_port(self, name, key_file=None):
        node = next(iter(n for n in self.nodes if n.name == name), None)
        if not node:
            raise NodeNotFound

        ssh_port = self.ssh_port
        if self.options.get('ssh_port'):
            ssh_port = self.options.get('ssh_port')

        with paramiko.SSHClient() as ssh:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if key_file:
                key_file_path = os.path.expandvars(os.path.expanduser(key_file))
                if os.path.exists(key_file_path):
                    ssh.load_host_keys(key_file_path)

            private_key_file = os.path.expandvars(os.path.expanduser(self.login.options.get('user_key_private')))
            for ip in node.private_ips + node.public_ips:
                log.debug('trying to connect on %s:%s', ip, self.ssh_port)
                try:
                    with timeout(self.startup_timeout, raise_timeout_error):
                        host_started = False
                        while not host_started:
                            try:
                                ssh.connect(ip,
                                            username=self.login.options.get('image_user'),
                                            password=self.login.options.get('image_user_password'),
                                            key_filename=private_key_file,
                                            allow_agent=True,
                                            look_for_keys=True,
                                            timeout=5,
                                            port=ssh_port)
                                try:
                                    if not os.path.exists(self.known_host_file):
                                        open(self.known_host_file, 'a').close()
                                    keys = paramiko.hostkeys.HostKeys(self.known_host_file)
                                    for host, key in ssh.get_host_keys().items():
                                        for t, d in key.items():
                                            keys.add(host, t, d)
                                    keys.save(self.known_host_file)
                                except IOError:
                                    log.warning("Ignoring error saving known_hosts file: %s", self.known_host_file)
                                ssh.close()
                                host_started = True
                            except socket.error as ex:
                                log.debug("Host %s (%s) not reachable, retrying. (%s)", self.name, ip, ex)
                                time.sleep(self.polling_interval)
                        return ip, ssh_port
                except paramiko.SSHException as ex:
                    log.debug("Ignoring error %s while connecting to %s", str(ex), ip)
        return None, None

    def __str__(self):
        ssh_node = self.ssh_node()
        if ssh_node:
            frontend = ssh_node.name
        else:
            frontend = 'unknown'
        result = 'Cluster name:      {}\n'.format(self.name)
        result += 'Cluster template:  {}\n'.format(self.template)
        result += 'Default ssh node:  {}\n\n'.format(frontend)
        if len(self.nodes) > 0:
            for node in sorted(self.nodes, key=lambda n: n.name):
                result += '- {}\n'.format(node.name)
            result += '\nTo login on the frontend node, run the command:\n\n'
            result += 'elasticluster ssh {}\n\n'.format(frontend)
            result += 'To upload or download files to the cluster, use the command:\n\n'
            result += 'elasticluster sftp {}\n'.format(frontend)
        else:
            result += 'Cluster does not appear to be in active state\n'
        return result
