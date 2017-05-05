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

    def __init__(self, subscription_id, key_file, storage_path=None, **config):
        super(AzureCloudProvider, self).__init__(**config)
        self.driver = Azure(subscription_id=subscription_id, key_file=key_file)

    def get_key_pair_fingerprint(self, name):
        pass

    def import_key_from_string(self, name, public_key_material):
        pass

    def list_key_pairs(self):
        pass

    def deallocate_floating_ip(self, node):
        pass

    def allocate_floating_ip(self, node):
        pass

    def list_security_groups(self):
        pass

    def start_instance(self, key_name, public_key_path, private_key_path, security_group, flavor, image_id,
                       image_userdata, username=None, node_name=None, network_ids=None, **kwargs):
        fl, img = self.prepare_instance(key_name, public_key_path, private_key_path, flavor, image_id)
        node = self.driver.create_node(name=node_name,
                                       image=img,
                                       size=fl,
                                       ex_cloud_service_name=AZURE_CLOUD_SERVICE_NAME)
        if self.floating_ip:
            self.allocate_floating_ip(node)
        return node.id
