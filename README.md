# IBM CleanUP and Billing Update

This application manages sandbox account usage and billing within an OpenShift environment and includes integrated metrics export to Prometheus. It consists of two main components: Cleanup and Update Billing, both deployed as cronjobs.

## Overview

### Components

1. Cleanup
This component runs every 30 minutes to check for sandbox accounts that need to be cleaned up or released for reuse. Accounts are eligible for release after showing no cost increase across two consecutive billing updates.

2. Update Billing
Runs every hour at the 15th minute to update utilization costs for each account in DynamoDB.

## Metrics Export

Both components export metrics to a Prometheus Pushgateway, ensuring detailed monitoring and alerting. The Pushgateway is installed and configured as part of the application's deployment using its Helm chart.

### Metrics Details

```
request_latency_seconds = Summary(
    'request_latency_seconds',
    'Time spent processing request',
    ['method_name']
    )

ibm_verify_accounts = Gauge(
    'ibm_verify_accounts',
    'Total number of accounts verified',
    ['account', 'cloud_provider', 'instance', 'job_name']
)

ibm_current_usage = Gauge(
    'ibm_current_usage',
    'Total number of current usage',
    ['account', 'cloud_provider', 'instance', 'job_name']
)

ibm_previous_usage = Gauge(
    'ibm_previous_usage',
    'Total number of previous usage',
    ['account', 'cloud_provider', 'instance', 'job_name']
)

ibm_clean_accounts = Gauge(
    'ibm_clean_accounts',
    'Total number of accounts cleaned',
    ['account', 'cloud_provider', 'instance', 'job_name']
)

ibm_update_billing_account_total = Counter(
    'ibm_update_billing_account_total',
    'Total number of accounts updated',
    ['instance']
)

ibm_update_billing_account_failure_total = Counter(
    'ibm_update_billing_account_failure_total',
    'Total number of account updates that failed',
    ['instance']
)

ibm_update_billing_acccount_failures = Counter(
    'ibm_update_billing_account_failures',
    'Total number of account updates that failed',
    ['sandbox_name', 'instance']
)

ibm_update_billing_account_success = Counter(
    'ibm_update_billing_account_success',
    'Total number of account updates that succeeded',
    ['sandbox_name', 'instance']
)

```