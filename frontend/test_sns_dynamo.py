"""
Test script to add job info to DynamoDB and trigger Lambda tasks using SNS.

Author: Angad Gill
"""
import boto3
import json

DYNAMO_URL = 'https://dynamodb.us-west-1.amazonaws.com'
DYNAMO_TABLE = 'test_table'
DYNAMO_REGION = 'us-west-1'
SNS_TOPIC_ARN = 'arn:aws:sns:us-west-1:000169391513:kmeans-service'
S3_BUCKET = 'kmeansservice'

import time


def send_to_dynamo(id, job_id, task_id, covar_tied, covar_type, k, n_init, s3_file_key, columns, sns_message,
                   sns_subject, task_status):
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    response = table.put_item(
        Item={'id': id, 'job_id': job_id, 'task_id': task_id, 'sns_message': sns_message, 'sns_subject': sns_subject,
              'covar_type': covar_type, 'covar_tied': covar_tied, 'k': k, 'n_init': n_init, 's3_file_key': s3_file_key,
              'columns': columns, 'task_status': task_status})
    return response


def send_to_sns(message, subject):
    sns = boto3.client('sns')
    response = sns.publish(TopicArn=SNS_TOPIC_ARN, Message=message, Subject=subject)
    return response


if __name__ == '__main__':
    job_id = 5
    # task_id = 2
    # covar_tied = True
    # covar_type = 'full'

    covar_types = ['full', 'diag', 'spher']
    covar_tieds = [True, False]
    # covar_types = ['full']
    # covar_tieds = [True]
    s3_file_key = 'data/2/CalPoly_no_outliers.csv'
    n_init = 10
    task_status = 'pending'
    columns = ['EC1', 'EC2']
    max_k = 2
    n_experiments = 2

    task_id = 0
    start_time = time.time()
    for _ in range(n_experiments):
        for k in range(1, max_k+1):
            for covar_type in covar_types:
                for covar_tied in covar_tieds:
                    id = int('{}'.format(job_id)+'{0:04d}'.format(task_id))
                    payload = dict(id=id, k=k, covar_type=covar_type, covar_tied=covar_tied, n_init=n_init,
                                   s3_file_key=s3_file_key, columns=columns)
                    sns_message = json.dumps(payload)
                    sns_subject = 'script test'

                    print(send_to_dynamo(id, job_id, task_id, covar_tied, covar_type, k, n_init, s3_file_key, columns,
                                         sns_message, sns_subject, task_status))
                    print(send_to_sns(sns_message, sns_subject))
                    print('task_id: {} submitted.'.format(task_id))
                    task_id += 1
    print('Time taken: {:.4f} seconds'.format(time.time()-start_time))