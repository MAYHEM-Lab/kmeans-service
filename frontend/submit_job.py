"""
Submit job to AWS DynamoDB and AWS Lambda or Celery Worker asynchronously using Celery and RabbitMQ

Author: Angad Gill
"""
import boto3
from botocore.exceptions import ClientError

import json
import time

from celery import Celery
from config import DYNAMO_URL, DYNAMO_TABLE, DYNAMO_REGION, SNS_TOPIC_ARN, CELERY_BROKER
from work_task import work_task

from utils import put_item_by_item
from utils import generate_id

from config import DYNAMO_RETRY_EXCEPTIONS


app = Celery('jobs', broker=CELERY_BROKER)
USE_LAMBDA = False


@app.task
def submit_job(n_init, n_experiments, max_k, covars, columns, s3_file_key, filename, job_id, n_tasks):
    task_status = 'pending'
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    if USE_LAMBDA:
        sns = boto3.client('sns')

    task_id = 0
    retries = 0
    max_retries = 10

    with table.batch_writer() as batch:
        for _ in range(n_experiments):
            for k in range(1, max_k+1):
                for covar in covars:
                    start_time = str(time.time())
                    covar_type, covar_tied = covar.lower().split('-')
                    covar_tied = covar_tied == 'tied'
                    id = generate_id(job_id, task_id)
                    sns_payload = dict(id=id, k=k, covar_type=covar_type, covar_tied=covar_tied, n_init=n_init,
                                       s3_file_key=s3_file_key, columns=columns)
                    sns_message = json.dumps(sns_payload)
                    item = dict(id=id, job_id=job_id, task_id=task_id,
                                covar_type=covar_type, covar_tied=covar_tied, k=k, n_init=n_init, s3_file_key=s3_file_key,
                                columns=columns, task_status=task_status, n_tasks=n_tasks, start_time=start_time,
                                filename=filename)

                    # Submit task to the queue
                    if USE_LAMBDA:
                        sns_subject = 'web test'
                        sns_response = sns.publish(TopicArn=SNS_TOPIC_ARN, Message=sns_message, Subject=sns_subject)
                    else:
                        work_task.delay(sns_message)

                    # Create task entry in DynamoDB
                    success = False
                    while not success:
                        try:
                            batch.put_item(Item=item)
                            retries = 0
                            success = True
                        except ClientError as err:
                            if err.response['Error']['Code'] not in DYNAMO_RETRY_EXCEPTIONS:
                                raise err
                            if retries > max_retries:
                                raise Exception('Maximum retries reached with {}'.format(err.response['Error']['Code']))
                            print('submit_job. retry count: {}'.format(retries))
                            retries += 1
                            time.sleep(2 ** retries)

                    task_id += 1
                    # time.sleep(0.5)


@app.task
def submit_task(columns, covar_tied, covar_type, filename, job_id, k, n_init, n_tasks, s3_file_key, start_time, task_id,
                task_status):
    covar_tied = covar_tied == 'tied'
    id = generate_id(job_id, task_id)
    sns_payload = dict(id=id, k=k, covar_type=covar_type, covar_tied=covar_tied, n_init=n_init,
                       s3_file_key=s3_file_key, columns=columns)
    sns_message = json.dumps(sns_payload)
    item = dict(id=id, job_id=job_id, task_id=task_id,
                covar_type=covar_type, covar_tied=covar_tied, k=k, n_init=n_init, s3_file_key=s3_file_key,
                columns=columns, task_status=task_status, n_tasks=n_tasks, start_time=start_time,
                filename=filename)
    put_item_by_item(item)
    if USE_LAMBDA:
        sns = boto3.client('sns')
        sns_subject = 'web test'
        sns_response = sns.publish(TopicArn=SNS_TOPIC_ARN, Message=sns_message, Subject=sns_subject)
    else:
        work_task(sns_message)



