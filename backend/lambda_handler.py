"""
Code run on Amazon Lambda that is triggered by Amazon SNS by messages published by the frontend server.

Purpose of this code:
1) Run the analysis based on the data and parameters provided in the SNS message
2) When done, update DynamoDB with the analysis results

Message format:
{"covar_type":"full", "covar_tied":"true", "n_init":10, "data_s3":"some_url", "k":2}

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
from sf_kmeans import sf_kmeans

DYNAMO_URL = 'https://dynamodb.us-west-1.amazonaws.com'
DYNAMO_TABLE = 'test_table'
DYNAMO_REGION = 'us-west-1'


def test_data():
    k, d, N = 3, 2, 1000
    centers = np.random.rand(k, d)
    x = np.array([np.random.normal(loc=c,scale=0.05,size=(N, d)) for c in centers])
    x = x.reshape(N*k, d)
    return x


def float_to_str(num):
    return '{:.4f}'.format(num)


def run_kmeans(n_clusters, covar_type, covar_tied, n_init):
    kmeans = sf_kmeans.SF_KMeans(n_clusters=n_clusters, covar_type=covar_type, covar_tied=covar_tied, n_init=n_init,
                                 verbose=0)
    data = test_data()
    kmeans.fit(data)
    aic, bic = kmeans.aic(data), kmeans.bic(data)
    aic, bic = float_to_str(aic), float_to_str(bic)
    return aic, bic


def update_at_dynamo(id, aic, bic, elapsed_time):
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION,
                              endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    key = {'id': id}
    response = table.update_item(Key=key,
                                 UpdateExpression='SET aic = :val1, bic=:val2, elapsed_time=:val3',
                                 ExpressionAttributeValues={':val1': aic, ':val2': bic, ':val3': elapsed_time})
    return response


def lambda_handler(event, context):
    start_time = time.time()

    print("Received event: " + json.dumps(event, indent=2))
    message = event['Records'][0]['Sns']['Message']

    args = json.loads(message)
    print('args:', args)

    id = args['id']
    covar_type = args['covar_type']
    covar_tied = args['covar_tied']
    n_init = int(args['n_init'])
    k = int(args['k'])

    aic, bic = run_kmeans(k, covar_type, covar_tied, n_init)
    elapsed_time = time.time() - start_time
    elapsed_time = float_to_str(elapsed_time)
    time.sleep(5)

    response = update_at_dynamo(id, aic, bic, elapsed_time)

    return message



