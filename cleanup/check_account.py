import os
import sys
import urllib
import argparse
import json
import logging
from datetime import datetime, timezone, timedelta
# import concurrent.futures
# import threading

import boto3
import botocore

import clean_ibm_sandbox


def api_call(url, **kwargs):
    if 'values' in kwargs:
        values = kwargs['values']
    else:
        values = {}

    if 'headers' in kwargs:
        headers = kwargs['headers']
    else:
        headers = {}

    if not values:
        request = urllib.request.Request(url=url, headers=headers)
        response = urllib.request.urlopen(request)
    else:
        data = urllib.parse.urlencode(values)
        data = data.encode('ascii')
        request = urllib.request.Request(url, data, headers)
        response = urllib.request.urlopen(request)

    return response


def get_token(saa_api_key, saa_url):
    url = f"{saa_url}/token"
    values = {
        "api_key": saa_api_key
    }
    response = api_call(url, values=values)
    token = json.loads(response.read())

    return token['access_token']


def get_accounts(saa_url, saa_token, query_type):
    if query_type == 'cleanup':
        url = f"{saa_url}/sandbox/cleanup"
    elif query_type == 'verify':
        url = f"{saa_url}/sandbox/release"

    headers = {
        "Authorization": f"Bearer {saa_token}"
    }

    response = api_call(url, headers=headers)
    response = json.loads(response.read())

    return response


def clean_accounts(saa_api_key, saa_url):
    saa_token = get_token(saa_api_key, saa_url)

    need_clean_accounts = get_accounts(saa_url, saa_token, 'cleanup')
    if need_clean_accounts:
        logging.info("Accounts needing cleanup:")
        logging.info(need_clean_accounts)
        for account in need_clean_accounts:
            cloud_provider = account['cloud_provider']['S']
            account_name = account['account_name']['S']
            ibm_api_key = account['master_api_key']['S']
            logging.info(f"Starting clean of account {account_name}")
            cleaning = clean_ibm_sandbox.clean(ibm_api_key)
            if not cleaning:
                logging.info(
                    f"No resources found in account {account_name}; marking cleanup timestamp.")
                response = update_account(saa_url, saa_token, account_name,
                                          cloud_provider, 'cleanup')
            else:
                logging.error(
                    f"Account {account['account_name']} in cloud provider {account['cloud_provider']} could not be fully cleaned.")
                response = update_account(saa_url, saa_token, account_name,
                                          cloud_provider, 'cleanup')
            return response

    else:
        logging.info("No accounts need cleanup.")
        return


def verify_accounts(saa_api_key, saa_url):
    billing_table = os.environ.get('IBM_USAGE_DB')
    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_region = os.environ.get('AWS_REGION')

    if aws_access_key_id and aws_secret_access_key and aws_region:
        prod = boto3.session.Session(aws_access_key_id=aws_access_key_id,
                                     aws_secret_access_key=aws_secret_access_key, region_name=aws_region)
        db = prod.client('dynamodb')
        logging.info("Using production dynamodb.")
    else:
        db = boto3.client('dynamodb', endpoint_url='http://localhost:8000')
        logging.info("Using local development dynamodb")

    saa_token = get_token(saa_api_key, saa_url)

    need_verify_accounts = get_accounts(saa_url, saa_token, 'verify')

    if need_verify_accounts:
        logging.info(f"Accounts needing verification: {need_verify_accounts}")
    else:
        logging.info("No accounts need usage verification.")

    for account in need_verify_accounts:
        account_name = account['account_name']['S']
        cloud_provider = account['cloud_provider']['S']
        logging.info(f"Starting verification of account {account_name}")
        cleanup_time = datetime.fromisoformat(account['cleanup_time']['S'])
        verification_time = cleanup_time + timedelta(hours=3)
        if datetime.now(timezone.utc) >= verification_time:
            logging.info(f"Evaluating account {account['account_name']['S']}.")
            previous_usage = db.query(
                TableName=billing_table,
                KeyConditionExpression='account_name = :an AND begins_with(#t, :ts)',
                ExpressionAttributeValues={
                    ":an": {
                        "S": account_name
                    },
                    ":ts": {
                        "S": (datetime.now(timezone.utc) - timedelta(hours=2, minutes=20)).strftime('%Y-%m-%dT%H')
                    }
                },
                ExpressionAttributeNames={
                    "#t": "timestamp"
                }
            )

            logging.info(
                f"{account_name} previous usage is {previous_usage['Items'][0]['billable_cost']['N']}")

            current_usage = db.query(
                TableName=billing_table,
                KeyConditionExpression='account_name = :an AND begins_with(#t, :ts)',
                ExpressionAttributeValues={
                    ":an": {
                        "S": account_name
                    },
                    ":ts": {
                        "S": (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime('%Y-%m-%dT%H')
                    }
                },
                ExpressionAttributeNames={
                    "#t": "timestamp"
                }
            )

            logging.info(
                f"{account_name} current usage is {current_usage['Items'][0]['billable_cost']['N']}")

            current_cost = float(
                current_usage['Items'][0]['billable_cost']['N'])
            previous_cost = float(
                previous_usage['Items'][0]['billable_cost']['N'])

            if current_cost > previous_cost:
                logging.warning(
                    f"The current charges of {current_cost} are greater than the previous charges of {previous_cost} in account {account_name}.")
            else:
                logging.info(
                    f"No additional charges detected in account {account_name}.")
                response = update_account(saa_url, saa_token, account_name,
                                          cloud_provider, 'verify')
                logging.info(f"Account {account_name} released.")

                return response

        else:
            logging.info(
                f"Account {account['account_name']['S']} is not ready to be verified.")


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

    response = api_call(url, headers=headers, values=values)
    response = json.loads(response.read())
    return response


def main(api_key=None):
    if api_key is None:
        saa_api_key = os.environ.get('SAA_API_KEY')
    elif api_key:
        saa_api_key = api_key
    else:
        logging.error("API key must be provided.")

    saa_url = os.environ.get('SAA_URL')
    if saa_url is None:
        logging.error("Sandbox assignment API URL must be set as env variable")

    clean_accounts(saa_api_key, saa_url)

    verify_accounts(saa_api_key, saa_url)


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format='%(asctime)s %(module)s %(levelname)s %(message)s', datefmt='%Y-%m-%dT%H:%M:%S%z')

    parser = argparse.ArgumentParser(
        "Get billing data from cloud provider")
    parser.add_argument("--api-key", required=False,
                        help="The API key to the account assignment API.")
    args = parser.parse_args()

    main(api_key=args.api_key)
