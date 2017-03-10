# -*- coding: utf-8 -*-

##
# Copyright 2017 xFlow Research Pvt. Ltd
# This file is part of openmano
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# For those usages not covered by the Apache License, Version 2.0 please
# contact with: saboor.ahmad@xflowresearch.com
##

'''
AWS-connector implements all the methods to interact with AWS using the BOTO client
'''

__author__="Saboor Ahmad, Raja Bilal Saleem"
__date__ ="$09-mar-2017 12:44$"

import vimconn
import json
import yaml
import logging
import netaddr

from httplib import HTTPException
from requests.exceptions import ConnectionError

try:
    import boto
    from boto.vpc import VPCConnection
except:
    exit("Boto not avialable. Try activating your virtualenv OR `pip install boto`")

intr_assossiation_list={}

class vimconnector(vimconn.vimconnector):
    def __init__(self, uuid, name, tenant_id, tenant_name, url, url_admin=None, user=None, passwd=None, log_level=None, config={}):
        '''
        Params:
            uuid - id asigned to this VIM
            name - name assigned to this VIM, can be used for logging
            tenant_id - ID to be used for tenant
            tenant_name - name of tenant to be used VIM tenant to be used
            url_admin - optional, url used for administrative tasks
            user - credentials of the VIM user
            passwd - credentials of the VIM user
            log_level - if must use a different log_level than the general one
            config - dictionary with extra VIM information. This contains a consolidate version of general VIM config at create and particular VIM config at attach
        '''
        vimconn.vimconnector.__init__(self, uuid, name, tenant_id, tenant_name, url, url_admin, user, passwd, log_level, config)
        self.a_creds={}
        if user:
            self.a_creds['aws_access_key_id'] = user
        if passwd:
            self.a_creds['aws_secret_access_key'] = passwd
        if 'region' in config:
            self.region = config.get('region')
        self.vpc_data={}
        self.subnet_data={}
        self.conn=None
        self.conn_vpc=None
        self.logger = logging.getLogger('openmano.vim.aws')
        if log_level:
            self.logger.setLevel(getattr(logging, log_level))

    def __setitem__(self, index, value):
        '''
        Params:
            index - name of value of set
            value - value to set
        '''
        if index=='user':
            self.a_creds['aws_access_key_id'] = value
        elif index=='passwd':
            self.a_creds['aws_secret_access_key'] = value
        elif index=='region':
            self.region = value
        else:
            vimconn.vimconnector.__setitem__(self, index, value)

    def _reload_connection(self):
        '''
        Sets EC2 and VPC connection to work with AWS services
        '''
        try:
            self.conn = boto.ec2.connect_to_region(self.region, aws_access_key_id=self.a_creds['aws_access_key_id'], aws_secret_access_key=self.a_creds['aws_secret_access_key'])
            self.conn_vpc = boto.vpc.connect_to_region(self.region, aws_access_key_id=self.a_creds['aws_access_key_id'], aws_secret_access_key=self.a_creds['aws_secret_access_key'])
        except Exception as e:
            print "Exception Caught at _reload_connection()"
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnConnectionException(type(e).__name__ + ": " + str(e))

    def get_region_list(self):
        '''
        Returns:
            list of regions
        '''
        try:
            self._reload_connection()
            return self.conn.get_all_regions()#aws_access_key_id=self.a_creds['aws_access_key_id'], aws_secret_access_key=self.a_creds['aws_secret_access_key'])
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnConnectionException(type(e).__name__ + ": " + str(e))

    def get_tenant_list(self, filter_dict=()):
        '''
        Params:
            filter_dict - NOT USED
        Returns:
            list of VPCs
        '''
        try:
            self._reload_connection()
            return self.conn_vpc.get_all_vpcs()
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnConnectionException(type(e).__name__ + ": " + str(e))

    def new_tenant(self, tenant_name=None, tenant_description=None):
        '''
        Params
            tenant_name - CIDR block
            tenant_description - supported tenancy options i.e. 'default' or 'dedicated'
        Returns
            vpc.id - ID of VPC created
        '''
        self.logger.debug("Adding a new VPC" )
        try:
            self._reload_connection()
            vpc = self.conn_vpc.create_vpc(tenant_name, tenant_description)

            self.conn_vpc.modify_vpc_attribute(vpc.id, enable_dns_support=True)
            self.conn_vpc.modify_vpc_attribute(vpc.id, enable_dns_hostnames=True)
            gateway = self.conn_vpc.create_internet_gateway()
            self.conn_vpc.attach_internet_gateway(gateway.id, vpc.id)
            route_table = self.conn_vpc.create_route_table(vpc.id)
            self.conn_vpc.create_route(route_table.id, '0.0.0.0/0', gateway.id)
            self.vpc_data[vpc.id]=(gateway.id, route_table.id)
            return vpc.id
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def delete_tenant(self, tenant_id):
        self.logger.debug("Deleting specified VPC")
        try:
            self._reload_connection()
            gateway_id, route_table_id=self.vpc_data.get(tenant_id)
            self.conn_vpc.detach_internet_gateway(gateway_id, tenant_id)
            self.conn_vpc.delete_vpc(tenant_id)
            self.conn_vpc.delete_route(route_table_id, '0.0.0.0/0')
            return tenant_id
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def new_network(self, net_name, net_type=None, ip_profile=None, shared=False, vlan=None):
        '''
        Params
            net_name - ID of VPC, to create subnet
            ip_profile - dictionary
                cidr_block - CIDR block to create subnet
        Returns
        '''
        self.logger.debug("Adding a subnet to VPC")
        try:
            self._reload_connection()
            route_table_id=self.vpc_data.get(net_name)[1]
            subnet = self.conn_vpc.create_subnet(net_name, ip_profile.get('cidr_block'))
            assossiation_id = self.conn_vpc.associate_route_table(route_table_id, subnet.id)
            self.subnet_data[subnet.id]=assossiation_id
            return subnet.id
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def get_network_list(self, filter_dict={}):
        '''
        Params
            filter_dict - dictionary
                subnet_ids - list of subnet IDs
                filters - list of tuple or dictionaries containing filters
        Returns
            net_list - list of subnets
        '''
        self.logger.debug("Getting all subnets from VIM")
        try:
            self._reload_connection()
            net_list = self.conn_vpc.get_all_subnets()
            return str(net_list)
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def get_network(self, net_id):
        self.logger.debug("Getting VPC's subnet from VIM")
        try:
            subnet = self.conn_vpc.get_all_subnets(list(net_id))[0]
            return subnet
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def delete_network(self, net_id):
        '''
        Params
            net_id - ID of subnet to delete
        Returns
            net_id - ID of subnet deleted
        '''
        self.logger.debug("Deleting subnet from VIM")
        try:
            self._reload_connection()
            assossiation_id=self.subnet_data.get(net_id)
            self.conn_vpc.disassociate_route_table(assossiation_id)
            self.conn_vpc.delete_subnet(net_id)
            return net_id
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def refresh_nets_status(self, net_list):
        '''
        Params
            net_list - list of subnet IDs
        Returns
            dict_entry - a dictionary
                Key:    subnet ID
                Value:  info of VM {'status', 'error_msg', 'vim_info'}
        '''
        dict_entry = {}
        try:
            for net in net_list:
                subnet = self.get_network(net_id=net.split(':')[1])
                subnet_dict = {}
                if subnet:
                    if subnet.state == "pending":
                        subnet_dict['status'] = "BUILD"
                    elif subnet.state == "available":
                        subnet_dict['status'] = 'ACTIVE'
                    else:
                        subnet_dict['status'] = 'DOWN'
                    subnet_dict['error_msg'] = ''
                else:
                    subnet_dict['status'] = 'DELETED'
                    subnet_dict['error_msg'] = 'Network not found'
                try:
                    subnet_dict['vim_info'] = yaml.safe_dump(subnet, default_flow_style=True, width=256)
                except yaml.representer.RepresenterError:
                    subnet_dict['vim_info'] = str(net_vim)
                dict_entry[net]=subnet_dict
        except:
            self.logger.debug("Error in refresh_nets_status")
        return dict_entry


    def new_vminstance(self, name=None, description=None, start=None, image_id=None, flavor_id=None, net_list=None, cloud_config=None):
        '''
        Params:
            name - name of key-pair
            image_id - image ID to use to deploy instance
            flavor_id - flavor ID to use to deploy instance
            net_list - list of subnets to assossiate with this VM
                net_id - subnet ID
                elatic_ip - elastic IP to assosiate with the isnatnce
                security_group - sercurity groups to assosiate with the instance
        Returns:
            instance.id - ID of instance created
        '''
        self.logger.debug("Creating a new VM instance")
        try:
            self._reload_connection()
            instance = None

            if not net_list:
                reservation = self.conn.run_instances(
                    image_id,
                    key_name=name,
                    instance_type=flavor_id,
                )
                instance = reservation.instances[0]
            else:
                for index, subnet in enumerate(net_list):
                    net_intr = boto.ec2.networkinterface.NetworkInterfaceSpecification(subnet_id=subnet.get('net_id'),
                                                                        groups=[subnet.get('security_group')],
                                                                        associate_public_ip_address=True)
                    if subnet.get('elastic_ip'):
                        eip = self.conn.allocate_address()
                        self.conn.associate_address(allocation_id=eip.allocation_id, network_interface_id=net_intr.id)

                    if index == 0:
                        reservation = self.conn.run_instances(
                            image_id,
                            key_name=name,
                            instance_type=flavor_id,
                            network_interfaces=boto.ec2.networkinterface.NetworkInterfaceCollection(net_intr)
                        )
                        instance = reservation.instances[0]
                        intr_assossiation_list[instance.id] = [net_intr]
                    else:
                        self.conn.attach_network_interface(NetworkInterfaceId=boto.ec2.networkinterface.NetworkInterfaceCollection(net_intr), InstanceId=instance.id)
                        intr_assossiation_list[instance.id].append(net_intr)
            return instance.id
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def get_vminstance_list(self):
        '''
        Returns:
            instance_list - list of all the instance
        '''
        try:
            self._reload_connection()
            instance_list = self.conn.get_all_instances()
            return instance_list
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def get_vminstance(self, vm_id):
        '''
        Params:
            vm_id - ID of instance to get
        Returns:
            instance - instance required
        '''
        try:
            self._reload_connection()
            instance = self.conn.get_all_instances(list(vm_id))
            return instance[0]
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def delete_vminstance(self, vm_id):
        '''
        Params:
            vm_id - ID of instance to delete
        Returns:
            vm_id - ID of instance deleted
        '''
        try:
            self._reload_connection()
            # self.conn.stop_instance(vm_id)
            self.conn.terminate_instances(vm_id)
            return vm_id
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def refresh_vms_status(self, vm_list):
        '''
        Params
            vm_list - list of instance IDs
        Returns - a dictionary
                vm_id:          #VIM id of this Virtual Machine
                    status:     #Mandatory. Text with one of:
                                #  DELETED (not found at vim)
                                #  VIM_ERROR (Cannot connect to VIM, VIM response error, ...)
                                #  OTHER (Vim reported other status not understood)
                                #  ERROR (VIM indicates an ERROR status)
                                #  ACTIVE, PAUSED, SUSPENDED, INACTIVE (not running),
                                #  CREATING (on building process), ERROR
                                #  ACTIVE:NoMgmtIP (Active but any of its interface has an IP address
                                #
                    error_msg:  #Text with VIM error message, if any. Or the VIM connection ERROR
                    vim_info:   #Text with plain information obtained from vim (yaml.safe_dump)
                    interfaces:
                     -  hypervisor:         #Text with plain information obtained from vim (yaml.safe_dump)
                        subnet_id:          #subnet_id where this interface is connected
                        interfaces:         #interface/port VIM id
        '''
        vm_dict={}
        self.logger.debug("Getting VM instance information from VIM")
        self._reload_connection()
        for vm_id in vm_list:
            vm={}
            try:
                vm_vim = self.conn.get_all_instance_status(list(vm_id))[0]
                if 'status' in vm_vim:
                    vm['status'] = vm_vim['status']
                else:
                    vm['status'] = "other"
                    vm['error_msg'] = "VIM status reported " + vm_vim['status']
                try:
                    vm['vim_info'] = yaml.safe_dump(vm_vim, default_flow_style=True, width=256)
                except yaml.representer.RepresenterError:
                    vm['vim_info'] = str(vm_vim)
                vm["interfaces"] = []
                if vm_vim.get('fault'):
                    vm['error_msg'] = str(vm_vim['fault'])
                try:
                    self._reload_connection()
                    port_list = intr_assossiation_list[vm_id]
                    for port in port_list:
                        interface={}
                        try:
                            interface['hypervisor'] = yaml.safe_dump(port, default_flow_style=True, width=256)
                        except yaml.representer.RepresenterError:
                            interface['hypervisor'] = str(port)
                        interface["subnet_id"] = port["subnet_id"]
                        interface["interfaces"] = port["interfaces"]
                        vm["interfaces"].append(interface)
                except Exception as e:
                    self.logger.error("Error getting vm interface information " + type(e).__name__ + ": "+  str(e))
            except Exception as e:
                self.logger.error("Exception getting vm status: %s", str(e))
                vm['status'] = "DELETED"
                vm['error_msg'] = str(e)
            vm_dict[vm_id] = vm
        return vm_dict

    def action_vminstance(self, vm_id, action_dict):
        '''
        Params:
            vm_id - ID of instance to execute action upon
            action_dict - list of actions
        Returns:
            vm_id - returns ID of current instance
        '''
        self.logger.debug("Action over VM '%s': %s", vm_id, str(action_dict))
        try:
            self._reload_connection()
            if "start" in action_dict:
                self.conn.start_instances(vm_id)
            elif "stop" in action_dict or "stop" in action_dict:
                self.conn.stop_instances(vm_id)
            elif "terminate" in action_dict:
                self.conn.terminate_instances(vm_id)
            elif "reboot" in action_dict:
                self.conn.reboot_instances(vm_id)
            return vm_id
        except Exception as e:
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))


    def get_flavor_id_from_data(self, flavor_dict):
        """
        Params:
            flavor_dict - contains specifications to find out any flavor that matches such specifications
                ram
                vcpus
                disk
                extended
                    numas - assumed to be a boolean True/False
        Returns:
            flavor_id - flavor ID of the flavor that satisfies user's requirements
        """
        try:
            self._reload_connection()
            # numa = flavor_dict.get('extended', {}).get("numas")
            # AWS has instance types 'i2' that is suitable for NUMA
            # details of 'i2' instance type can be found at: https://aws.amazon.com/blogs/aws/amazon-ec2-new-i2-instance-type-available-now/
            for flavor in self.conn.get_all_instance_types():
                if flavor.memory != flavor_dict["ram"]:
                    continue
                if flavor.cores != flavor_dict["vcpus"]:
                    continue
                if flavor.disk != flavor_dict["disk"]:
                    continue
                return flavor.name
            raise vimconn.vimconnNotFoundException("Cannot find any flavor matching specfied requirements '{}'".format(str(flavor_dict)))
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def get_flavor(self, flavor_id):
        '''
        Params:
            flavor_id - flavor ID to retreive
        Returns:
            flavor - boto.ec2.instancetype.InstanceType
        '''
        self.logger.debug("Getting instance type")
        try:
            if flavor_id not in flavor_list:
                print "Instance type not found"
            return flavor_list[flavor_id]
        except Exception as e:
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def new_image(self, image_dict):
        '''
        Params:
            image_dict
                instance - isnatcne ID to get export image from
                name - name of the image user wants to create
                description - description of the image
                no_reboot - specifying , if the instance should be terminated/shutdown before generating image from it
        Returns:
            image_id - image ID of the newly created image
        '''
        try:
            self._reload_connection()
            return self.conn.create_image(image_dict['name'], image_dict['description'])
        except Exception as e:
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def delete_image(self, image_id):
        '''
        Params:
            image_id - image ID of image to delete
        Returns:
            image_id - image ID of deleted image
        '''
        try:
            self._reload_connection()
            self.conn.deregister_image(image_id)
            return image_id
        except Exception as e:
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def get_image_from_id(self, image_id):
        '''
        Params:
            image_id - image ID of image to delete
        Returns:
            image - object of image
        '''
        try:
            self._reload_connection()
            image = self.conn.get_image(image_id)
            return image
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))

    def get_image_list(self, filter_dict={}):
        '''
        Params:
            filter_dict
                image_ids - IDs of images to retrieve
        Returns:
            image_id - image ID of deleted image
        '''
        self.logger.debug("Getting image list from VIM")
        try:
            self._reload_connection()
            images = self.conn.get_all_images(filter_dict.get('image_ids'))

            if len(images)==0:
                return []
            return images
        except Exception as e:
            self.conn=None
            self.conn_vpc=None
            raise vimconn.vimconnException(type(e).__name__ + ": " + str(e))
