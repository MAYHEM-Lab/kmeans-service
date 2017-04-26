"""
Submit job to AWS DynamoDB and AWS Labmda asynchronously using Celery and RabbitMQ

Author: Angad Gill
"""

import boto3
import json
import time

from celery import Celery
from config import DYNAMO_URL, DYNAMO_TABLE, DYNAMO_REGION, SNS_TOPIC_ARN, CELERY_BROKER

app = Celery('jobs', broker=CELERY_BROKER)


def generate_id(job_id, task_id):
    return int('{}'.format(int(job_id))+'{0:04d}'.format(int(task_id)))


@app.task
def submit_job(n_init, n_experiments, max_k, covars, columns, s3_file_key, filename, job_id, n_tasks):
    task_status = 'pending'
    task_id = 0

    for _ in range(n_experiments):
        for k in range(1, max_k+1):
            for covar in covars:
                start_time = str(time.time())
                covar_type, covar_tied = covar.lower().split('-')
                submit_task(columns, covar_tied, covar_type, filename, job_id, k, n_init, n_tasks, s3_file_key,
                            start_time, task_id, task_status)
                task_id += 1
                time.sleep(0.5)


@app.task
def submit_task(columns, covar_tied, covar_type, filename, job_id, k, n_init, n_tasks, s3_file_key, start_time, task_id,
                task_status):
    covar_tied = covar_tied == 'tied'
    id = generate_id(job_id, task_id)
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    sns = boto3.client('sns')
    sns_payload = dict(id=id, k=k, covar_type=covar_type, covar_tied=covar_tied, n_init=n_init,
                       s3_file_key=s3_file_key, columns=columns)
    sns_message = json.dumps(sns_payload)
    sns_subject = 'web test'
    item = dict(id=id, job_id=job_id, task_id=task_id,
                # sns_message=sns_message, sns_subject=sns_subject,
                covar_type=covar_type, covar_tied=covar_tied, k=k, n_init=n_init, s3_file_key=s3_file_key,
                columns=columns, task_status=task_status, n_tasks=n_tasks, start_time=start_time,
                filename=filename)
    dynamodb_response = table.put_item(Item=item)
    sns_response = sns.publish(TopicArn=SNS_TOPIC_ARN, Message=sns_message, Subject=sns_subject)


