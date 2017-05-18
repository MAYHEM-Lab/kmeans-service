"""
All code to perform analysis tasks go here. This is run by Celery.

The purpose of the Backend Worker is to do the following:
1. Run the analysis based on the data and parameters provided in the Backedn Queue.
2. When done, update the Backend Database with the analysis results.

Architecture:
Frontend Flask server --> Celery Worker
    |           |               |   ^
    v           v               |   |
Amazon S3      MongoDB  <-------+   |
    |                           |   |
    |                           |   |
    +---------------------------+---+

Author: Angad Gill
"""
import time
from sf_kmeans import sf_kmeans
from utils import s3_to_df, float_to_str
from database import mongo_no_context_add_tasks, mongo_no_context_get_job, mongo_no_context_get_task
from database import mongo_no_context_update_task_status, mongo_no_context_update_task
from celery import Celery
from config import CELERY_BROKER
from sklearn import preprocessing


app = Celery('jobs', broker=CELERY_BROKER)


@app.task
def create_tasks(job_id, n_init, n_experiments, max_k, covars, columns, s3_file_key, scale):
    task_status = 'pending'

    # Add tasks to DB
    task_id = 0
    tasks = []
    for _ in range(n_experiments):
        for k in range(1, max_k + 1):
            for covar in covars:
                covar_type, covar_tied = covar.lower().split('-')
                covar_tied = covar_tied == 'tied'
                task = dict(task_id=task_id, covar_type=covar_type, covar_tied=covar_tied, k=k, n_init=n_init,
                            job_id=job_id,
                            columns=columns, task_status=task_status)
                tasks += [task]
                task_id += 1

    reponse = mongo_no_context_add_tasks(tasks)

    # Start workers
    task_id = 0
    for _ in range(n_experiments):
        for k in range(1, max_k + 1):
            for covar in covars:
                covar_type, covar_tied = covar.lower().split('-')
                covar_tied = covar_tied == 'tied'
                work_task.delay(job_id, task_id, k, covar_type, covar_tied, n_init, s3_file_key, columns, scale)
                task_id += 1

@app.task
def rerun_task(job_id, task_id):
    job = mongo_no_context_get_job(job_id)
    # task = job['tasks'][task_id]
    task = mongo_no_context_get_task(job_id, task_id)
    k = task['k']
    covar_type = task['covar_type']
    covar_tied = task['covar_tied']
    n_init = task['n_init']
    s3_file_key = job['s3_file_key']
    columns = job['columns']
    scale = job['scale']
    work_task.delay(job_id, task_id, k, covar_type, covar_tied, n_init, s3_file_key, columns, scale)
    response = mongo_no_context_update_task_status(job_id, task_id, 'pending')


def run_kmeans(data, n_clusters, covar_type, covar_tied, n_init):
    kmeans = sf_kmeans.SF_KMeans(n_clusters=n_clusters, covar_type=covar_type, covar_tied=covar_tied, n_init=n_init,
                                 verbose=0)
    kmeans.fit(data)
    aic, bic = kmeans.aic(data), kmeans.bic(data)
    labels = [int(l) for l in kmeans.labels_]
    return aic, bic, labels


@app.task
def work_task(job_id, task_id, k, covar_type, covar_tied, n_init, s3_file_key, columns, scale):
    try:
        start_time = time.time()
        start_read_time = time.time()
        data = s3_to_df(s3_file_key)
        elapsed_read_time = time.time() - start_read_time

        start_processing_time = time.time()
        data = data.loc[:, columns]
        if scale:
            data = preprocessing.scale(data)
        aic, bic, labels = run_kmeans(data, k, covar_type, covar_tied, n_init)
        print('job_id:{}, bic:{}'.format(job_id, bic))
        elapsed_processing_time = time.time() - start_processing_time

        elapsed_time = time.time() - start_time

        elapsed_time = float_to_str(elapsed_time)
        elapsed_read_time = float_to_str(elapsed_read_time)
        elapsed_processing_time = float_to_str(elapsed_processing_time)
        response = mongo_no_context_update_task(job_id, task_id, aic, bic, labels, elapsed_time, elapsed_read_time, elapsed_processing_time)
    except Exception as e:
        response = mongo_no_context_update_task_status(job_id, task_id, 'error')
        raise Exception(e)
    return 'Done'



