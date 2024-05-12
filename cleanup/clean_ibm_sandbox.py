import argparse
from time import sleep
import logging
import sys
import urllib3
from urllib.parse import urlencode
import json

from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from ibm_cloud_sdk_core import ApiException
from ibm_vpc import VpcV1
from ibm_platform_services.resource_manager_v2 import ResourceManagerV2
from ibm_platform_services.resource_controller_v2 import ResourceControllerV2


def get_token(api_key):
    url = "https://iam.cloud.ibm.com/identity/token?"
    values = {'grant_type': 'urn:ibm:params:oauth:grant-type:apikey',
              'apikey': api_key}
    encoded_args = urlencode(values)
    url = url + encoded_args
    http = urllib3.PoolManager()
    response = http.request('POST', url)
    token = json.loads(response.data.decode('utf-8'))
    return token['access_token']


def get_resource_groups(resource_manager):
    rgs = resource_manager.list_resource_groups().get_result()['resources']
    resource_group = []
    for rg in rgs:
        resource_group.append(rg['id'])
    return resource_group


def get_instance_groups(service):
    instance_groups = service.list_instance_groups(limit=100).get_result()[
        'instance_groups']
    response = []
    for ig in instance_groups:
        response.append(ig)
    return response


def delete_instance_groups(service):
    instance_groups = get_instance_groups(service)
    instance_group_patch = {
        "membership_count": 0
    }
    for ig in instance_groups:
        try:
            # Remove the autoscale manager if it exists
            for manager in ig['managers']:
                try:
                    service.delete_instance_group_manager(
                        ig['id'], manager['id'])
                except ApiException as e:
                    logging.error(f"{e.code}: {e.message}")

            # Set the membership_cout to 0, as defined
            # in instance_group_patch variable
            service.update_instance_group(
                ig['id'], instance_group_patch)

            # Wait for the instance group to scale down to 0
            ig_membership = service.list_instance_group_memberships(
                ig['id']).get_result()['memberships']
            if ig_membership:
                attempt = 0
                while attempt <= 5 and ig_membership:
                    logging.info(
                        f"Checking on instance group membership ({attempt})")
                    sleep(15)
                    attempt += 1
                    ig_membership = service.list_instance_group_memberships(
                        ig['id']).get_result()['memberships']

            # Delete the instance group
            logging.info(
                f"Deleting instance group {ig['id']} in VPC {ig['vpc']['id']} in resource group {ig['resource_group']['id']}")
            service.delete_instance_group(ig['id'])
        except ApiException as e:
            logging.error(
                f"Delete instance group failed with code {str(e.code)}: {str(e.message)}")

    remaining_instance_groups = get_instance_groups(service)
    if remaining_instance_groups:
        for ig in remaining_instance_groups:
            logging.error(
                f"Instance group {ig['id']} could not be deleted. Investigate.")
    else:
        logging.info("All instance groups deleted successfully.")


def get_instance_templates(service):
    instance_templates = service.list_instance_templates().get_result()[
        'templates']
    response = []
    for it in instance_templates:
        response.append(it)
    return response


def delete_instance_templates(service):
    instance_templates = get_instance_templates(service)
    for it in instance_templates:
        try:
            logging.info(
                f"Deleting instance template {it['id']} in VPC: {it['vpc']['id']} in resource group {it['resource_group']['id']}")
            service.delete_instance_template(it['id'])
        except ApiException as e:
            logging.error(
                f"Delete instance template failed with code {str(e.code)}: {str(e.message)}")

    if instance_templates:
        sleep(15)

    remaining_instance_templates = get_instance_templates(service)
    attempt = 0
    while attempt <= 5 and remaining_instance_templates:
        for it in remaining_instance_templates:
            try:
                logging.warning(
                    f"Instance template {it['id']} stuck in state {it['status']}.")
                logging.warning(
                    f"Retrying delete of instance template {it['id']} for attemp {attempt}.")
                service.delete_instance_template(it['id'])
            except ApiException as e:
                logging.error(
                    f"Delete instance template failed with code {e.code}: {e.message}")
        attempt += 1
        sleep(15)
        remaining_instance_templates = get_instance_templates(service)

    if remaining_instance_templates:
        for it in remaining_instance_templates:
            logging.error(
                f"Instance template {it['id']} could not be deleted. Investigate.")
    else:
        logging.info("All instance templates deleted successfully.")


def get_instances(service):
    instances = service.list_instances(limit=100).get_result()['instances']
    response = []
    for instance in instances:
        response.append(instance)
    return response


def delete_instances(service):
    instances = get_instances(service)
    for instance in instances:
        try:
            logging.info(
                f"Deleting instance {instance['id']} in VPC: {instance['vpc']['id']} in resource group: {instance['resource_group']['id']}")
            service.delete_instance(instance['id'])
        except ApiException as e:
            logging.error(
                f"Delete instance failed with code {e.code}: {e.message}")

    if instances:
        sleep(30)

    remaining_instances = get_instances(service)
    attempt = 0
    while attempt <= 5 and remaining_instances:
        for instance in remaining_instances:
            try:
                logging.warning(
                    f"Instance {instance['id']} stuck in state {instance['status']}.")
                logging.warning(
                    f"Retrying delete of instance {instance['id']} for attempt {attempt}.")
                service.delete_instance(instance['id'])
            except ApiException as e:
                logging.error(
                    f"Delete instance failed with code {e.code}: {e.message}")
        attempt += 1
        sleep(15)
        remaining_instances = get_instances(service)

    if remaining_instances:
        for instance in remaining_instances:
            logging.error(
                f"Instance {instance['id']} could not be deleted. Investigate.")
    else:
        logging.info("All instances deleted successfully.")


def get_volumes(service):
    volumes = service.list_volumes(limit=100).get_result()['volumes']
    response = []
    for volume in volumes:
        response.append(volume)
    return response


def delete_volumes(service):
    volumes = get_volumes(service)
    for volume in volumes:
        if volume['status'] in {'available', 'failed'}:
            try:
                logging.info(
                    f"Deleting volume {volume['id']} in: resource group: {volume['resource_group']['id']}")
                service.delete_volume(volume['id'])
            except ApiException as e:
                logging.error(
                    f"Delete volume failed with code {e.code}: {e.message}")

    if volumes:
        sleep(30)

    remaining_volumes = get_volumes(service)
    attempt = 0
    while attempt <= 5 and remaining_volumes:
        for volume in remaining_volumes:
            logging.warning(
                f"Volume {volume['id']} stuck in state {volume['status']}.")
            if volume['status'] in {'available', 'failed'}:
                try:
                    logging.warning(
                        f"Retrying delete of volume {volume['id']} for attempt {attempt}.")
                    service.delete_volume(volume['id'])
                except ApiException as e:
                    logging.error(
                        f"Delete volume failed with code {e.code}: {e.message}")
        attempt += 1
        sleep(15)
        remaining_volumes = get_volumes(service)

    if remaining_volumes:
        for volume in remaining_volumes:
            logging.error(
                f"Volume {volume['id']} could not be deleted. Investigate.")
    else:
        logging.info("All volumes deleted successfully.")


def get_keys(service):
    keys = service.list_keys(limit=100).get_result()['keys']
    response = []
    for key in keys:
        response.append(key)
    return response


def delete_keys(service):
    keys = get_keys(service)
    for key in keys:
        try:
            logging.info(
                f"Deleting key {key['id']} in: resource group: {key['resource_group']['id']}")
            service.delete_key(key['id'])
        except ApiException as e:
            logging.error(f"Delete key failed with code {e.code}: {e.message}")

    if keys:
        sleep(30)

    remaining_keys = get_keys(service)
    attempt = 0
    while attempt <= 5 and remaining_keys:
        for key in remaining_keys:
            try:
                logging.warning(
                    f"Retrying delete of key {key['id']} for attempt {attempt}.")
                service.delete_key(key['id'])
            except ApiException as e:
                logging.error(
                    f"Delete key failed with code {e.code}: {e.message}")
        attempt += 1
        sleep(15)
        remaining_keys = get_keys(service)

    if remaining_keys:
        for key in remaining_keys:
            logging.error(
                f"Key {key['id']} could not be deleted. Investigate.")
    else:
        logging.info("All keys deleted successfully.")


def get_images(service, resource_group):
    images = service.list_images(
        limit=100, resource_group_id=resource_group).get_result()['images']
    if images:
        image_list = []
        for image in images:
            image_list.append(image['id'])
        return image_list


def delete_images(service, resource_groups):
    for resource_group in resource_groups:
        images = get_images(service, resource_group)
        if images:
            for image in images:
                try:
                    logging.info(
                        f"Deleting the following image in resource group {resource_group}: {image}"
                    )
                    service.delete_image(image)
                except ApiException as e:
                    logging.error(
                        f"Delete image failed with code {e.code}: {e.message}"
                    )

        if images:
            sleep(30)

        remaining_images = get_images(service, resource_group)
        attempt = 0
        while attempt <= 5 and remaining_images:
            for image in remaining_images:
                try:
                    logging.warning(
                        f"Retrying delete of image {image['id']} for attempt {attempt}.")
                    service.delete_image(image)
                except ApiException as e:
                    logging.error(
                        f"Delete key failed with code {e.code}: {e.message}")
            attempt += 1
            sleep(15)
            remaining_images = get_images(service, resource_group)

        if remaining_images:
            for image in remaining_images:
                logging.error(
                    f"Key {image['id']} could not be deleted. Investigate.")
        else:
            logging.info("All images deleted successfully.")


def get_public_gateways(service):
    public_gateways = service.list_public_gateways(
        limit=100).get_result()['public_gateways']
    response = []
    for public_gateway in public_gateways:
        response.append(public_gateway)
    return response


def delete_public_gateways(service):
    public_gateways = get_public_gateways(service)
    for public_gateway in public_gateways:
        try:
            logging.info(
                f"Deleting public gateway {public_gateway['id']} in VPC: {public_gateway['vpc']['id']} resource group: {public_gateway['resource_group']['id']}")
            service.delete_public_gateway(public_gateway['id'])
        except ApiException as e:
            logging.error(
                f"Delete public gateway failed with code {e.code}: {e.message}")

    if public_gateways:
        sleep(30)

    remaining_public_gateways = get_public_gateways(service)
    attempt = 0
    while attempt <= 5 and remaining_public_gateways:
        for public_gateway in remaining_public_gateways:
            try:
                logging.warning(
                    f"Public gateway {public_gateway['id']} stuck in state {public_gateway['status']}.")
                logging.warning(
                    f"Retrying delete of public gateway {public_gateway['id']} for attempt {attempt}.")
                service.delete_public_gateway(public_gateway['id'])
            except ApiException as e:
                logging.error(
                    f"Delete public gateway failed with code {e.code}: {e.message}")
        attempt += 1
        sleep(15)
        remaining_public_gateways = get_public_gateways(service)

    if remaining_public_gateways:
        for public_gateway in remaining_public_gateways:
            logging.error(
                f"Public gateway {public_gateway['id']} could not be deleted. Investigate.")
    else:
        logging.info("All public gateways deleted successfully.")


def get_floating_ips(service):
    floating_ips = service.list_floating_ips(
        limit=100).get_result()['floating_ips']
    response = []
    for fip in floating_ips:
        response.append(fip)
    return response


def delete_floating_ips(service):
    floating_ips = get_floating_ips(service)
    for fip in floating_ips:
        try:
            logging.info(
                f"Deleting floating ip {fip['address']} with ID {fip['id']} in resource group: {fip['resource_group']['id']}")
            service.delete_floating_ip(fip['id'])
        except ApiException as e:
            logging.error(
                f"Delete floating IP failed with code {e.code}: {e.message}")

    if floating_ips:
        sleep(30)

    remaining_floating_ips = get_floating_ips(service)
    attempt = 0
    while attempt <= 5 and remaining_floating_ips:
        for fip in remaining_floating_ips:
            try:
                logging.warning(
                    f"Floating IP {fip['id']} stuck in state {fip['status']}.")
                logging.warning(
                    f"Retrying delete of floating IP {fip['id']} for attempt {attempt}.")
                service.delete_floating_ip(fip['id'])
            except ApiException as e:
                logging.error(
                    f"Delete instance failed with code {e.code}: {e.message}")
        attempt += 1
        sleep(15)
        remaining_floating_ips = get_floating_ips(service)

    if remaining_floating_ips:
        for fip in remaining_floating_ips:
            logging.error(
                f"Floating IP {fip['id']} could not be deleted. Investigate.")
    else:
        logging.info("All floating IP deleted successfully.")


def get_vpn_gateways(service):
    vpn_gateways = service.list_vpn_gateways(
        limit=100).get_result()['vpn_gateways']
    response = []
    for vpn_gateway in vpn_gateways:
        response.append(vpn_gateway)
    return response


def delete_vpn_gateways(service):
    vpn_gateways = get_vpn_gateways(service)
    for vpn_gateway in vpn_gateways:
        try:
            logging.info(
                f"Deleting VPN Gateway {vpn_gateway['id']} in resource group: {vpn_gateway['resource_group']['id']}")
            service.delete_vpn_gateway(vpn_gateway['id'])
        except ApiException as e:
            logging.error(
                f"Delete VPN Gateway failed with code {e.code}: {e.message}")

    if vpn_gateways:
        sleep(90)

    remaining_vpn_gateways = get_vpn_gateways(service)
    attempt = 0
    while attempt <= 5 and remaining_vpn_gateways:
        for vpn_gateway in remaining_vpn_gateways:
            try:
                logging.warning(
                    f"VPN Gateway {vpn_gateway['id']} stuck in state {vpn_gateway['status']}.")
                logging.warning(
                    f"Retrying delete of VPN Gateway {vpn_gateway['id']} for attempt {attempt}.")
                service.delete_vpn_gateway(vpn_gateway['id'])
            except ApiException as e:
                logging.error(
                    f"Delete VPN Gateway failed with code {e.code}: {e.message}")
        attempt += 1
        sleep(15)
        remaining_vpn_gateways = get_vpn_gateways(service)

    if remaining_vpn_gateways:
        for vpn_gateway in remaining_vpn_gateways:
            logging.error(
                f"VPN Gateway {vpn_gateway['id']} could not be deleted. Investigate.")
    else:
        logging.info("All VPN Gateways deleted successfully.")


def get_load_balancers(service):
    load_balancers = service.list_load_balancers(
        limit=100).get_result()['load_balancers']
    response = []
    if not load_balancers:
        return []

    for load_balancer in load_balancers:
        response.append(load_balancer)
    return response


def delete_load_balancers(service):
    load_balancers = get_load_balancers(service)
    for load_balancer in load_balancers:
        try:
            logging.info(
                f"Deleting load balancer {load_balancer['id']} in resource group: {load_balancer['resource_group']['id']}")
            service.delete_load_balancer(load_balancer['id'])
        except ApiException as e:
            logging.error(
                f"Delete load balancer failed with code {e.code}: {e.message}")

    if load_balancers:
        logging.info("sleeping 120")
        sleep(120)

    remaining_load_balancers = get_load_balancers(service)
    attempt = 0
    while attempt <= 5 and remaining_load_balancers:
        for load_balancer in remaining_load_balancers:
            try:
                logging.warning(
                    f"Load balancer {load_balancer['id']} stuck in state {load_balancer['provisioning_status']} ({attempt}).")
                if load_balancer['provisioning_status'] in {'active', 'failed'}:
                    logging.warning(
                        f"Retrying delete of load balancer {load_balancer['id']} for attempt {attempt}.")
                    service.delete_load_balancer(load_balancer['id'])
            except ApiException as e:
                logging.error(
                    f"Delete load balancer failed with code {e.code}: {e.message}")
        attempt += 1
        sleep(30)
        remaining_load_balancers = get_load_balancers(service)

    if remaining_load_balancers:
        for load_balancer in remaining_load_balancers:
            logging.error(
                f"Load balancer {load_balancer['id']} could not be deleted. Investigate.")
    else:
        logging.info("All load balancers deleted successfully.")


def get_endpoint_gateways(service):
    try:
        endpoint_gateways = service.list_endpoint_gateways(
            limit=100).get_result()['endpoint_gateways']
        response = []
        for endpoint_gateway in endpoint_gateways:
            response.append(endpoint_gateway)
        return response
    except Exception as e:
        logging.error(f"Get endpoint gateways failed with {e}", stack_info=True)


def delete_endpoint_gateways(service):
    endpoint_gateways = get_endpoint_gateways(service)
    for endpoint_gateway in endpoint_gateways:
        try:
            logging.info(
                f"Deleting endpoint gateway {endpoint_gateway['id']} in VPC: {endpoint_gateway['vpc']['id']} resource group: {endpoint_gateway['resource_group']['id']}")
            service.delete_endpoint_gateway(endpoint_gateway['id'])
        except ApiException as e:
            logging.error(
                f"Delete endpoint gateway failed with code {e.code}: {e.message}")

    if len(endpoint_gateways) > 0:
        sleep(30)

    remaining_endpoint_gateways = get_endpoint_gateways(service)
    attempt = 0
    while attempt <= 5 and remaining_endpoint_gateways:
        for endpoint_gateway in remaining_endpoint_gateways:
            try:
                logging.warning(
                    f"Endpoint gateway {endpoint_gateway['id']} stuck in state {endpoint_gateway['lifecycle_state']}.")
                logging.warning(
                    f"Retrying delete of endpoint gateway {endpoint_gateway['id']} for attempt {attempt}.")
                service.delete_endpoint_gateway(endpoint_gateway['id'])
            except ApiException as e:
                logging.error(
                    f"Delete endpoint gateway failed with code {e.code}: {e.message}")
        attempt += 1
        sleep(15)
        remaining_endpoint_gateways = get_endpoint_gateways(service)

    if remaining_endpoint_gateways:
        for endpoint_gateway in remaining_endpoint_gateways:
            logging.error(
                f"Endpoint gateway {endpoint_gateway['id']} could not be deleted. Investigate.")
    else:
        logging.info("All endpoint gateways deleted successfully.")


def get_flow_log_collectors(service):
    """
    As of 28 March 2024, the IBM Log Analysis and IBM Cloud Activity Tracker services
    are deprecated and will no longer be supported as of 30 March 2025.
    Customers will need to migrate to IBM Cloud Logs, which replaces these two services,
    prior to 30 March 2025.
    """

    try:
        flow_log_collectors = service.list_flow_log_collectors(limit=100).get_result()[
            'flow_log_collectors']

        if flow_log_collectors:
            logging.warning("The following flow log collectors exist:")
            for flc in flow_log_collectors:
                logging.warning(flc['id'])
        else:
            logging.info("No flow log collectors to delete.")

    except ApiException as e:
        if e.code == 502:
            return []

        logging.error(f"Get flow log collectors failed with {e.code}", stack_info=True)


def delete_flow_log_collectors(service):
    # TODO: Once COS is enabled and people can create private
    # flow collectors, this will need to be implemented.
    pass


def get_subnets(service):
    try:
        subnets = service.list_subnets().get_result()['subnets']
        response = []
        for subnet in subnets:
            response.append(subnet)
        return response
    except ApiException as e:
        if e.code == 502:
            return []

        logging.error(f"Get subnets failed with {e.code}", stack_info=True)
        return []


def delete_subnets(service):
    subnets = get_subnets(service)
    for subnet in subnets:
        try:
            logging.info(
                f"Deleting subnet {subnet['id']} in VPC: {subnet['vpc']['id']} resource group: {subnet['resource_group']['id']}")
            service.delete_subnet(subnet['id'])
        except ApiException as e:
            logging.error(
                f"Delete subnet failed with code {e.code}: {e.message}")

    if subnets:
        sleep(30)

    remaining_subnets = get_subnets(service)
    attempt = 0
    while attempt <= 5 and remaining_subnets:
        for subnet in remaining_subnets:
            try:
                logging.warning(
                    f"Subnet {subnet['id']} stuck in state {subnet['status']}.")
                logging.warning(
                    f"Retrying delete of subnet {subnet['id']} for attempt {attempt}.")
                service.delete_subnet(subnet['id'])
            except ApiException as e:
                logging.error(
                    f"Delete subnet failed with code {e.code}: {e.message}")
        attempt += 1
        sleep(15)
        remaining_subnets = get_subnets(service)

    if remaining_subnets:
        for subnet in remaining_subnets:
            logging.error(
                f"Subnet {subnet['id']} could not be deleted. Investigate.")
    else:
        logging.info("All Subnets deleted successfully.")


def get_vpcs(service):
    vpcs = service.list_vpcs().get_result()['vpcs']
    response = []
    for vpc in vpcs:
        response.append(vpc)
    return response


def delete_vpcs(service):
    vpcs = get_vpcs(service)
    for vpc in vpcs:
        try:
            logging.info(
                f"Deleting VPC {vpc['id']} in resource group: {vpc['resource_group']['id']}")
            service.delete_vpc(vpc['id'])
        except ApiException as e:
            logging.error(f"Delete VPC failed with code {e.code}: {e.message}")

    if vpcs:
        sleep(30)

    remaining_vpcs = get_vpcs(service)
    attempt = 0
    while attempt <= 5 and remaining_vpcs:
        for vpc in remaining_vpcs:
            try:
                logging.warning(
                    f"VPC {vpc['id']} stuck in state {vpc['status']}.")
                logging.warning(
                    f"Retrying delete of VPC {vpc['id']} for attempt {attempt}.")
                service.delete_vpc(vpc['id'])
            except ApiException as e:
                logging.error(
                    f"Delete VPC failed with code {e.code}: {e.message}")
        attempt += 1
        sleep(15)
        remaining_vpcs = get_vpcs(service)

    if remaining_vpcs:
        for vpc in remaining_vpcs:
            logging.error(
                f"VPC {vpc['id']} could not be deleted. Investigate.")
    else:
        logging.info("All VPCs deleted successfully.")


def get_security_groups(service):
    security_groups = service.list_security_groups().get_result()[
        'security_groups']
    response = []
    for sg in security_groups:
        response.append(sg)
    return response


def delete_security_groups(service):
    security_groups = get_security_groups(service)
    for sg in security_groups:
        try:
            logging.info(
                f"Deleting security group {sg['id']} in resource group: {sg['resource_group']['id']}")
            service.delete_security_group(sg['id'])
        except ApiException as e:
            logging.error(
                f"Delete security group failed with code {e.code}: {e.message}")

    if security_groups:
        sleep(15)

    remaining_security_groups = get_security_groups(service)
    attempt = 0
    while attempt <= 5 and remaining_security_groups:
        for sg in remaining_security_groups:
            try:
                logging.warning(
                    f"Retrying delete of security group {sg['id']} for attempt {attempt}.")
                service.delete_security_group(sg['id'])
            except ApiException as e:
                logging.error(
                    f"Delete security group failed with code {e.code}: {e.message}")
        attempt += 1
        sleep(15)
        remaining_security_groups = get_security_groups(service)

    if remaining_security_groups:
        for sg in remaining_security_groups:
            logging.error(
                f"Security group {sg['id']} could not be deleted. Investigate.")
    else:
        logging.info("All security groups deleted successfully.")


def get_rhoic_clusters(api_key):
    token = get_token(api_key)
    http = urllib3.PoolManager()
    url = "https://containers.cloud.ibm.com/global/v2/vpc/getClusters"
    headers = {"Authorization": "Bearer " + token}
    logging.info("Getting the list of RHOIC clusters")
    rhoic_clusters = http.request(
        'GET',
        url,
        headers=headers
    ).data.decode('utf-8')
    rhoic_clusters = json.loads(rhoic_clusters)

    return rhoic_clusters


def delete_rhoic_clusters(api_key):
    rhoic_clusters = get_rhoic_clusters(api_key)
    rhoic_cluster_deleted = False
    for cluster in rhoic_clusters:
        if cluster['state'] != 'deleting':
            token = get_token(api_key)
            http = urllib3.PoolManager()
            url = f"https://containers.cloud.ibm.com/global/v1/clusters/{cluster['id']}?deleteResources=True"
            headers = {"Authorization": "Bearer " + token}
            logging.info(f"Deleting the RHOIC cluster {cluster['id']}")
            http.request(
                'DELETE',
                url,
                headers=headers
            )
            rhoic_cluster_deleted = True

    if rhoic_cluster_deleted:
        logging.info(
            "Sleeping for 10 minutes to wait for RHOIC clusters to delete")
        sleep(600)

    remaining_rhoic_clusters = get_rhoic_clusters(api_key)
    attempt = 0
    while attempt <= 5 and remaining_rhoic_clusters:
        logging.info(
            f"Pausing 60 seconds for RHOIC cleanup attempt #{attempt}")
        sleep(60)
        attempt += 1
        remaining_rhoic_clusters = get_rhoic_clusters(api_key)

    if remaining_rhoic_clusters:
        logging.error("RHOIC clusters could not be cleaned up")
    else:
        logging.info("No RHOIC clusters found.")


def delete_cos_instance(resource_controller, resource):
    try:
        logging.info(f"Deleting COS instance {resource}")
        resource_controller.delete_resource_instance(resource, recursive=True)
    except ApiException as e:
        logging.error(
            f"Delete resource instance failed with code {e.code}: {e.message}")

    logging.info("Pausing 20s for COS instances to delete")
    sleep(20)

    cos_instance = resource_controller.get_resource_instance(
        resource).get_result()

    if cos_instance['state'] != 'removed':
        logging.warning(
            f"COS instance {cos_instance['crn']} may not be deleted. Investigate"
        )
    else:
        logging.info(
            f"COS instance {cos_instance['crn']} deleted successfully.")


def get_all_resources(resource_controller, resource_groups):
    resource_list = []
    for rg in resource_groups:
        resources = resource_controller.list_resource_instances(
            resource_group_id=rg).get_result()['resources']
        if resources:
            for resource in resources:
                logging.warning(
                    f"Resource group {rg} still has resources: {resource['resource_id']}: {resource['id']}")
                resource_list.append(resource)
        else:
            logging.info(f"No resources in resource group {rg}")
    # The security advisor resources cannot be deleted, so we
    # will exclude them from the list
    ignore_resource = ['security-advisor', 'schematics']
    response = [res for res in resource_list if all(i not in res['id'] for i in ignore_resource)]
    return response


def clean(api_key=None):
    if api_key is None:
        logging.error("API key must be provided.")
        return None

    authenticator = IAMAuthenticator(api_key)
    resource_manager = ResourceManagerV2(authenticator=authenticator)
    resource_groups = get_resource_groups(resource_manager)

    # RHOIC is global, so this is being deleted before looping
    # through the regions
    delete_rhoic_clusters(api_key)

    service = VpcV1(authenticator=authenticator, generation=2)

    regions = service.list_regions().get_result()['regions']
    for region in regions:
        # This region is causing a error 502
        if region['name'] == 'ca-tor':
            continue

        base_url = region['endpoint'] + '/v1'
        service.set_service_url(base_url)
        logging.info(f"Processing region: {region['endpoint']}")
        delete_instance_groups(service)
        delete_instance_templates(service)
        delete_instances(service)
        delete_volumes(service)
        delete_keys(service)
        delete_images(service, resource_groups)
        delete_vpn_gateways(service)
        delete_load_balancers(service)
        delete_endpoint_gateways(service)
        get_flow_log_collectors(service)
        delete_subnets(service)
        delete_public_gateways(service)
        delete_floating_ips(service)
        delete_vpcs(service)
        delete_security_groups(service)

    logging.info("Sleeping for 60s to let resource controller catch up.")
    sleep(60)

    resource_controller = ResourceControllerV2(authenticator=authenticator)
    resource_list = get_all_resources(resource_controller, resource_groups)

    logging.info("Processing cloud object storage instances")
    for resource in resource_list:
        if 'cloud-object-storage' in resource['crn']:
            delete_cos_instance(resource_controller, resource['crn'])

    resource_list = get_all_resources(resource_controller, resource_groups)
    return resource_list


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format='%(asctime)s %(module)s %(levelname)s %(message)s', datefmt='%Y-%m-%dT%H:%M:%S%z')
    parser = argparse.ArgumentParser("Create and update IBM Cloud accounts.")
    parser.add_argument("--api-key", required=True,
                        help="The API key that will be used to create access token")
    args = parser.parse_args()

    if args.api_key:
        api_key = args.api_key

    clean(api_key)
