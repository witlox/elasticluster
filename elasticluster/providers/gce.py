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
from schema import Optional

from elasticluster.providers.cloud_provider import CloudProvider

from libcloud.compute.providers import get_driver
from libcloud.compute.types import Provider

from elasticluster.exceptions import InstanceError
from elasticluster.validate import nonempty_str

ComputeEngine = get_driver(Provider.GCE)

GCE_DEFAULT_ZONE = 'us-central1-a'
GCE_DEFAULT_SERVICE_EMAIL = 'default'
GCE_DEFAULT_SCOPES = ['https://www.googleapis.com/auth/devstorage'
                      '.full_control',
                      'https://www.googleapis.com/auth/compute']


class GoogleCloudProvider(CloudProvider):
    rules = {
        "gce_client_id": nonempty_str,
        "gce_client_secret": nonempty_str,
        "gce_project_id": nonempty_str,
        Optional("zone", default="us-central1-a"): nonempty_str,
        Optional("network", default="default"): nonempty_str,
    }

    def __init__(self, gce_client_id, gce_client_secret, gce_project_id, zone=GCE_DEFAULT_ZONE,
                 network='default', email=GCE_DEFAULT_SERVICE_EMAIL, request_floating_ip=False,
                 noauth_local_webserver=False, storage_path=None):
        self.network = network
        self.email = email
        self.floating_ip = request_floating_ip
        self.project_name = gce_project_id
        self.driver = ComputeEngine(gce_client_id, gce_client_secret, datacenter=zone, project=self.project_name)

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
                       image_userdata, username=None, node_name=None, boot_disk_type='pd-standard',
                       boot_disk_size=10, tags=None, scheduling=None, **kwargs):
        boot_disk_size_gb = int(boot_disk_size)
        if scheduling is None:
            scheduling_option = {}
        elif scheduling == 'preemptible':
            scheduling_option = {
                'preemptible': True
            }
        else:
            raise InstanceError("Unknown scheduling option: '%s'" % scheduling)

        with open(public_key_path, 'r') as f:
            public_key_content = f.read()

        floating = None
        if self.floating_ip:
            floating = 'ephemeral'
        fl, img = self.prepare_instance(key_name, public_key_path, private_key_path, flavor, image_id)
        metadata = {
            'scheduling': scheduling_option,
            'disks': [{
                'autoDelete': 'true',
                'boot': 'true',
                'type': 'PERSISTENT',
                'initializeParams' : {
                    'diskSizeGb': boot_disk_size_gb,
                    }
                }],
            'networkInterfaces': [
                {'accessConfigs': [
                    {'type': 'ONE_TO_ONE_NAT',
                     'name': 'External NAT'
                    }],
                }],
            'serviceAccounts': [
                {'email': self.email,
                 'scopes': GCE_DEFAULT_SCOPES
                }],
            "metadata": {
                "kind": "compute#metadata",
                "items": [
                    {
                        "key": "sshKeys",
                        "value": "%s:%s" % (username, public_key_content)
                    }
                ]
            }
        }
        node = self.driver.create_node(name=node_name,
                                       image=img,
                                       size=fl,
                                       external_ip=floating,
                                       ex_network=self.network,
                                       ex_metadata=metadata)
        return node.id

