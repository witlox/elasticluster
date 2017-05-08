import logging
from schema import Schema

from elasticluster import log
from elasticluster.utils import update_options

KEY_RENAMES = [('tenant_name', 'project_name')]


class Cloud(object):
    def __init__(self, name, rules, **options):
        self.name = name
        self.options = Schema(rules).validate(update_options(KEY_RENAMES, options))
        if log.very_verbose:
            log.debug('%s options: %s', self.name, dict(self.options))

    def __get_provider(self):
        return self.__provider

    def __set_provider(self, value):
        self.__provider = value

    provider = property(__get_provider, __set_provider)
