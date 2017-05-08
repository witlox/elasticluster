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

aws = get_driver(Provider.EC2)


class AwsCloudProvider(CloudProvider):
    rules = {
        Optional("ec2_region", default=os.getenv('AWS_DEFAULT_REGION', '')): nonempty_str,
        Optional("ec2_access_key", default=os.getenv('EC2_ACCESS_KEY', '')): nonempty_str,
        Optional("ec2_secret_key", default=os.getenv('EC2_SECRET_KEY', '')): nonempty_str,
    }

    def __init__(self, **config):
        super(AwsCloudProvider).__init__(**config)
        self.vpc = config.get('vpc')
        self.instance_profile = config.get('instance_profile')
        self.floating_ip = config.get('request_floating_ip')
        self.driver = aws(config.get('access_key'),
                          config.get('secret_key'),
                          region=config.get('region'))

    def deallocate_floating_ip(self, node):
        eips = self.driver.ex_describe_addresses_for_node(node)
        if eips:
            for elastic_ip in eips:
                self.driver.ex_disassociate_address(elastic_ip)
                self.driver.ex_release_address(elastic_ip)

    def allocate_floating_ip(self, node):
        elastic_ip = self.driver.ex_allocate_address()
        self.driver.ex_associate_address_with_node(node, elastic_ip)

    def start_instance(self, **config):
        super(AwsCloudProvider, self).start_instance(**config)
        node = self.start_node({'name': config.get('node_name'),
                                'image': config.get('image'),
                                'size': config.get('flavor'),
                                'ex_userdata': config.get('image_userdata'),
                                'ex_security_groups': config.get('security_groups'),
                                'ex_iamprofile': config.get('iam_profile'),
                                'ex_assign_public_ip': config.get('public_ip')})

        if self.floating_ip:
            self.allocate_floating_ip(node)
        return node.id
