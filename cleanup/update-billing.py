import os
from datetime import datetime, timezone, timedelta
import logging
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from ibm_platform_services.enterprise_usage_reports_v1 import EnterpriseUsageReportsV1
from ibm_platform_services.enterprise_management_v1 import EnterpriseManagementV1
import boto3


logger = logging.getLogger()


def get_account_group_billing(usage_reporter, account_groups, billing_month):
    for ag in account_groups:
        accounts = usage_reporter.get_resource_usage_report(
            account_group_id=ag['id'], month=billing_month, children=True).get_result()['reports']
        for account in accounts:
            print(account['entity_name'])
        print()


def create_record(db, billing_table, billing_ttl, **kwargs):
    response = db.put_item(
        TableName=billing_table,
        Item={
            "account_name": {
                "S": kwargs['account_name']
            },
            "cloud_provider": {
                "S": kwargs['cloud_provider']
            },
            "account_id": {
                "S": kwargs['account_id']
            },
            "billing_month": {
                "S": kwargs['billing_month']
            },
            "billable_cost": {
                "N": str(kwargs['billable_cost'])
            },
            "timestamp": {
                "S": datetime.now(timezone.utc).isoformat("T", "minutes")
            },
            "ttl": {
                "N": str(billing_ttl.timestamp())
            }
        }
    )
    return response


def main():
    enterprice_api_key = os.environ.get('ENTERPRISE_API_KEY')
    if enterprice_api_key is None:
        print("API key must be provided (env ENTERPRISE_API_KEY).")
        return None

    enterprice_account_id = os.environ.get('ENTERPRISE_ACCOUNT_ID')
    if enterprice_account_id is None:
        print("Account ID must be provided (env ENTERPRISE_ACCOUNT_ID).")
        return None

    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_region = os.environ.get('AWS_REGION', 'us-west-2')

    if aws_access_key_id is None or aws_secret_access_key is None:
        print("AWS credentials must be provided (env AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY).")
        return None

    billing_table = os.environ.get('BILLING_TABLE', 'sandbox_billing')
    cloud_provider = os.environ.get('CLOUD_PROVIDER', 'ibm')

    aws_session = boto3.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=aws_region
        )
    db = aws_session.client('dynamodb')

    billing_month = datetime.now().strftime('%Y-%m')

    authenticator = IAMAuthenticator(enterprice_api_key)

    account_manager = EnterpriseManagementV1(authenticator=authenticator)
    usage_reporter = EnterpriseUsageReportsV1(authenticator=authenticator)

    account_groups = account_manager.list_account_groups(
        enterprise_id=enterprice_account_id).get_result()['resources']

    for ag in account_groups:
        logger.info(f"Getting billing for account group {ag['name']}")
        billing_ttl = datetime.now() + timedelta(days=61)
        usage = usage_reporter.get_resource_usage_report(account_group_id=ag['id'],
                                                         month=billing_month,
                                                         children=True,
                                                         limit=100
                                                         ).get_result()['reports']
        for account in usage:
            logger.info(f"Updating billing for account {account['entity_name']}")
            response = create_record(db,
                                     billing_table,
                                     billing_ttl,
                                     account_name=account['entity_name'],
                                     account_id=account['entity_id'],
                                     billable_cost=account['billable_cost'],
                                     billing_month=billing_month,
                                     cloud_provider=cloud_provider
                                     )
            if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                print(
                    f"Account {account['entity_name']} updated successfully.")
            else:
                logger.error(
                    f"Account {account['entity_name']} could not be updated.")
                print(
                    f"Account {account['entity_name']} could not be updated.")


if __name__ == '__main__':
    main()
