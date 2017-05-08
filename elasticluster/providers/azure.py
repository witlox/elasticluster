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
import os

from elasticluster.providers.cloud_provider import CloudProvider

from libcloud.compute.providers import get_driver
from libcloud.compute.types import Provider

from elasticluster.validate import nonempty_str

Azure = get_driver(Provider.AZURE)

AZURE_CLOUD_SERVICE_NAME = 'Elasticluster'


class AzureCloudProvider(CloudProvider):
    rules = {
        'subscription_id': nonempty_str,
        'certificate': nonempty_str,
    }

    def __init__(self, **config):
        super(AzureCloudProvider, self).__init__(**config)
        self.driver = Azure(subscription_id=config.get('subscription_id'),
                            key_file=os.path.expandvars(os.path.expanduser(config.get('key_file'))))

    def deallocate_floating_ip(self, node):
        pass

    def allocate_floating_ip(self, node):
        pass

    def start_instance(self, boot_disk_size=10, tags=None, scheduling=None, **config):
        super(AzureCloudProvider, self).start_instance(**config)
        node = self.start_node({'name': config.get('node_name'),
                                'image': config.get('image'),
                                'size': config.get('flavor'),
                                'ex_cloud_service_name': AZURE_CLOUD_SERVICE_NAME})
        return node
