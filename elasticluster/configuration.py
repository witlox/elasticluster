import os

from six.moves.configparser import ConfigParser

from elasticluster import AnsibleSetupProvider, log
from elasticluster import AwsCloudProvider
from elasticluster import AzureCloudProvider
from elasticluster import GoogleCloudProvider
from elasticluster import OpenStackCloudProvider
from elasticluster.cloud import Cloud
from elasticluster.cluster import Cluster
from elasticluster.exceptions import ConfigurationError
from elasticluster.login import Login
from elasticluster.setup import Setup

CLOUD_PREFIX = 'cloud/'
CLUSTER_PREFIX = 'cluster/'
LOGIN_PREFIX = 'login/'
SETUP_PREFIX = 'setup/'

CLOUD_PROVIDERS = {
    'aws': AwsCloudProvider,
    'azure': AzureCloudProvider,
    'gce': GoogleCloudProvider,
    'openstack': OpenStackCloudProvider,
}

SETUP_PROVIDERS = {
    'ansible': AnsibleSetupProvider,
}

DEFAULT_STORAGE_PATH = "~/.elasticluster/storage"
DEFAULT_STORAGE_TYPE = "yaml"


class Configuration(object):
    storage_path = DEFAULT_STORAGE_PATH
    storage_type = DEFAULT_STORAGE_TYPE

    def __init__(self, config_file_path, storage_path=None, storage_type=None):
        self.parser = ConfigParser()
        self.parser.read(os.path.expandvars(os.path.expanduser(config_file_path)))
        if storage_path:
            self.storage_path = os.path.expandvars(os.path.expanduser(storage_path))
        if storage_type:
            self.storage_type = storage_type

    """
    Parse all running clusters
    """
    @staticmethod
    def parse(config_file_path, storage_path=None, storage_type=None):
        configuration = Configuration(config_file_path, storage_path, storage_type)
        for file_name in [f for f in os.listdir(os.path.expanduser(configuration.storage_path))
                          if f.endswith('.{}'.format(configuration.storage_type))]:
            log.debug('loading cluster configuration file %s (%s)', file_name, configuration.storage_path)
            name = os.path.splitext(os.path.basename(file_name))[0]
            cluster = Cluster(configuration.storage_path, configuration.storage_type, None,
                              name=name,
                              **{'cloud': 'none',
                                 'login': 'none',
                                 'setup': 'none',
                                 'size': 'none',
                                 'image': 'none'})
            if cluster and cluster.template:
                for c in configuration.get_cluster(cluster.template, name):
                    yield c

    """
    Parse all templates
    """
    @staticmethod
    def templates(config_file_path, storage_path=None, storage_type=None):
        configuration = Configuration(config_file_path, storage_path, storage_type)
        templates = {}
        for section in [s for s in configuration.parser.sections() if s.startswith(CLUSTER_PREFIX)]:
            for (key, value) in [kv for kv in configuration.parser.items(section) if 'nodes' in kv[0]]:
                template_key = section[len(CLUSTER_PREFIX):].split('/')[0]
                if template_key not in templates.keys():
                    templates[template_key] = []
                templates[template_key].append((key, value))
        return templates

    """
    Find a specific cluster by name
    """
    @staticmethod
    def find(config_file_path, name, storage_path=None, storage_type=None):
        log.info('searching for cluster %s', name)
        for cluster in Configuration.parse(config_file_path, storage_path, storage_type):
            log.debug('checking cluster %s', cluster.name)
            if cluster.name == name:
                return cluster
        return None

    def get_cluster(self, template, name):
        log.debug('trying to get cluster %s configuration with template %s', name, template)
        group_specific_options = {}
        for go in [s for s in self.parser.sections()
                   if s.startswith(CLUSTER_PREFIX)
                   and template in s[len(CLUSTER_PREFIX):]
                   and len(s) > len(CLUSTER_PREFIX)+len(template)]:
            group_name = go[len(CLUSTER_PREFIX)+len(template)+1:]
            group_specific_options[group_name] = {}
            log.debug('extra group options (%s) detected for %s', group_name, template)
            for k, v in self.parser.items(go):
                group_specific_options[group_name][k] = v
        for cs in [s for s in self.parser.sections()
                   if s.startswith(CLUSTER_PREFIX) and s[len(CLUSTER_PREFIX):] == template]:
            cloud = None
            login = None
            setup = None
            options = {}
            for k, v in self.parser.items(cs):
                if k == 'cloud':
                    cloud = next(self.get_cloud(v), None)
                elif k == 'login':
                    login = next(self.get_login(v), None)
                elif k == 'setup':
                    setup = next(self.get_setup(v), None)
                options[k] = v
            yield Cluster(self.storage_path,
                          self.storage_type,
                          template,
                          name=name,
                          cloud_instance=cloud,
                          login_instance=login,
                          setup_instance=setup,
                          group_specific_options=group_specific_options,
                          **options)

    def get_login(self, name):
        for ls in [s for s in self.parser.sections()
                   if s.startswith(LOGIN_PREFIX) and s[len(LOGIN_PREFIX):] == name]:
            options = {}
            for k, v in self.parser.items(ls):
                options[k] = v
            log.debug('selecting login {}'.format(name))
            yield Login(name, **options)

    def get_cloud(self, name):
        for cs in [s for s in self.parser.sections()
                   if s.startswith(CLOUD_PREFIX) and s[len(CLOUD_PREFIX):] == name]:
            provider = None
            options = {}
            for k, v in self.parser.items(cs):
                if k == 'provider':
                    if v not in CLOUD_PROVIDERS:
                        raise ConfigurationError('Invalid value `{}` for `cloud provider` '
                                                 'in configuration file.'.format(v))
                    provider = CLOUD_PROVIDERS[v]
                else:
                    options[k] = v
            log.debug('selecting cloud {}'.format(name))
            cloud = Cloud(name, provider.rules, **options)
            cloud.provider = provider
            yield cloud

    def get_setup(self, name):
        for ss in [s for s in self.parser.sections()
                   if s.startswith(SETUP_PREFIX) and s[len(SETUP_PREFIX):] == name]:
            provider = None
            options = {}
            for k, v in self.parser.items(ss):
                if k == 'provider':
                    if v not in SETUP_PROVIDERS:
                        raise ConfigurationError('Invalid value `{}` for `setup provider` '
                                                 'in configuration file.'.format(v))
                    provider = SETUP_PROVIDERS[v]
                else:
                    options[k] = v
            log.debug('selecting setup {}'.format(name))
            setup = Setup(name, **options)
            setup.provider = provider
            yield setup
