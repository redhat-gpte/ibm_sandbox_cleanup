import os
import sys
from datetime import datetime, timezone, timedelta
import argparse
import json
import logging
import urllib3
from metrics import CleanUpSandboxMetrics
import boto3

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


@CleanUpSandboxMetrics.record_request_latency
def clean_accounts(saa_api_key, saa_url, account_to_clean=None):
    saa_token = get_token(saa_api_key, saa_url)
    need_clean_accounts = get_accounts(saa_url, saa_token, 'cleanup')
    if need_clean_accounts:
        logging.info(f"Accounts needing cleanup: {need_clean_accounts}")
        for account in need_clean_accounts:
            cloud_provider = account['cloud_provider']['S']
            account_name = account['account_name']['S']

            if account_to_clean and account_name != account_to_clean:
                logging.info(f"Skipping account {account_name}")
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

                CleanUpSandboxMetrics.push_clean_metrics('ibm_clean_accounts', clean_status, 'check_cleanup', labels)
    else:
        logging.info("No accounts need cleanup.")
        return


@CleanUpSandboxMetrics.record_request_latency
def verify_accounts(saa_api_key, saa_url, account_to_verify=None):
    billing_table = os.environ.get('IBM_USAGE_DB')
    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_region = os.environ.get('AWS_REGION')

    if aws_access_key_id and aws_secret_access_key and aws_region:
        aws_session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region
            )
        db = aws_session.client('dynamodb')
        logging.info("Using production dynamodb.")
    else:
        db = boto3.client('dynamodb', endpoint_url='http://localhost:8000')
        logging.info("Using local development dynamodb")

    saa_token = get_token(saa_api_key, saa_url)
    need_verify_accounts = get_accounts(saa_url, saa_token, 'verify')

    if need_verify_accounts:
        logging.info(f"Accounts needing verification: {need_verify_accounts}")
        for account in need_verify_accounts:
            account_name = account['account_name']['S']

            if account_to_verify and account_name != account_to_verify:
                continue

            cloud_provider = account['cloud_provider']['S']
            logging.info(f"Starting verification of account {account_name}")
            cleanup_time = datetime.fromisoformat(account['cleanup_time']['S'])
            verification_time = cleanup_time + timedelta(hours=8)
            labels = {'account': account_name, 'cloud_provider': cloud_provider}
            if datetime.now(timezone.utc) >= verification_time:
                logging.info(f"Evaluating account {account['account_name']['S']}.")
                previous_usage_time = (datetime.now(timezone.utc) - timedelta(hours=1, minutes=20)).strftime('%Y-%m-%dT%H:%M')
                logging.info(f"Previous usage timestamp is {previous_usage_time}")
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
                no_current_usage = False

                if previous_usage['Items']:
                    logging.info(
                        f"{account_name} previous usage is {previous_usage['Items'][0]['billable_cost']['N']}")
                else:
                    logging.error(
                        f"There is no previous usage data for {account_name}"
                    )
                    no_current_usage = True

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
                    no_current_usage = True

                if no_current_usage:
                    current_cost = 0
                    previous_cost = 0
                else:
                    current_cost = float(
                        current_usage['Items'][0]['billable_cost']['N'])
                    previous_cost = float(
                        previous_usage['Items'][0]['billable_cost']['N'])

                CleanUpSandboxMetrics.push_clean_metrics('ibm_current_usage',
                                                         current_cost,
                                                         'verify_account',
                                                         labels,
                                                         'verify_account'
                                                         )
                CleanUpSandboxMetrics.push_clean_metrics('ibm_previous_usage',
                                                         previous_cost,
                                                         'verify_account',
                                                         labels,
                                                         'verify_account'
                                                         )

                if current_cost > previous_cost:
                    logging.warning(
                        f"The current charges of {current_cost} are greater than the previous charges of {previous_cost} in account {account_name}.")
                else:
                    logging.info(
                        f"No additional charges detected in account {account_name}.")
                    saa_token = get_token(saa_api_key, saa_url)
                    update_account(saa_url, saa_token, account_name,
                                   cloud_provider, 'verify'
                                   )
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

    push_gw_url = os.environ.get('PUSH_GATEWAY_URL', 'http://localhost:9091')
    if push_gw_url is None:
        logging.error("Push Gateway asssignment PUSH_GATEWAY_URL must be set as env variable")

    CleanUpSandboxMetrics.push_metrics()

    clean_accounts(saa_api_key, saa_url, account_to_clean=account)

    verify_accounts(saa_api_key, saa_url, account_to_verify=account)


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
