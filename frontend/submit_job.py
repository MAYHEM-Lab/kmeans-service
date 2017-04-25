"""
Submit job to AWS DynamoDB and AWS Labmda asynchronously using Celery and RabbitMQ

Author: Angad Gill
"""

import boto3
import json
import pandas as pd

from celery import Celery

app = Celery('jobs', broker='amqp://localhost//')


DYNAMO_URL = 'https://dynamodb.us-west-1.amazonaws.com'
DYNAMO_TABLE = 'test_table'
DYNAMO_REGION = 'us-west-1'
SNS_TOPIC_ARN = 'arn:aws:sns:us-west-1:000169391513:kmeans-service'

@app.task
def submit_job(n_init, n_experiments, max_k, covars, filepath, s3_file_key, job_id):
    n_tasks = n_experiments * max_k * len(covars)

    df = pd.read_csv(filepath, nrows=1)
    exclude_columns = ['longitude', 'latitude']
    columns = [c for c in df.columns if c.lower() not in exclude_columns]
    task_status = 'pending'
    task_id = 0

    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    sns = boto3.client('sns')

    for _ in range(n_experiments):
        for k in range(1, max_k+1):
            for covar in covars:
                covar_type, covar_tied = covar.lower().split('-')
                covar_tied = covar_tied=='tied'
                id = int('{}'.format(job_id)+'{0:04d}'.format(task_id))

                sns_payload = dict(id=id, k=k, covar_type=covar_type, covar_tied=covar_tied, n_init=n_init,
                                   s3_file_key=s3_file_key, columns=columns)
                sns_message = json.dumps(sns_payload)
                sns_subject = 'web test'

                item = dict(id=id, job_id=job_id, task_id=task_id, sns_message=sns_message, sns_subject=sns_subject,
                            covar_type=covar_type, covar_tied=covar_tied, k=k, n_init=n_init, s3_file_key=s3_file_key,
                            columns=columns, task_status=task_status, n_tasks=n_tasks)
                dynamodb_response = table.put_item(Item=item)
                sns_response = sns.publish(TopicArn=SNS_TOPIC_ARN, Message=sns_message, Subject=sns_subject)
                task_id += 1
