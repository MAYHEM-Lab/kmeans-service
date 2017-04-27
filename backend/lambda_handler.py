"""
Code run on Amazon Lambda that is triggered by Amazon SNS by messages published by the frontend server.

Purpose of this code:
1) Run the analysis based on the data and parameters provided in the SNS message
2) When done, update DynamoDB with the analysis results

Architecture:
Frontend Flask server --> Amazon SNS --> Amazon Lambda
    |           |                           |   ^
    v           v                           |   |
Amazon         Amazon    <------------------+   |
S3             DynamoDB                         |
    |                                           |
    +-------------------------------------------+

Author: Angad Gill
"""

from __future__ import print_function

import json
import boto3
import time
import numpy as np
import pandas as pd
from sf_kmeans import sf_kmeans

DYNAMO_URL = 'https://dynamodb.us-west-1.amazonaws.com'
DYNAMO_TABLE = 'kmeansservice'
DYNAMO_REGION = 'us-west-1'
S3_BUCKET = 'kmeansservice'


def test_data():
    k, d, N = 3, 2, 1000
    centers = np.random.rand(k, d)
    x = np.array([np.random.normal(loc=c,scale=0.05,size=(N, d)) for c in centers])
    x = x.reshape(N*k, d)
    return x


def float_to_str(num):
    return '{:.4f}'.format(num)


def run_kmeans(data, n_clusters, covar_type, covar_tied, n_init):
    kmeans = sf_kmeans.SF_KMeans(n_clusters=n_clusters, covar_type=covar_type, covar_tied=covar_tied, n_init=n_init,
                                 verbose=0)
    kmeans.fit(data)
    aic, bic = kmeans.aic(data), kmeans.bic(data)
    aic, bic = float_to_str(aic), float_to_str(bic)
    labels = list(kmeans.labels_)
    return aic, bic, labels


def update_at_dynamo(id, aic, bic, elapsed_time, elapsed_read_time, elapsed_processing_time, labels):
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    key = {'id': id}
    response = table.update_item(Key=key,
                                 UpdateExpression='SET aic=:val1, bic=:val2, elapsed_time=:val3, task_status=:val4, '
                                                  'elapsed_read_time=:val5, elapsed_processing_time=:val6, '
                                                  'labels=:val7',
                                 ExpressionAttributeValues={':val1': aic, ':val2': bic, ':val3': elapsed_time,
                                                            ':val4':'done', ':val5':elapsed_read_time,
                                                            ':val6':elapsed_processing_time, ':val7':labels})
    return response

def update_at_dynamo_error(id):
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    key = {'id': id}
    response = table.update_item(Key=key,
                                 UpdateExpression='SET task_status = :val1', ExpressionAttributeValues={':val1': 'error'})
    return response


def s3_to_df(s3_file_key):
    s3 = boto3.client('s3')
    file_name = '/tmp/data_file'
    s3.download_file(S3_BUCKET, s3_file_key, file_name)
    return pd.read_csv(file_name)


def lambda_handler(event, context):
    start_time = time.time()
    print("Received event: " + json.dumps(event, indent=2))
    message = event['Records'][0]['Sns']['Message']
    args = json.loads(message)
    print('args:', args)
    id = args['id']
    try:
        covar_type = args['covar_type']
        covar_tied = args['covar_tied']
        n_init = int(args['n_init'])
        k = int(args['k'])
        s3_file_key = args['s3_file_key']
        columns = args['columns']

        # data = test_data()
        start_read_time = time.time()
        data = s3_to_df(s3_file_key)
        elapsed_read_time = time.time() - start_read_time

        start_processing_time = time.time()
        data = data.loc[:, columns]
        aic, bic, labels = run_kmeans(data, k, covar_type, covar_tied, n_init)
        elapsed_processing_time = time.time() - start_processing_time

        elapsed_time = time.time() - start_time

        elapsed_time = float_to_str(elapsed_time)
        elapsed_read_time = float_to_str(elapsed_read_time)
        elapsed_processing_time = float_to_str(elapsed_processing_time)
        # time.sleep(5)

        response = update_at_dynamo(id, aic, bic, elapsed_time, elapsed_read_time, elapsed_processing_time, labels)
    except Exception as e:
        response = update_at_dynamo_error(id)
        # print(e)
        raise Exception(e)
    return message



