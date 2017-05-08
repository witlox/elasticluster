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

    def _get_ip_pool(self):
        return next(iter(self.driver.ex_list_floating_ip_pools()), None)

    def deallocate_floating_ip(self, node):
        pool = self._get_ip_pool()
        if pool:
            for ip in list(set(self.driver.ex_list_floating_ips()) & set(node.public_ips + node.private_ips)):
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
        config = super(OpenStackCloudProvider, self).start_instance(**config)
        config['ex_keyname'] = self.key_name
        node = self.start_node(config)
        if node:
            if config.get('request_floating_ip'):
                self.allocate_floating_ip(node)
        return node
