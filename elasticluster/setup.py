import os

import logging
from pkg_resources import resource_filename
from schema import Optional, Schema

from elasticluster import log
from elasticluster.utils import key_warn, update_options
from elasticluster.validate import executable_file, readable_file

RENAMED_NODE_GROUPS = {
    # old name            ->  new name
    'gluster_client':         'glusterfs_client',
    'gluster_data':           'glusterfs_server',
    'gridengine_clients':     'gridengine_worker',
    'slurm_clients':          'slurm_worker',
    'slurm_workers':          'slurm_worker',
}

KEY_RENAMES = [('ssh_pipelining', 'ansible_ssh_pipelining')]


class Setup(object):
    rules = {Optional('provider', default='ansible'): str,
             Optional("playbook_path", default=os.path.join(resource_filename('elasticluster', 'share/playbooks'), 'site.yml')): readable_file,
             Optional("ansible_command"): executable_file,
             Optional("ansible_extra_args"): str,
             # allow other keys w/out restrictions
             Optional(str): str}

    def __init__(self, name, **kwargs):
        self.name = name
        self.options = update_options(KEY_RENAMES, Schema(self.rules).validate(kwargs))
        updated_options = {}
        for k, v in self.options.items():
            if '_groups' in k and k.split('_groups')[0] in [rng for rng in RENAMED_NODE_GROUPS.keys()]:
                new_key = RENAMED_NODE_GROUPS[k.split('_groups')[0]]
                key_warn(k, new_key)
                updated_options['{}_groups'.format(new_key)] = v
            else:
                updated_options[k] = v
        self.options = updated_options
        if log.very_verbose:
            log.debug('%s options: %s', self.name, dict(self.options))

    def __get_provider(self):
        return self.__provider

    def __set_provider(self, value):
        self.__provider = value

    provider = property(__get_provider, __set_provider)

    def node_groups(self, node_type):
        for v in [v for k, v in self.options.items() if '_groups' in k and node_type in k]:
            for g in v.split(','):
                yield g.strip()
