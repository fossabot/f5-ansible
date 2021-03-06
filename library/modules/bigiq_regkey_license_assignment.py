#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2017, F5 Networks Inc.
# GNU General Public License v3.0 (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = r'''
---
module: bigiq_regkey_license_assignment
short_description: Manage regkey license assignment on BIG-IPs from a BIG-IQ.
description:
  - Manages the assignment of regkey licenses on a BIG-IQ. Assignment means that
    the license is assigned to a BIG-IP, or, it needs to be assigned to a BIG-IP.
    Additionally, this module supported revoking the assignments from BIG-IP devices.
version_added: 2.6
options:
  pool:
    description:
      - The registration key pool to use.
    required: True
  key:
    description:
      - The registration key that you want to assign from the pool.
    required: True
  device:
    description:
      - When C(managed) is C(no), specifies the address, or hostname, where the BIG-IQ
        can reach the remote device to register.
      - When (Cmanaged) is C(yes), specifies the managed device, or device UUID, that
        you want to register.
      - If C(managed) is C(yes), it is very important that you do not have more than
        one device with the same name. BIG-IQ internally recognizes devices by their ID,
        and therefore, this module's cannot guarantee that the correct device will be
        registered. The device returned is the device that will be used.
  managed:
    description:
      - Whether the specified device is a managed or un-managed device.
      - When C(state) is C(present), this parameter is required.
    type: bool
  device_port:
    description:
      - Specifies the port of the remote device to connect to.
      - If this parameter is not specified, the default of C(443) will be used.
    default: 443
  device_username:
    description:
      - The username used to connect to the remote device.
      - This username should be one that has sufficient privileges on the remote device
        to do licensing. Usually this is the C(Administrator) role.
      - When C(managed) is C(no), this parameter is required.
  device_password:
    description:
      - The password of the C(device_username).
      - When C(managed) is C(no), this parameter is required.
  state:
    description:
      - When C(present), ensures that the device is assigned the specified license.
      - When C(absent), ensures the license is revokes from the remote device and freed
        on the BIG-IQ.
    default: present
    choices:
      - present
      - absent
extends_documentation_fragment: f5
author:
  - Tim Rupp (@caphrim007)
'''

EXAMPLES = r'''
- name: Register an unmanaged device
  bigiq_regkey_license_assignment:
    pool: my-regkey-pool
    key: XXXX-XXXX-XXXX-XXXX-XXXX
    device: 1.1.1.1
    managed: no
    device_username: admin
    device_password: secret
    password: secret
    server: lb.mydomain.com
    state: present
    user: admin
  delegate_to: localhost

- name: Register an managed device, by name
  bigiq_regkey_license_assignment:
    pool: my-regkey-pool
    key: XXXX-XXXX-XXXX-XXXX-XXXX
    device: bigi1.foo.com
    managed: yes
    password: secret
    server: lb.mydomain.com
    state: present
    user: admin
  delegate_to: localhost

- name: Register an managed device, by UUID
  bigiq_regkey_license_assignment:
    pool: my-regkey-pool
    key: XXXX-XXXX-XXXX-XXXX-XXXX
    device: 7141a063-7cf8-423f-9829-9d40599fa3e0
    managed: yes
    password: secret
    server: lb.mydomain.com
    state: present
    user: admin
  delegate_to: localhost
'''

RETURN = r'''
param1:
  description: The new param1 value of the resource.
  returned: changed
  type: bool
  sample: true
param2:
  description: The new param2 value of the resource.
  returned: changed
  type: string
  sample: Foo is bar
'''

import re

from ansible.module_utils.basic import AnsibleModule

try:
    from library.module_utils.network.f5.bigiq import F5RestClient
    from library.module_utils.network.f5.common import F5ModuleError
    from library.module_utils.network.f5.common import AnsibleF5Parameters
    from library.module_utils.network.f5.common import f5_argument_spec
    from library.module_utils.network.f5.common import exit_json
    from library.module_utils.network.f5.common import fail_json
except ImportError:
    from ansible.module_utils.network.f5.bigiq import F5RestClient
    from ansible.module_utils.network.f5.common import F5ModuleError
    from ansible.module_utils.network.f5.common import AnsibleF5Parameters
    from ansible.module_utils.network.f5.common import f5_argument_spec
    from ansible.module_utils.network.f5.common import exit_json
    from ansible.module_utils.network.f5.common import fail_json
try:
    import netaddr
    HAS_NETADDR = True
except ImportError:
    HAS_NETADDR = False


class Parameters(AnsibleF5Parameters):
    api_map = {
        'deviceReference': 'device_reference',
        'deviceAddress': 'device_address',
        'username': 'device_username',
        'password': 'device_password',
        'httpsPort': 'device_port'
    }

    api_attributes = [
        'deviceReference', 'deviceAddress', 'username', 'password', 'httpsPort' 'managed'
    ]

    returnables = [
        'device_address', 'httpsPort'
    ]

    updatables = [

    ]

    def to_return(self):
        result = {}
        try:
            for returnable in self.returnables:
                result[returnable] = getattr(self, returnable)
            result = self._filter_params(result)
        except Exception:
            pass
        return result


class ApiParameters(Parameters):
    pass


class ModuleParameters(Parameters):
    @property
    def device_port(self):
        if self._values['device_port'] is None:
            return None
        return int(self._values['device_port'])

    @property
    def device_is_address(self):
        try:
            netaddr.IPAddress(self.device)
            return True
        except (ValueError, netaddr.core.AddrFormatError):
            return False

    @property
    def device_is_id(self):
        pattern = r'[A-Za-z0-9]{8}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{12}'
        if re.match(pattern, self.device):
            return True
        return False

    @property
    def device_is_name(self):
        if not self.device_is_address and not self.device_is_id:
            return True
        return False

    @property
    def device_reference(self):
        uri = "/mgmt/shared/resolver/device-groups/cm-bigip-allBigIpDevices/devices/?$filter=(address eq '{0}'&$top=1".format(self.device)
        resp = self.client.api.get(uri)
        if resp.status_code == 200 and resp.json()['totalItems'] == 0:
            raise F5ModuleError(
                "No device with the specified address was found."
            )
        id = resp.json()['items'][0]['uuid']
        return dict(
            link='https://localhost/mgmt/shared/resolver/device-groups/cm-bigip-allBigIpDevices/devices/{0}'.format(id)
        )

    @property
    def pool_id(self):
        filter = "(name eq '{0}')".format(self.pool)
        uri = '/mgmt/cm/device/licensing/pool/regkey/licenses?$filter={0}&$top=1'.format(filter)
        resp = self.client.api.get(uri)
        if resp.status_code == 200 and resp.json()['totalItems'] == 0:
            raise F5ModuleError(
                "No pool with the specified name was found."
            )
        return resp.json()['items'][0]['id']

    @property
    def member_id(self):
        filter = "(kind eq 'cm:device:licensing:pool:regkey:licenses:regkeypoollicensestate')"
        if self.device_is_address:
            # This range lookup
            filter += " and (deviceAddress eq '{0}...{0}')".format(self.device)
        elif self.device_is_name:
            filter += " and (deviceName eq '{0}')".format(self.device)
        elif self.device_is_id:
            filter += " and (deviceMachineId eq '{0}')".format(self.device)
        else:
            raise F5ModuleError(
                "Unknown device format '{0}'".format(self.device)
            )
        uri = '/mgmt/shared/index/config?$filter={0}'.format(filter)
        resp = self.client.api.get(uri)
        if resp.status_code == 200 and resp.json()['totalItems'] == 0:
            return None
        result = resp.json()['items'][0]['id']
        return result


class Changes(Parameters):
    pass


class UsableChanges(Changes):
    @property
    def device_port(self):
        if self._values['managed']:
            return None
        return self._values['device_port']

    @property
    def device_username(self):
        if self._values['managed']:
            return None
        return self._values['device_username']

    @property
    def device_password(self):
        if self._values['managed']:
            return None
        return self._values['device_password']

    @property
    def device_reference(self):
        if not self._values['managed']:
            return None
        return self._values['device_reference']

    @property
    def managed(self):
        return None


class ReportableChanges(Changes):
    pass


class Difference(object):
    def __init__(self, want, have=None):
        self.want = want
        self.have = have

    def compare(self, param):
        try:
            result = getattr(self, param)
            return result
        except AttributeError:
            return self.__default(param)

    def __default(self, param):
        attr1 = getattr(self.want, param)
        try:
            attr2 = getattr(self.have, param)
            if attr1 != attr2:
                return attr1
        except AttributeError:
            return attr1


class ModuleManager(object):
    def __init__(self, *args, **kwargs):
        self.module = kwargs.get('module', None)
        self.client = kwargs.get('client', None)
        self.want = ModuleParameters(params=self.module.params, client=self.client)
        self.have = ApiParameters()
        self.changes = UsableChanges()

    def _set_changed_options(self):
        changed = {}
        for key in Parameters.returnables:
            if getattr(self.want, key) is not None:
                changed[key] = getattr(self.want, key)
        if changed:
            self.changes = UsableChanges(params=changed)

    def _update_changed_options(self):
        diff = Difference(self.want, self.have)
        updatables = Parameters.updatables
        changed = dict()
        for k in updatables:
            change = diff.compare(k)
            if change is None:
                continue
            else:
                if isinstance(change, dict):
                    changed.update(change)
                else:
                    changed[k] = change
        if changed:
            self.changes = UsableChanges(params=changed)
            return True
        return False

    def should_update(self):
        result = self._update_changed_options()
        if result:
            return True
        return False

    def exec_module(self):
        changed = False
        result = dict()
        state = self.want.state

        if state == "present":
            changed = self.present()
        elif state == "absent":
            changed = self.absent()

        reportable = ReportableChanges(params=self.changes.to_return())
        changes = reportable.to_return()
        result.update(**changes)
        result.update(dict(changed=changed))
        self._announce_deprecations(result)
        self._append_debug_output(result)
        return result

    def _announce_deprecations(self, result):
        warnings = result.pop('__warnings', [])
        for warning in warnings:
            self.module.deprecate(
                msg=warning['msg'],
                version=warning['version']
            )

    def _append_debug_output(self, result):
        if not self.module._debug:
            return
        result['__f5debug__'] = self.client.debug_output

    def present(self):
        if self.exists():
            return False
        else:
            return self.create()

    def exists(self):
        if self.want.member_id is None:
            return False
        uri = '/mgmt/cm/device/licensing/pool/regkey/licenses/{0}/offerings/{1}/members/{2}'.format(
            self.want.pool_id, self.want.key, self.want.member_id
        )
        resp = self.client.api.get(uri)
        if resp.status_code == 200:
            return True
        return False

    def remove(self):
        if self.module.check_mode:
            return True
        self.remove_from_device()
        if self.exists():
            raise F5ModuleError("Failed to delete the resource.")
        return True

    def create(self):
        self._set_changed_options()
        if self.module.check_mode:
            return True
        self.create_on_device()
        return True

    def create_on_device(self):
        params = self.want.api_params()
        uri = '/mgmt/cm/device/licensing/pool/regkey/licenses/{0}/offerings/{1}/members/'.format(self.want.pool_id, self.want.key)
        self.client.api.post(uri, data=json.dumps(params))

    def absent(self):
        if self.exists():
            return self.remove()
        return False

    def remove_from_device(self):
        uri = '/mgmt/cm/device/licensing/pool/regkey/licenses/{0}/offerings/{1}/members/{2}'.format(
            self.want.pool_id, self.want.key, self.want.member_id
        )
        self.client.api.delete(uri)


class ArgumentSpec(object):
    def __init__(self):
        self.supports_check_mode = True
        argument_spec = dict(
            pool=dict(required=True),
            key=dict(required=True),
            device=dict(required=True),
            managed=dict(type='bool'),
            device_port=dict(type='int', default=443),
            device_username=dict(),
            device_password=dict(),
            state=dict(default='present', choices=['absent', 'present'])
        )
        self.argument_spec = {}
        self.argument_spec.update(f5_argument_spec)
        self.argument_spec.update(argument_spec)
        self.required_if = [
            ['state', 'present', ['key', 'managed']],
            ['managed', False, ['device', 'device_username', 'device_password']],
            ['managed', True, ['device']]
        ]


def main():
    spec = ArgumentSpec()

    module = AnsibleModule(
        argument_spec=spec.argument_spec,
        supports_check_mode=spec.supports_check_mode,
        required_if=spec.required_if
    )
    if not HAS_NETADDR:
        module.fail_json(msg="The python netaddr module is required")

    try:
        client = F5RestClient(module=module)
        mm = ModuleManager(module=module, client=client)
        results = mm.exec_module()
        exit_json(module, results, client)
    except F5ModuleError as ex:
        fail_json(module, ex, client)


if __name__ == '__main__':
    main()
