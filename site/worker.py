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
from time import time
from sf_kmeans import sf_kmeans
from utils import s3_to_df, float_to_str
from celery import Celery
from config import CELERY_BROKER
from sklearn import preprocessing
from db import Job, Task

app = Celery('jobs', broker=CELERY_BROKER)


@app.task
def create_tasks(job_id, n_init, n_experiments, max_k, covars, columns, s3_file_key, scale):
    """
    Creates all the tasks needed to complete a job.
    Adds database entries for each task and triggers an asynchronous
    functions to process the task.

    Parameters
    ----------
    job_id: str
    n_init: int
    n_experiments: int
    max_k: int
    covars: list(str)
    columns: list(str)
    s3_file_key: str
    scale: bool

    Returns
    -------
    None
    """
    task_status = 'pending'

    # Add tasks to DB
    task_id = 0
    tasks = []
    print("creating tasks")
    for _ in range(n_experiments):
        for k in range(1, max_k + 1):
            for covar in covars:
                covar_type, covar_tied = covar.lower().split('-')
                covar_tied = covar_tied == 'tied'
                task = Task(task_id=task_id, covar_type=covar_type,
                         covar_tied=covar_tied, k=k, n_init=n_init,
                            job_id=job_id,
                            columns=columns, task_status=task_status)
                tasks += [task]
                task_id += 1

    response = Task.objects.insert(tasks)
    print(response)

    # Start workers
    task_id = 0
    for _ in range(n_experiments):
        for k in range(1, max_k + 1):
            for covar in covars:
                covar_type, covar_tied = covar.lower().split('-')
                covar_tied = covar_tied == 'tied'
                work_task.delay(job_id, task_id, k, covar_type, covar_tied,
                                n_init, s3_file_key, columns, scale)
                task_id += 1

@app.task
def rerun_task(job_id, task_id):
    """
    Reruns a specific task from a job.
    Sets the task status to 'pending' and triggers an asynchronous function to
    process the task.

    Parameters
    ----------
    job_id: str
    task_id: int

    Returns
    -------
    None
    """
    job = mongo_no_context_get_job(job_id)
    task = mongo_no_context_get_task(job_id, task_id)
    k = task['k']
    covar_type = task['covar_type']
    covar_tied = task['covar_tied']
    n_init = task['n_init']
    s3_file_key = job['s3_file_key']
    columns = job['columns']
    scale = job.get('scale', False)
    response = mongo_no_context_update_task_status(job_id, task_id, 'pending')
    work_task.delay(job_id, task_id, k, covar_type, covar_tied, n_init,
                    s3_file_key, columns, scale)


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
    return aic, bic, labels


@app.task
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

        aic, bic, labels = run_kmeans(data, k, covar_type, covar_tied, n_init)

        elapsed_processing_time = (datetime.utcnow() -
                                   start_processing_time).total_seconds()
        elapsed_time = (datetime.utcnow() - start_time).total_seconds()
        elapsed_processing_time = elapsed_processing_time



        response = Task.objects(job_id=job_id, task_id=task_id).update_one(
            task_status='done', aic=aic, bic=bic, labels=labels,
            elapsed_time=elapsed_time, elapsed_read_time=elapsed_read_time,
            elapsed_processing_time=elapsed_processing_time)
        print(response)
    except Exception as e:
        response = Task.objects(job_id=job_id, task_id=task_id).update_one(
            task_status='error')
        raise e
    return 'Done'



