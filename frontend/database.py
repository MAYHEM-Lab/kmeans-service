"""
Wrapper function for MongoDB

Author: Angad Gill
"""
import time
from flask_app import mongo
from bson.objectid import ObjectId
from pymongo import MongoClient

from config import MONGO_DBNAME, MONGO_URI


def add_job_to_mongo(job_id):
    mongo.db.jobs.insert({'job_id': job_id})


def mongo_job_id_exists(job_id):
    key = dict(_id=ObjectId(job_id))
    count = mongo.db.jobs.count(key)
    return count == 1


def mongo_get_job(job_id):
    key = dict(_id=ObjectId(job_id))
    response = mongo.db.jobs.find_one(key)
    return response


def mongo_no_context_get_job(job_id):
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DBNAME]
    key = dict(_id=ObjectId(job_id))
    response = db.jobs.find_one(key)
    return response


def mongo_get_tasks(job_id):
    key = dict(job_id=job_id)
    response = list(mongo.db.tasks.find(key))
    return response


def mongo_get_task(job_id, task_id):
    key = dict(job_id=job_id, task_id=task_id)
    response = mongo.db.tasks.find_one(key)
    return response

def mongo_no_context_get_task(job_id, task_id):
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DBNAME]
    key = dict(job_id=job_id, task_id=task_id)
    response = db.tasks.find_one(key)
    return response


def mongo_add_s3_file_key(job_id, s3_file_key):
    response = mongo.db.jobs.update_one({'_id': ObjectId(job_id)}, {'$set': {'s3_file_key': s3_file_key}})
    return response


def mongo_create_job(n_experiments, max_k, columns, filename, n_tasks, scale):
    key = dict(n_experiments=n_experiments, max_k=max_k, columns=columns, filename=filename,
               # tasks=[],
               n_tasks=n_tasks, start_time=time.time(), scale=scale)
    response = mongo.db.jobs.insert_one(key)
    job_id = str(response.inserted_id)
    return job_id


def mongo_add_tasks(tasks):
    # Tasks must already have a field for job_id
    response = mongo.db.tasks.insert_many(tasks)
    return response


def mongo_no_context_add_tasks(tasks):
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DBNAME]
    response = db.tasks.insert_many(tasks)
    return response


def mongo_update_task(job_id, task_id, aic, bic, labels, elapsed_time, elapsed_read_time, elapsed_processing_time):
    response = mongo.db.tasks.update_one(
        {'job_id': job_id, 'task_id': task_id},
        {'$set': {'task_status': 'done', 'aic': aic, 'bic': bic, 'labels': labels,
                  'elapsed_time': elapsed_time, 'elapsed_read_time': elapsed_read_time,
                  'elapsed_processing_time': elapsed_processing_time}})
    return response


def mongo_no_context_update_task(job_id, task_id, aic, bic, labels, elapsed_time, elapsed_read_time, elapsed_processing_time):
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DBNAME]
    response = db.tasks.update_one(
        {'job_id': job_id, 'task_id': task_id},
        {'$set': {'task_status': 'done', 'aic': aic, 'bic': bic, 'labels': labels,
                  'elapsed_time': elapsed_time, 'elapsed_read_time': elapsed_read_time,
                  'elapsed_processing_time': elapsed_processing_time}})
    return response


def mongo_update_task_status(job_id, task_id, status):
    response = mongo.db.tasks.update_one(
        {'job_id': job_id, 'task_id': task_id},
        {'$set': {'task_status': status}})
    return response


def mongo_no_context_update_task_status(job_id, task_id, status):
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DBNAME]
    response = db.jobs.update_one(
        {'job_id': job_id, 'task_id': task_id},
        {'$set': {'task_status': status}})
    return response
