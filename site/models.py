"""
Classes used to represent jobs and tasks and interact with the database.

Author: Nevena Golubovic
"""
from flask_app import db


class Job(db.Model):
    job_id = db.Column(db.Integer, primary_key=True)
    n_experiments = db.Column(db.Integer)
    max_k = db.Column(db.Integer)
    n_init = db.Column(db.Integer)
    n_tasks =  db.Column(db.Integer)
    columns = db.Column(db.ARRAY(db.String))
    filename = db.Column(db.String(100))
    start_time = db.Column(db.DateTime)
    scale = db.Column(db.Boolean)
    s3_file_key = db.Column(db.String(200))


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer)
    job_id = db.Column(db.Integer)
    n_init =  db.Column(db.Integer)
    n_tasks =  db.Column(db.Integer)
    n_experiments =  db.Column(db.Integer)
    max_k =  db.Column(db.Integer)
    k =  db.Column(db.Integer)
    covar_type = db.Column(db.String(10))
    covar_tied = db.Column(db.Boolean)
    task_status = db.Column(db.String(10))
    columns = db.Column(db.ARRAY(db.String))
    filename = db.Column(db.String(100))
    s3_file_key = db.Column(db.String(200))
    start_time = db.Column(db.DateTime)
    scale = db.Column(db.Boolean)
    aic = db.Column(db.Float)
    bic = db.Column(db.Float)
    labels = db.Column(db.ARRAY(db.Integer))
    iteration_num = db.Column(db.Integer)
    centers = db.Column(db.ARRAY(db.Float))
    cluster_counts = db.Column(db.ARRAY(db.Integer))
    cluster_count_minimum = db.Column(db.Integer)
    elapsed_time = db.Column(db.Integer)
    elapsed_read_time = db.Column(db.Integer)
    elapsed_processing_time = db.Column(db.Integer)
