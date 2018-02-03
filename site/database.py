"""
Wrapper function for MongoDB.

All function used withing Flask must use the context object. Outside of Flask, the "no_context" functions must be used.

Author: Angad Gill
"""
import time
#from flask_app import mongo
from bson.objectid import ObjectId
from pymongo import MongoClient
import numpy as np

from config import MONGO_DBNAME, MONGO_URI


def mongo_job_id_exists(job_id):
    """
    Check if a job_id exists in MongoDB.
    This uses the `mongo` context object from Flask.

    Parameters
    ----------
    job_id: str

    Returns
    -------
    bool
        True if job_id exists. False otherwise.
    """
    key = dict(_id=ObjectId(job_id))
    count = mongo.db.jobs.count(key)
    return count == 1


def mongo_get_job(job_id):
    """
    Get job object from MongoDB.
    This uses the `mongo` context object from Flask.

    Parameters
    ----------
    job_id: str

    Returns
    -------
    dict
        Job object
    """
    key = dict(_id=ObjectId(job_id))
    response = mongo.db.jobs.find_one(key)
    return response


def mongo_no_context_get_job(job_id):
    """
    Get job object from MongoDB.
    This does not use context object from Flask.

    Parameters
    ----------
    job_id: str

    Returns
    -------
    dict
        Job object
    """
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DBNAME]
    key = dict(_id=ObjectId(job_id))
    response = db.jobs.find_one(key)
    return response


def mongo_get_tasks(job_id):
    """
    Get all tasks for a job from MongoDB.
    This uses the `mongo` context object from Flask.

    Parameters
    ----------
    job_id: str

    Returns
    -------
    list(dict)
        All tasks for given job
    """
    key = dict(job_id=job_id)
    response = list(mongo.db.tasks.find(key))
    return response


def mongo_no_context_get_tasks(job_id):
    """
    Get all tasks for a job from MongoDB.
    This does not use context object from Flask.

    Parameters
    ----------
    job_id: str

    Returns
    -------
    list(dict)
        All task objects for given job
    """
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DBNAME]
    key = dict(job_id=job_id)
    response = list(db.tasks.find(key))
    return response


def mongo_get_task(job_id, task_id):
    """
    Get a task from MongoDB.
    This uses the `mongo` context object from Flask.

    Parameters
    ----------
    job_id: str
    task_id: int

    Returns
    -------
    dict
        task object
    """
    key = dict(job_id=job_id, task_id=task_id)
    response = mongo.db.tasks.find_one(key)
    return response


def mongo_no_context_get_task(job_id, task_id):
    """
    Get a task from MongoDB.
    This does not use context object from Flask.

    Parameters
    ----------
    job_id: str
    task_id: int

    Returns
    -------
    dict
        task object
    """
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DBNAME]
    key = dict(job_id=job_id, task_id=task_id)
    response = db.tasks.find_one(key)
    return response


def mongo_get_task_by_args(job_id, covar_type, covar_tied, k):
    """
    Get one task from MongoDB that match the function arguments.
    This uses the `mongo` context object from Flask.

    Parameters
    ----------
    job_id: str
    covar_type: str
    covar_tied: bool
    k: int

    Returns
    -------
    dict
        task object

    """
    key = dict(job_id=job_id, covar_type=covar_type, covar_tied=covar_tied, k=k)
    print(key)
    response = mongo.db.tasks.find_one(key)
    return response


def mongo_get_tasks_by_args(job_id, covar_type, covar_tied, k):
    """
    Get all tasks from MongoDB that match the fuction arguments.
    This uses the `mongo` context object from Flask.

    Parameters
    ----------
    job_id: str
    covar_type: str
    covar_tied: bool
    k: int

    Returns
    -------
    list(dict)
        all matching task objects

    """
    key = dict(job_id=job_id, covar_type=covar_type, covar_tied=covar_tied, k=k)
    response = list(mongo.db.tasks.find(key))
    return response


def mongo_add_s3_file_key(job_id, s3_file_key):
    """
    Adds 's3_file_key' key-value to job object in MongoDB.
    This uses the `mongo` context object from Flask.

    Parameters
    ----------
    job_id: str
    s3_file_key: str

    Returns
    -------
    None

    """
    response = mongo.db.jobs.update_one({'_id': ObjectId(job_id)}, {'$set': {'s3_file_key': s3_file_key}})
    return response


def mongo_create_job(n_experiments, max_k, columns, filename, n_tasks, scale):
    """
    Create a new job entry on MongoDB. All function parameters are used for the clustering analysis.

    This uses the `mongo` context object from Flask.

    Parameters
    ----------
    n_experiments: int
        Number of experiments to run using job parameteres.
    max_k: int
        Maximum number of clusters to fit to the data.
    columns: list(str)
        All columns from the data file to use for clustering.
    filename: str
        Name of the user data file.
    n_tasks: int
        Number of tasks created for this job.
    scale: bool
        Whether or not to scale the data before clustering.

    Returns
    -------
    str
        job id generated by MongoDB

    """
    key = dict(n_experiments=n_experiments, max_k=max_k, columns=columns, filename=filename,
               n_tasks=n_tasks, start_time=time.time(), scale=scale)
    response = mongo.db.jobs.insert_one(key)
    job_id = str(response.inserted_id)
    return job_id


def mongo_add_tasks(tasks):
    """
    Add tasks to MongoDB.
    This uses the `mongo` context object from Flask.

    Parameters
    ----------
    tasks: list(dict)
        List of all task objects.

    Returns
    -------
    dict
        response from MongoDB.
    """
    response = mongo.db.tasks.insert_many(tasks)
    return response


def mongo_no_context_add_tasks(tasks):
    """
    Add tasks to MongoDB.
    This does not use context object from Flask.

    Parameters
    ----------
    tasks: list(dict)
        List of all task objects.

    Returns
    -------
    dict
        response from MongoDB.
    """
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DBNAME]
    response = db.tasks.insert_many(tasks)
    return response


def mongo_update_task(job_id, task_id, aic, bic, labels, elapsed_time, elapsed_read_time, elapsed_processing_time):
    """
    Update task object on MongoDB.
    This uses the `mongo` context object from Flask.

    Parameters
    ----------
    job_id: str
    task_id: int
    aic: float
    bic: float
    labels: list(int)
    elapsed_time: str
        Epoch time converted to str
    elapsed_read_time: str
        Epoch time converted to str
    elapsed_processing_time: str
        Epoch time converted to str

    Returns
    -------
    dict
        response from MongoDB.
    """
    response = mongo.db.tasks.update_one(
        {'job_id': job_id, 'task_id': task_id},
        {'$set': {'task_status': 'done', 'aic': aic, 'bic': bic, 'labels': labels,
                  'elapsed_time': elapsed_time, 'elapsed_read_time': elapsed_read_time,
                  'elapsed_processing_time': elapsed_processing_time}})
    return response


def mongo_no_context_update_task(job_id, task_id, aic, bic, labels, elapsed_time, elapsed_read_time,
                                 elapsed_processing_time):
    """
    Update task object on MongoDB.
    This does not use context object from Flask.

    Parameters
    ----------
    job_id: str
    task_id: int
    aic: float
    bic: float
    labels: list(int)
    elapsed_time: str
        Epoch time converted to str
    elapsed_read_time: str
        Epoch time converted to str
    elapsed_processing_time: str
        Epoch time converted to str

    Returns
    -------
    dict
        response from MongoDB.
    """
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DBNAME]
    cluster_counts = np.sort(np.bincount(labels))[::-1]
    cluster_count_minimum = np.min(cluster_counts)
    response = db.tasks.update_one(
        {'job_id': job_id, 'task_id': task_id},
        {'$set': {'task_status': 'done', 'aic': aic, 'bic': bic, 'labels': labels,
                  'elapsed_time': elapsed_time, 'elapsed_read_time': elapsed_read_time,
                  'elapsed_processing_time': elapsed_processing_time,
                  'cluster_counts': cluster_counts, 'cluster_count_minimum':
                      cluster_count_minimum}})
    return response


def mongo_update_task_status(job_id, task_id, status):
    """
    Update 'task_status' value in task object.
    This uses the `mongo` context object from Flask.

    Parameters
    ----------
    job_id: str
    task_id: int
    status: str

    Returns
    -------
    dict
        response from MongoDB.
    """
    response = mongo.db.tasks.update_one(
        {'job_id': job_id, 'task_id': task_id},
        {'$set': {'task_status': status}})
    return response


def mongo_no_context_update_task_status(job_id, task_id, status):
    """
    Update 'task_status' value in task object.
    This does not use context object from Flask.

    Parameters
    ----------
    job_id: str
    task_id: int
    status: str

    Returns
    -------
    dict
        response from MongoDB.
    """
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DBNAME]
    response = db.tasks.update_one(
        {'job_id': job_id, 'task_id': task_id},
        {'$set': {'task_status': status}})
    return response
