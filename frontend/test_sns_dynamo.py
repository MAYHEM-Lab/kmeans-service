"""
Message format:
{"covar_type":"full", "covar_tied":"true", "n_init":10, "data_s3":"some_url", "k":2}

"""


import boto3
import json

DYNAMO_URL = 'https://dynamodb.us-west-1.amazonaws.com'
DYNAMO_TABLE = 'test_table'
DYNAMO_REGION = 'us-west-1'
SNS_TOPIC_ARN = 'arn:aws:sns:us-west-1:000169391513:kmeans-service'


def send_to_dynamo(id, job_id, task_id, covar_tied, covar_type, k, message, n_init, subject):
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION,
                              endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    response = table.put_item(
        Item={'id': id, 'job_id': job_id, 'task_id': task_id, 'message': message, 'subject': subject,
              'covar_type': covar_type, 'covar_tied': covar_tied, 'k': k, 'n_init': n_init})
    return response


def send_to_sns(message, subject):
    sns = boto3.client('sns')
    response = sns.publish(TopicArn=SNS_TOPIC_ARN, Message=message, Subject=subject)
    return response


if __name__ == '__main__':
    job_id = 3456
    task_id = 1
    id = int('{}{}'.format(job_id, task_id))

    covar_tied = True
    covar_type = 'diag'
    k = 3
    n_init = 10

    payload = {'id': id, 'k': k, 'covar_type': covar_type, 'covar_tied': covar_tied, 'n_init': n_init}
    message = json.dumps(payload)
    subject = 'script test'

    print send_to_dynamo(id, job_id, task_id, covar_tied, covar_type, k, message, n_init, subject)
    print send_to_sns(message, subject)
