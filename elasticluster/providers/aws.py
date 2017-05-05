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

    def __init__(self, region, access_key=None, secret_key=None, vpc=None, request_floating_ip=False,
                 instance_profile=None, storage_path=None):
        self.vpc = vpc
        self.instance_profile = instance_profile
        self.floating_ip = request_floating_ip
        self.driver = aws(access_key, secret_key, region=region)

    def get_key_pair_fingerprint(self, name):
        return self.driver.ex_describe_keypair(name)['keyFingerprint']

    def import_key_from_string(self, name, public_key_material):
        self.driver.ex_import_keypair_from_string(name, public_key_material)

    def list_key_pairs(self):
        self.driver.ex_describe_all_keypairs()

    def deallocate_floating_ip(self, node):
        eips = self.driver.ex_describe_addresses_for_node(node)
        if eips:
            for elastic_ip in eips:
                self.driver.ex_disassociate_address(elastic_ip)
                self.driver.ex_release_address(elastic_ip)

    def allocate_floating_ip(self, node):
        elastic_ip = self.driver.ex_allocate_address()
        self.driver.ex_associate_address_with_node(node, elastic_ip)

    def list_security_groups(self):
        pass

    def start_instance(self, key_name, public_key_path, private_key_path, security_group, flavor, image_id,
                       image_userdata, username=None, node_name=None, network_ids=None, **kwargs):
        fl, img = self.prepare_instance(key_name, public_key_path, private_key_path, flavor, image_id)
        sgs = self.security_groups(security_group)
        node = self.driver.create_node(name=node_name,
                                       image=img,
                                       size=fl,
                                       ex_keyname=key_name,
                                       ex_security_groups=sgs,
                                       ex_userdata=image_userdata,
                                       ex_iamprofile=self.instance_profile,
                                       ex_assign_public_ip=True)
        if self.floating_ip:
            self.allocate_floating_ip(node)
        return node.id
