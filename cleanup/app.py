import os
import sys
import urllib3
import argparse
import json
import logging
from datetime import datetime, timezone, timedelta
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway, Counter

import boto3
import botocore

import clean_ibm_sandbox


def get_token(saa_api_key, saa_url):
    url = f"{saa_url}/token"
    values = {
        "api_key": saa_api_key
    }
    http = urllib3.PoolManager()
    response = http.request('POST', url, fields=values)
    token = json.loads(response.data.decode('utf-8'))
    return token['access_token']


def get_accounts(saa_url, saa_token, query_type):
    if query_type == 'cleanup':
        url = f"{saa_url}/sandbox/cleanup"
    elif query_type == 'verify':
        url = f"{saa_url}/sandbox/release"

    headers = {
        "Authorization": f"Bearer {saa_token}"
    }

    http = urllib3.PoolManager()
    response = http.request(
        'GET',
        url,
        headers=headers
    )

    response = json.loads(response.data.decode('utf-8'))

    return response


def push_to_prometheus(push_gw_url, job_name, metric_name, description, value, labels=None, instance='check_cleanup'):
    labels_names = ['instance']
    labels_values = [instance]
    registry = CollectorRegistry()
    if labels and isinstance(labels, dict):
        for k,v in labels.items():
            labels_names.append(k)
            labels_values.append(v)
    g = Gauge(metric_name, description, labels_names, registry=registry)
    g.labels(*labels_values).set(value)
    try:
        logging.info(f"Pushing metrics to prometheus {push_gw_url}")
        push_to_gateway(push_gw_url, job=job_name, registry=registry)
    except Exception as e:
        logging.error(f"Error sending metrics to pushgateway {push_gw_url} with error {e}")


def clean_accounts(saa_api_key, saa_url, push_gw_url, account_to_clean=None):
    saa_token = get_token(saa_api_key, saa_url)
    need_clean_accounts = get_accounts(saa_url, saa_token, 'cleanup')
    if need_clean_accounts:
        logging.info("Accounts needing cleanup:")
        logging.info(need_clean_accounts)
        for account in need_clean_accounts:
            cloud_provider = account['cloud_provider']['S']
            account_name = account['account_name']['S']

            if account_name and account_name != account_to_clean:
                continue

            ibm_api_key = account['master_api_key']['S']
            labels = {'account': account_name, 'cloud_provider': cloud_provider}
            logging.info(f"Starting clean of account {account_name}")
            cleaning = clean_ibm_sandbox.clean(ibm_api_key)
            if not cleaning:
                saa_token = get_token(saa_api_key, saa_url)
                clean_status = 0
                update_account(saa_url, saa_token, account_name, cloud_provider, 'cleanup')
                logging.info(
                    f"No resources found in account {account_name}; marking cleanup timestamp.")
            else:
                logging.error(
                    f"Account {account['account_name']} in cloud provider {account['cloud_provider']} could not be fully cleaned.")
                clean_status = 1

            push_to_prometheus(push_gw_url, 'clean_accounts', 'ibm_clean_accounts', 'Resource to be clean by account', clean_status, labels)

    else:
        logging.info("No accounts need cleanup.")
        return


def verify_accounts(saa_api_key, saa_url, push_gw_url, account_to_verify=None):
    billing_table = os.environ.get('IBM_USAGE_DB')
    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_region = os.environ.get('AWS_REGION')

    if aws_access_key_id and aws_secret_access_key and aws_region:
        db = boto3.client('dynamodb', region_name=aws_region)
        logging.info("Using production dynamodb.")
    else:
        db = boto3.client('dynamodb', endpoint_url='http://localhost:8000')
        logging.info("Using local development dynamodb")

    saa_token = get_token(saa_api_key, saa_url)
    need_verify_accounts = get_accounts(saa_url, saa_token, 'verify')

    if need_verify_accounts:
        logging.info("Accounts needing verification:")
        logging.info(need_verify_accounts)
        for account in need_verify_accounts:
            account_name = account['account_name']['S']

            if account_to_verify and account_name != account_to_verify:
                continue

            cloud_provider = account['cloud_provider']['S']
            logging.info(f"Starting verification of account {account_name}")
            cleanup_time = datetime.fromisoformat(account['cleanup_time']['S'])
            verification_time = cleanup_time
            labels = {'account': account_name, 'cloud_provider': cloud_provider}
            if datetime.now(timezone.utc) >= verification_time:
                logging.info(f"Evaluating account {account['account_name']['S']}.")
                previous_usage_time = (datetime.now(timezone.utc) - timedelta(hours=1, minutes=20)).strftime('%Y-%m-%dT%H:%M')
                logging.info(f"Previous usage timestamp is {previous_usage_time}")
                db = boto3.client('dynamodb', region_name=aws_region)
                previous_usage = db.query(
                    TableName=billing_table,
                    KeyConditionExpression='account_name = :an AND begins_with(#t, :ts)',
                    ExpressionAttributeValues={
                        ":an": {
                            "S": account_name
                        },
                        ":ts": {
                            "S": previous_usage_time
                        }
                    },
                    ExpressionAttributeNames={
                        "#t": "timestamp"
                    }
                )

                if previous_usage['Items']:
                    logging.info(
                        f"{account_name} previous usage is {previous_usage['Items'][0]['billable_cost']['N']}")
                else:
                    logging.error(
                        f"There is no previous usage data for {account_name}"
                    )
                    return

                current_usage_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime('%Y-%m-%dT%H')
                logging.info(f"Current usage timestamp is {current_usage_time}")
                current_usage = db.query(
                    TableName=billing_table,
                    KeyConditionExpression='account_name = :an AND begins_with(#t, :ts)',
                    ExpressionAttributeValues={
                        ":an": {
                            "S": account_name
                        },
                        ":ts": {
                            "S": current_usage_time
                        }
                    },
                    ExpressionAttributeNames={
                        "#t": "timestamp"
                    }
                )

                if current_usage['Items']:
                    logging.info(
                        f"{account_name} current usage is {current_usage['Items'][0]['billable_cost']['N']}")
                else:
                    logging.error(
                        f"There is no current usage data for {account_name}"
                    )
                    return

                current_cost = float(
                    current_usage['Items'][0]['billable_cost']['N'])
                previous_cost = float(
                    previous_usage['Items'][0]['billable_cost']['N'])

                push_to_prometheus(push_gw_url, 'verify_accounts', 'ibm_current_usage', 'Current usage by account',
                                current_cost, labels)
                push_to_prometheus(push_gw_url, 'verify_accounts', 'ibm_previous_usage', 'Previous usage by account',
                                previous_cost, labels)

                if current_cost > previous_cost:
                    logging.warning(
                        f"The current charges of {current_cost} are greater than the previous charges of {previous_cost} in account {account_name}.")
                else:
                    logging.info(
                        f"No additional charges detected in account {account_name}.")
                    saa_token = get_token(saa_api_key, saa_url)
                    update_account(saa_url, saa_token, account_name,
                                            cloud_provider, 'verify')
                    logging.info(f"Account {account_name} released.")

            else:
                logging.info(
                    f"Account {account['account_name']['S']} is not ready to be verified.")

    else:
        logging.info("No accounts need usage verification.")


def update_account(saa_url, saa_token, account_name, cloud_provider, update_type):
    if update_type == 'cleanup':
        url = f"{saa_url}/sandbox/cleanup"
    elif update_type == 'verify':
        url = f"{saa_url}/sandbox/release"

    headers = {
        "Authorization": f"Bearer {saa_token}"
    }
    values = {
        "account_name": account_name,
        "cloud_provider": cloud_provider
    }

    http = urllib3.PoolManager()
    response = http.request(
        'POST',
        url,
        headers=headers,
        fields=values
    )
    response = json.loads(response.data.decode('utf-8'))
    return response


def main(api_key=None, account=None):
    if api_key is None:
        saa_api_key = os.environ.get('SAA_API_KEY')
    elif api_key:
        saa_api_key = api_key
    else:
        logging.error("API key must be provided.")

    saa_url = os.environ.get('SAA_URL')
    if saa_url is None:
        logging.error("Sandbox assignment API URL must be set as env variable")

    push_gw_url = os.environ.get('PUSH_GATEWAY_URL')
    if push_gw_url is None:
        logging.error("Push Gateway asssignment PUSH_GATEWAY_URL must be set as env variable")

    clean_accounts(saa_api_key, saa_url, push_gw_url, account_to_clean=account)

    verify_accounts(saa_api_key, saa_url, push_gw_url, account_to_verify=account)


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format='%(asctime)s %(module)s %(levelname)s %(message)s', datefmt='%Y-%m-%dT%H:%M:%S%z')

    parser = argparse.ArgumentParser(
        "Get billing data from cloud provider")
    parser.add_argument("--api-key", required=False,
                        help="The API key to the account assignment API.")
    parser.add_argument("--account", required=False,
                        help="The account to verifty or clean up.")
    args = parser.parse_args()

    main(api_key=args.api_key, account=args.account)
