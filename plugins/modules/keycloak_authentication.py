#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2019, INSPQ <philippe.gauthier@inspq.qc.ca>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = '''
---
module: keycloak_authentication

short_description: Configure authentication in Keycloak

description:
    - This module actually can only make a copy of an existing authentication flow, add an execution to it and configure it.
    - It can also delete the flow.

version_added: "3.3.0"

options:
    realm:
        description:
            - The name of the realm in which is the authentication.
        required: true
        type: str
    alias:
        description:
            - Alias for the authentication flow.
        required: true
        type: str
    description:
        description:
            - Description of the flow.
        type: str
    providerId:
        description:
            - C(providerId) for the new flow when not copied from an existing flow.
        type: str
    copyFrom:
        description:
            - C(flowAlias) of the authentication flow to use for the copy.
        type: str
    authenticationExecutions:
        description:
            - Configuration structure for the executions.
        type: list
        elements: dict
        suboptions:
            providerId:
                description:
                    - C(providerID) for the new flow when not copied from an existing flow.
                type: str
            displayName:
                description:
                    - Name of the execution or subflow to create or update.
                type: str
            requirement:
                description:
                    - Control status of the subflow or execution.
                choices: [ "REQUIRED", "ALTERNATIVE", "DISABLED", "CONDITIONAL" ]
                type: str
            flowAlias:
                description:
                    - Alias of parent flow.
                type: str
            authenticationConfig:
                description:
                    - Describe the config of the authentication.
                type: dict
            index:
                description:
                    - Priority order of the execution.
                type: int
    state:
        description:
            - Control if the authentication flow must exists or not.
        choices: [ "present", "absent" ]
        default: present
        type: str
    force:
        type: bool
        default: false
        description:
            - If C(true), allows to remove the authentication flow and recreate it.

extends_documentation_fragment:
- community.general.keycloak

author:
    - Philippe Gauthier (@elfelip)
    - Gaëtan Daubresse (@Gaetan2907)
'''

EXAMPLES = '''
    - name: Create an authentication flow from first broker login and add an execution to it.
      community.general.keycloak_authentication:
        auth_keycloak_url: http://localhost:8080/auth
        auth_realm: master
        auth_username: admin
        auth_password: password
        realm: master
        alias: "Copy of first broker login"
        copyFrom: "first broker login"
        authenticationExecutions:
          - providerId: "test-execution1"
            requirement: "REQUIRED"
            authenticationConfig:
              alias: "test.execution1.property"
              config:
                test1.property: "value"
          - providerId: "test-execution2"
            requirement: "REQUIRED"
            authenticationConfig:
              alias: "test.execution2.property"
              config:
                test2.property: "value"
        state: present

    - name: Re-create the authentication flow
      community.general.keycloak_authentication:
        auth_keycloak_url: http://localhost:8080/auth
        auth_realm: master
        auth_username: admin
        auth_password: password
        realm: master
        alias: "Copy of first broker login"
        copyFrom: "first broker login"
        authenticationExecutions:
          - providerId: "test-provisioning"
            requirement: "REQUIRED"
            authenticationConfig:
              alias: "test.provisioning.property"
              config:
                test.provisioning.property: "value"
        state: present
        force: true

    - name: Create an authentication flow with subflow containing an execution.
      community.general.keycloak_authentication:
        auth_keycloak_url: http://localhost:8080/auth
        auth_realm: master
        auth_username: admin
        auth_password: password
        realm: master
        alias: "Copy of first broker login"
        copyFrom: "first broker login"
        authenticationExecutions:
          - providerId: "test-execution1"
            requirement: "REQUIRED"
          - displayName: "New Subflow"
            requirement: "REQUIRED"
          - providerId: "auth-cookie"
            requirement: "REQUIRED"
            flowAlias: "New Sublow"
        state: present

    - name: Remove authentication.
      community.general.keycloak_authentication:
        auth_keycloak_url: http://localhost:8080/auth
        auth_realm: master
        auth_username: admin
        auth_password: password
        realm: master
        alias: "Copy of first broker login"
        state: absent
'''

RETURN = '''
msg:
    description: Message as to what action was taken.
    returned: always
    type: str

end_state:
    description: Representation of the authentication after module execution.
    returned: on success
    type: dict
    sample: {
      "alias": "Copy of first broker login",
      "authenticationExecutions": [
        {
          "alias": "review profile config",
          "authenticationConfig": {
            "alias": "review profile config",
            "config": { "update.profile.on.first.login": "missing" },
            "id": "6f09e4fb-aad4-496a-b873-7fa9779df6d7"
          },
          "configurable": true,
          "displayName": "Review Profile",
          "id": "8f77dab8-2008-416f-989e-88b09ccf0b4c",
          "index": 0,
          "level": 0,
          "providerId": "idp-review-profile",
          "requirement": "REQUIRED",
          "requirementChoices": [ "REQUIRED", "ALTERNATIVE", "DISABLED" ]
        }
      ],
      "builtIn": false,
      "description": "Actions taken after first broker login with identity provider account, which is not yet linked to any Keycloak account",
      "id": "bc228863-5887-4297-b898-4d988f8eaa5c",
      "providerId": "basic-flow",
      "topLevel": true
    }
'''

from ansible_collections.community.general.plugins.module_utils.identity.keycloak.keycloak \
    import KeycloakAPI, camel, keycloak_argument_spec, get_token, KeycloakError, is_struct_included
from ansible.module_utils.basic import AnsibleModule

def find_exec_in_executions(searched_exec, executions):
    """
    Search if exec is contained in the executions.
    :param searched_exec: Execution to search for.
    :param executions: List of executions.
    :return: Index of the execution, -1 if not found..
    """
    for i, existing_exec in enumerate(executions, start=0):
        if ("providerId" in existing_exec and "providerId" in searched_exec and
                existing_exec["providerId"] == searched_exec["providerId"] or
                "displayName" in existing_exec and "displayName" in searched_exec and
                existing_exec["displayName"] == searched_exec["displayName"]) and existing_exec["level"] == searched_exec["level"]:
            return i
    return -1

def get_identifier(execution):
    if execution["providerId"] is not None:
        return execution["providerId"]
    elif execution["displayName"] is not None:
        return execution["displayName"]
    else:
        raise Exception("could not find any name for execution {exec}".format(execution))
        
def create_authentication_execution(kc, config, new_exec, flow_alias_parent, isFlow, realm='master'):
    def hasSameName(other_exec):
        if "providerId" in other_exec and "providerId" in new_exec:
            return other_exec["providerId"] == new_exec["providerId"]
        elif "displayName" in other_exec and "displayName" in new_exec:
            return other_exec["displayName"] == new_exec["displayName"]
            
    updated_exec = {}
        
    # Add authentication execution (or subflow) and returns its id (given by keycloak)
    if isFlow:
        kc.create_subflow(new_exec["displayName"], flow_alias_parent, realm=realm)
    else:
        for key in new_exec: 
            if key != "flowAlias" and key != "authenticationConfig":
                updated_exec[key] = new_exec[key]
        #raise Exception(updated_exec)
        kc.create_execution(updated_exec, flowAlias=flow_alias_parent, realm=realm)
    return list(filter(hasSameName, kc.get_executions_representation(config, realm=realm)))[0]
                    
def update_authentication_execution(kc, flow_alias_parent, new_exec, realm):
    updated_exec = {}
    for key in new_exec:
        # Prepare updated execution. Configuration has been updated already.
        if key != "flowAlias" and key != "authenticationConfig":
            updated_exec[key] = new_exec[key]
    if new_exec["requirement"] is not None:
        kc.update_authentication_executions(flow_alias_parent, updated_exec, realm=realm)
        

def add_error_line(err_msg_lines, err_msg, flow, exec_name, subflow = None, expected = None, actual = None):
    err_msg_lines["lines"] += ["Flow {flow}{subflow}, Execution: {exec_name}: {err_msg} {expected}{actual}.".format(\
                        flow=flow, subflow=", subflow " + subflow if subflow is not None else "", err_msg=err_msg.capitalize(),\
                        exec_name=exec_name, \
                        expected=" (Expected : " + str(expected) if expected is not None else "",\
                        actual=", Actual : " + str(actual) if actual is not None else "")]

def create_or_update_executions(kc, config, check_mode, realm='master'):
    """
    Create or update executions for an authentication flow.
    :param kc: Keycloak API access.
    :param config: Representation of the authentication flow including it's executions.
    :param realm: Realm
    :return: tuple (changed, dict(before, after)
        WHERE
        bool changed indicates if changes have been made
        dict(str, str) shows state before and after creation/update
    """
    try:
        changed = False
        after = ""
        before = ""
        err_msg = {"lines":[]}
        
        if "authenticationExecutions" in config:
            # Get existing executions on the Keycloak server for this alias
            existing_executions = kc.get_executions_representation(config, realm=realm)
            levels = {}
            for new_exec_index, new_exec in enumerate(config["authenticationExecutions"], start=0) if config["authenticationExecutions"] is not None else []:
                if new_exec["index"] is not None:
                    new_exec_index = new_exec["index"]
                # Get flowalias parent if given
                if new_exec["flowAlias"] is not None:
                    flow_alias_parent = new_exec["flowAlias"]                        
                else:
                    flow_alias_parent = config["alias"]

                # Register the level for this execution: parent (sub-) flow's level + 1 if execution has a parent (sub-) flow, otherwise 0
                levels.update({get_identifier(new_exec) : levels[new_exec["flowAlias"]] + 1 if new_exec["flowAlias"] is not None else 0})
                new_exec["level"] = levels[get_identifier(new_exec)]
                
                # Check if there exists an execution with same name/providerID, at the same level as new execution
                exec_index = find_exec_in_executions(new_exec, existing_executions)
                if exec_index != -1: 
                    # There exists an execution of same name/providerID at same level.
                    # Remove key that doesn't need to be compared with existing_exec
                    exclude_key = ["authenticationConfig", "flowAlias"]
                    for index_key, key in enumerate(new_exec, start=0):
                        if new_exec[key] is None:
                            exclude_key.append(key)
                    # Compare the executions to see if it need changes
                    exec_need_changes = False
                    if not is_struct_included(new_exec, existing_executions[exec_index], exclude_key) or exec_index != new_exec_index:
                        exec_need_changes = True
                        before += str(existing_executions[exec_index])
                    existing_exec = existing_executions[exec_index]
                    new_exec["id"] = existing_exec["id"]
                    config_changed = False
                    #Determine if config is different
                    if new_exec["authenticationConfig"] is not None:
                        for key in new_exec["authenticationConfig"]:
                            config_changed |= new_exec["authenticationConfig"][key] is not None and\
                                "authenticationConfig" in existing_exec and\
                                new_exec["authenticationConfig"][key] != existing_exec["authenticationConfig"][key]
                        if config_changed:
                            before += str(existing_exec)
                            if not check_mode:
                                kc.add_authenticationConfig_to_execution(new_exec["id"], new_exec["authenticationConfig"], realm=realm)
                            after += str(new_exec)
                            changed = True
                            add_error_line(err_msg_lines=err_msg, err_msg= "wrong config", flow = config["alias"], exec_name=get_identifier(new_exec), \
                            expected = str(new_exec["authenticationConfig"]), actual = str(existing_exec["authenticationConfig"]))
                    if exec_need_changes:
                        changed = True
                        if not check_mode:
                            update_authentication_execution(kc, flow_alias_parent, new_exec, check_mode, realm)
                        add_error_line(err_msg_lines=err_msg, err_msg="wrong requirement", flow=config["alias"], exec_name=get_identifier(new_exec),\
                        expected = new_exec["requirement"], actual = existing_exec["requirement"])
                        after = str(new_exec)
                    if exec_index != new_exec_index:
                        changed = True
                        if not check_mode:
                            kc.change_execution_priority(new_exec["id"], exec_index - new_exec_index, realm=realm)
                        add_error_line(err_msg_lines=err_msg, err_msg="wrong index", flow=config["alias"], exec_name=get_identifier(new_exec),\
                        expected = new_exec_index, actual = exec_index)
                        
                    existing_executions[exec_index].clear()
                elif new_exec["providerId"] is not None or new_exec["displayName"] is not None :
                    isFlow = new_exec["displayName"] is not None and new_exec["providerId"] is None
                    if isFlow and new_exec_index < len(existing_executions) and existing_executions[new_exec_index]["displayName"] is not None:
                        # A subflow already exists at this index, but wasn't found because it has the wrong name
                        id_to_update = existing_executions[new_exec_index]["id"]
                        new_exec["id"] = id_to_update
                        if not check_mode:
                            update_authentication_execution(kc, flow_alias_parent, new_exec, check_mode, realm)
                        add_error_line(err_msg_lines=err_msg, err_msg="wrong flow name",flow=config["alias"],\
                            exec_name = get_identifier(new_exec), \
                            expected = get_identifier(new_exec), \
                            actual = existing_executions[new_exec_index]["displayName"])
                        existing_executions[new_exec_index].clear()
                    elif not check_mode:
                        created = create_authentication_execution(kc, config, new_exec, flow_alias_parent, isFlow, realm)
                        new_exec["id"] = created["id"]
                        update_authentication_execution(kc, flow_alias_parent, new_exec, check_mode, realm)
                        kc.add_authenticationConfig_to_execution(new_exec["id"], new_exec["authenticationConfig"], realm=realm)

                    changed = True
                    after += str(new_exec) + '\n'
                    err_msg["lines"] += ["Flow {flow} is missing execution {exec_name}{subflow}".format(flow=config["alias"],\
                        exec_name=get_identifier(new_exec), \
                        subflow = (" in subflow " + new_exec["flowAlias"]) if new_exec["flowAlias"] is not None else "")]
            
            # Remove extra executions if any
            for existing_exec in existing_executions:
                if existing_exec != {} :
                    changed = True
                    before += "{existing_exec}\n".format(existing_exec=existing_exec)
                    err_msg["lines"] += ["Flow {flow} has extra execution {exec_name} at depth level {level}".format(flow=config["alias"], exec_name=existing_exec["displayName"], level=existing_exec["level"])]
                    if not check_mode:
                        kc.delete_authentication_execution(existing_exec["id"], realm=realm)
        return changed, dict(before=before, after=after), err_msg

    except Exception as e:
        kc.module.fail_json(msg='Could not create or update executions for authentication flow %s in realm %s: %s'
                            % (config["alias"], realm, str(e)))

def main():
    """
    Module execution

    :return:
    """
    argument_spec = keycloak_argument_spec()

    meta_args = dict(
        realm=dict(type='str', required=True),
        alias=dict(type='str', required=True),
        providerId=dict(type='str'),
        description=dict(type='str'),
        copyFrom=dict(type='str'),
        authenticationExecutions=dict(type='list', elements='dict',
                                      options=dict(
                                          providerId=dict(type='str'),
                                          displayName=dict(type='str'),
                                          requirement=dict(choices=["REQUIRED", "ALTERNATIVE", "DISABLED", "CONDITIONAL"], type='str'),
                                          flowAlias=dict(type='str'),
                                          authenticationConfig=dict(type='dict'),
                                          index=dict(type='int'),
                                      )),
        state=dict(choices=["absent", "present", "exact"], default='present'),
        force=dict(type='bool', default=False),
    )

    argument_spec.update(meta_args)

    module = AnsibleModule(argument_spec=argument_spec,
                           supports_check_mode=True,
                           required_one_of=([['token', 'auth_realm', 'auth_username', 'auth_password']]),
                           required_together=([['auth_realm', 'auth_username', 'auth_password']])
                           )

    result = dict(changed=False, msg='', flow={})

    # Obtain access token, initialize API
    try:
        connection_header = get_token(module.params)
    except KeycloakError as e:
        module.fail_json(msg=str(e))

    kc = KeycloakAPI(module, connection_header)

    realm = module.params.get('realm')
    state = module.params.get('state')
    force = module.params.get('force')

    new_auth_repr = {
        "alias": module.params.get("alias"),
        "copyFrom": module.params.get("copyFrom"),
        "providerId": module.params.get("providerId"),
        "authenticationExecutions": module.params.get("authenticationExecutions"),
        "description": module.params.get("description"),
        "builtIn": module.params.get("builtIn"),
        "subflow": module.params.get("subflow"),
    }

    auth_repr = kc.get_authentication_flow_by_alias(alias=new_auth_repr["alias"], realm=realm)

    # Cater for when it doesn't exist (an empty dict)
    if not auth_repr:
        if state == 'absent':
            # Do nothing and exit
            if module._diff:
                result['diff'] = dict(before='', after='')
            result['changed'] = False
            result['end_state'] = {}
            result['msg'] = new_auth_repr["alias"] + ' absent'
            module.exit_json(**result)

        elif state == 'present':
            # Process a creation
            result['changed'] = True

            if module._diff:
                result['diff'] = dict(before='', after=new_auth_repr)

            if module.check_mode:
                module.exit_json(**result)

            # If copyFrom is defined, create authentication flow from a copy
            if "copyFrom" in new_auth_repr and new_auth_repr["copyFrom"] is not None:
                auth_repr = kc.copy_auth_flow(config=new_auth_repr, realm=realm)
            else:  # Create an empty authentication flow
                auth_repr = kc.create_empty_auth_flow(config=new_auth_repr, realm=realm)

            # If the authentication still not exist on the server, raise an exception.
            if auth_repr is None:
                result['msg'] = "Authentication just created not found: " + str(new_auth_repr)
                module.fail_json(**result)

            # Configure the executions for the flow
            create_or_update_executions(kc=kc, config=new_auth_repr, check_mode=module.check_mode, realm=realm)

            # Get executions created
            exec_repr = kc.get_executions_representation(config=new_auth_repr, realm=realm)
            if exec_repr is not None:
                auth_repr["authenticationExecutions"] = exec_repr
            result['end_state'] = auth_repr

    else:
        if state == 'present':
            # Process an update

            if force:  # If force option is true
                # Delete the actual authentication flow
                result['changed'] = True
                if module._diff:
                    result['diff'] = dict(before=auth_repr, after=new_auth_repr)
                if module.check_mode:
                    module.exit_json(**result)
                kc.delete_authentication_flow_by_id(id=auth_repr["id"], realm=realm)
                # If copyFrom is defined, create authentication flow from a copy
                if "copyFrom" in new_auth_repr and new_auth_repr["copyFrom"] is not None:
                    auth_repr = kc.copy_auth_flow(config=new_auth_repr, realm=realm)
                else:  # Create an empty authentication flow
                    auth_repr = kc.create_empty_auth_flow(config=new_auth_repr, realm=realm)
                # If the authentication still not exist on the server, raise an exception.
                if auth_repr is None:
                    result['msg'] = "Authentication just created not found: " + str(new_auth_repr)
                    module.fail_json(**result)

            # Configure the executions for the flow
            changed, diff, err_msg = create_or_update_executions(kc=kc, config=new_auth_repr, check_mode=module.check_mode, realm=realm)
            result['changed'] |= changed

            if module._diff:
                result['diff'] = diff

            # Get executions created
            exec_repr = kc.get_executions_representation(config=new_auth_repr, realm=realm)
            if exec_repr is not None:
                auth_repr["authenticationExecutions"] = exec_repr
            result['end_state'] = auth_repr
            
            result['msg'] = err_msg["lines"]

        else:
            # Process a deletion (because state was not 'present')
            result['changed'] = True

            if module._diff:
                result['diff'] = dict(before=auth_repr, after='')

            if module.check_mode:
                module.exit_json(**result)

            # delete it
            kc.delete_authentication_flow_by_id(id=auth_repr["id"], realm=realm)

            result['msg'] = 'Authentication flow: {alias} id: {id} is deleted'.format(alias=new_auth_repr['alias'],
                                                                                      id=auth_repr["id"])

    module.exit_json(**result)


if __name__ == '__main__':
    main()
