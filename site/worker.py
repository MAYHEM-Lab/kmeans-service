"""
All code to perform analysis tasks goes here. This is run by Celery.

The purpose of the Backend Worker is to do the following:
1. Run the analysis based on the parameters provided in the Backend Queue.
2. When done, update the Backend Database with the analysis results.

Architecture:
Frontend Flask server --> Celery Worker
    |           |               |   ^
    v           v               |   |
Amazon S3      MongoDB  <-------+   |
    |                           |   |
    |                           |   |
    +---------------------------+---+

Author: Angad Gill, Nevena Golubovic
"""
from datetime import datetime
from sf_kmeans import sf_kmeans
from utils import s3_to_df
# from celery import Celery
from config import CELERY_BROKER
from sklearn_lite import preprocessing
from models import Job, Task
from flask_app import db
import numpy as np
import os, json

S3_BUCKET = os.environ['S3_BUCKET']

# app = Celery('jobs', broker=CELERY_BROKER)


# TODO pass the task id instead of all the params. do this everywhere.
# @app.task
# def rerun_task(job_id, task_id):
#     """
#     Reruns a specific task from a job.
#     Sets the task status to 'pending' and triggers an asynchronous function to
#     process the task.

#     Parameters
#     ----------
#     job_id: str
#     task_id: int

#     Returns
#     -------
#     None
#     """
#     job = db.session.query(Job).filter_by(job_id=job_id).first()
#     task = db.session.query(Task).filter_by(job_id=job_id, task_id=task_id).first()
#     k = task.k
#     covar_type = task.covar_type
#     covar_tied = task.covar_tied
#     n_init = task.n_init
#     s3_file_key = job.s3_file_key
#     columns = job.columns
#     scale = job.scale
#     task.task_status = 'pending'
#     db.session.commit()
#     work_task.delay(job_id, task_id, k, covar_type, covar_tied, n_init,
#                     s3_file_key, columns, scale)

def lambda_handler(event, context):
    message = event['Records'][0]['Sns']['Message']
    task = json.loads(message)
    job_id = task['job_id']
    task_id = task['task_id']
    k = task['k']
    covar_type = task['covar_type']
    covar_tied = task['covar_tied']
    n_init = task['n_init']
    s3_file_key = task['s3_file_key']
    columns = task['columns']
    scale = task['scale']
    response = work_task(job_id, task_id, k, covar_type, covar_tied, n_init, s3_file_key, columns, scale)
    return {"job_id": job_id, "task_id": task_id, "response": response}

def run_kmeans(data, n_clusters, covar_type, covar_tied, n_init):
    """
    Creates an instance of the `kmeans` object and runs `fit` using the data.

    Parameters
    ----------
    data: Pandas DataFrame
        Data containing only the columns to be used for `fit`
    n_clusters: int
    covar_type: str
    covar_tied: bool
    n_init: int

    Returns
    -------
    float, float, list(int)
        aic, bic, labels
    """
    kmeans = sf_kmeans.SF_KMeans(n_clusters=n_clusters, covar_type=covar_type,
                                 covar_tied=covar_tied, n_init=n_init,
                                 verbose=0)
    kmeans.fit(data)
    aic, bic = kmeans.aic(data), kmeans.bic(data)
    labels = [int(l) for l in kmeans.labels_]
    return aic, bic, labels, kmeans.iteration_num, kmeans.cluster_centers_


# @app.task
def work_task(job_id, task_id, k, covar_type, covar_tied, n_init, s3_file_key, columns, scale):
    """
    Performs the processing needed to complete a task.
    Downloads the task parameters and the file. Runs K-Means `fit` and
    updates the database with results.
    Sets `task_status` to 'done' if completed successfully, else to 'error'.

    Parameters
    ----------
    job_id: str
    task_id: int
    k: int
    covar_type: str
    covar_tied: bool
    n_init: int
    s3_file_key: str
    columns: list(str)
    scale: bool

    Returns
    -------
    str
        'Done'
    """
    try:
        print(' working on: job_id:{}, task_id:{}'.format(job_id, task_id))
        start_time = datetime.utcnow()
        data = s3_to_df(s3_file_key)
        elapsed_read_time = (datetime.utcnow() - start_time).total_seconds()
        start_processing_time = datetime.utcnow()
        data = data.loc[:, columns]
        if scale:
            data = preprocessing.scale(data)

        aic, bic, labels, iteration_num, centers = run_kmeans(data, k,
            covar_type, covar_tied, n_init)

        elapsed_processing_time = (datetime.utcnow() -
                                   start_processing_time).total_seconds()
        elapsed_time = (datetime.utcnow() - start_time).total_seconds()
        elapsed_processing_time = elapsed_processing_time
        cluster_counts = (np.sort(np.bincount(labels))[::-1]).tolist()
        cluster_count_minimum = int(np.min(cluster_counts))

        db.session.query(Task).filter_by(job_id=job_id, task_id=task_id).update(
            dict(
                task_status='done', aic=aic, bic=bic, labels=labels,
                iteration_num=iteration_num, centers=((centers).tolist()),
                elapsed_time=elapsed_time, elapsed_read_time=elapsed_read_time,
                elapsed_processing_time=elapsed_processing_time,
                cluster_counts=cluster_counts,
                cluster_count_minimum=cluster_count_minimum))
        db.session.commit()
        total_time = (datetime.utcnow() - start_time).total_seconds()
        print("Time stamp : {}".format(datetime.utcnow()))
        print('total time : {}'.format(total_time))
    except Exception as e:
        db.session.query(Task).filter_by(job_id=job_id,
                                     task_id=task_id).update(
            task_status='error')
        raise e
    return 'Done'