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

from elasticluster import log

# This assumes you we have SSL set up.
import libcloud.security

from elasticluster.validate import nonempty_str, url

libcloud.security.VERIFY_SSL_CERT = True

OpenStack = get_driver(Provider.OPENSTACK)


class OpenStackCloudProvider(CloudProvider):
    rules = {
        Optional('auth_url', default=os.getenv('OS_AUTH_URL', '')): url,
        Optional('username', default=os.getenv('OS_USERNAME', '')): nonempty_str,
        Optional('password', default=os.getenv('OS_PASSWORD', '')): nonempty_str,
        Optional('project_name', default=os.getenv('OS_PROJECT_NAME', os.getenv('OS_TENANT_NAME', ''))): nonempty_str,
    }

    def __init__(self, **config):
        super(OpenStackCloudProvider, self).__init__(**config)
        self.driver = OpenStack(config.get('username'),
                                config.get('password'),
                                ex_force_auth_url=config.get('auth_url').rsplit('/', 1)[0],
                                ex_tenant_name=self.project_name,
                                ex_force_auth_version='2.0_password')

    def import_key_from_file(self, name, public_key):
        self.driver.ex_import_key_pair_from_file(name, public_key)

    def list_key_pairs(self):
        for kp in self.driver.ex_list_keypairs():
            yield kp.name

    def list_security_groups(self):
        for sg in self.driver.ex_list_security_groups():
            yield sg.name

    def resolve_security_group(self, security_group_name):
        for sg in self.driver.ex_list_security_groups():
            if sg.name == security_group_name:
                return sg

    def resolve_network(self, network_id):
        for ne in self.driver.ex_list_networks():
            if ne.id == network_id:
                return ne

    def deallocate_floating_ip(self, node):
        floating = self._attached_floating_ips(node)
        if floating:
            pool = self._get_ip_pool()
            for ip in floating:
                self.driver.ex_detach_floating_ip_from_node(node, ip)
                pool.ex_delete_floating_ip(ip)

    def allocate_floating_ip(self, node):
        pool = self._get_ip_pool()
        if pool:
            fip = pool.ex_create_floating_ip()
            self.driver.ex_attach_floating_ip_to_node(node, fip)
        else:
            log.warn('could not locate default ip pool, assignment of floating IP failed')

    def start_instance(self, **config):
        super(OpenStackCloudProvider, self).start_instance(**config)
        return self.start_node({'name': config.get('node_name'),
                                'image': self.check_image(config.get('image_id')),
                                'size': self.check_flavor(config.get('flavor')),
                                'auth': self.get_auth(),
                                'ex_userdata': config.get('image_userdata'),
                                'ex_security_groups': self._get_security_groups(config),
                                'networks': self._get_networks(config),
                                'ex_keyname': self.key_name})
