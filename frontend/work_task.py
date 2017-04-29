"""
Code triggered by Celery.

Purpose of this code:
1) Run the analysis based on the data and parameters provided by Celery
2) When done, update DynamoDB with the analysis results

Architecture:
Frontend Flask server --> Amazon SNS --> Celery Worker
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
import time
from sf_kmeans import sf_kmeans

from utils import s3_to_df, update_at_dynamo, update_at_dynamo_error, float_to_str
from config import CELERY_BROKER

from celery import Celery


app = Celery('workers', broker=CELERY_BROKER)


def run_kmeans(data, n_clusters, covar_type, covar_tied, n_init):
    kmeans = sf_kmeans.SF_KMeans(n_clusters=n_clusters, covar_type=covar_type, covar_tied=covar_tied, n_init=n_init,
                                 verbose=0)
    kmeans.fit(data)
    aic, bic = kmeans.aic(data), kmeans.bic(data)
    aic, bic = float_to_str(aic), float_to_str(bic)
    labels = [int(l) for l in kmeans.labels_]
    return aic, bic, labels


@app.task
def work_task(message):
    start_time = time.time()
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

        start_read_time = time.time()
        data = s3_to_df(s3_file_key)
        elapsed_read_time = time.time() - start_read_time

        start_processing_time = time.time()
        data = data.loc[:, columns]
        aic, bic, labels = run_kmeans(data, k, covar_type, covar_tied, n_init)
        print('id:{}, bic:{}'.format(id, bic))
        elapsed_processing_time = time.time() - start_processing_time

        elapsed_time = time.time() - start_time

        elapsed_time = float_to_str(elapsed_time)
        elapsed_read_time = float_to_str(elapsed_read_time)
        elapsed_processing_time = float_to_str(elapsed_processing_time)
        response = update_at_dynamo(id, aic, bic, elapsed_time, elapsed_read_time, elapsed_processing_time, labels)
    except Exception as e:
        response = update_at_dynamo_error(id)
        raise Exception(e)
    return message



