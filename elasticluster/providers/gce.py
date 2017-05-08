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

from schema import Optional

from elasticluster.providers.cloud_provider import CloudProvider

from libcloud.compute.providers import get_driver
from libcloud.compute.types import Provider

from elasticluster.validate import nonempty_str

ComputeEngine = get_driver(Provider.GCE)

GCE_DEFAULT_SCOPES = ['https://www.googleapis.com/auth/devstorage.full_control',
                      'https://www.googleapis.com/auth/compute']


class GoogleCloudProvider(CloudProvider):
    rules = {
        "gce_client_id": nonempty_str,
        "gce_client_secret": nonempty_str,
        "gce_project_id": nonempty_str,
        Optional("location", default="us-central1-a"): nonempty_str,
    }

    def __init__(self, **config):
        super(GoogleCloudProvider).__init__(**config)
        self.project_name = config.get('gce_project_id')
        if config.get('gce_client_secret'):
            validator = config.get('gce_client_secret')
        else:
            validator = os.path.expandvars(os.path.expanduser(config.get('key_file')))
        self.driver = ComputeEngine(config.get('gce_client_id'),
                                    validator,
                                    datacenter=config.get('zone'),
                                    project=self.project_name)

    def deallocate_floating_ip(self, node):
        pass

    def allocate_floating_ip(self, node):
        pass

    def start_instance(self, boot_disk_size=10, tags=None, scheduling=None, **config):
        super(GoogleCloudProvider, self).start_instance(**config)
        service_accounts = []
        if config.get('email'):
            for email in config.get('email').split(','):
                service_accounts.append({'email': email.strip(), 'scopes': GCE_DEFAULT_SCOPES})
        node = self.start_node({'name': config.get('node_name'),
                                'image': config.get('image'),
                                'size': config.get('flavor'),
                                'location': config.get('zone'),
                                'external_ip': config.get('external_ip'),
                                'ex_network': config.get('networks'),
                                'ex_tags': config.get('tags'),
                                'ex_boot_disk': config.get('boot_disk'),
                                'ex_disk_type': config.get('disk_type'),
                                'ex_service_accounts': service_accounts})
        return node
