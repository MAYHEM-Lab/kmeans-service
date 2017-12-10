"""
Classes used to represent jobs and tasks and interact with database.

Author: Nevena Golubovic
"""
from flask_app import db


class Job(db.Document):
    job_id = db.ObjectIdField(max_length=80)  # index
    n_experiments = db.IntField(max_length=8)
    max_k = db.IntField(max_length=2)
    n_init = db.IntField(max_length=8)
    n_tasks = db.IntField(max_length=20)
    columns = db.StringField()
    filename = db.StringField()
    start_time = db.DateTimeField()  # or check db.DateTimeField()
    scale = db.BooleanField()
    s3_file_key = db.StringField()

    # TODO add index - meta = {     'indexes': [ ...


class Task(db.Document):
    job_id = db.ObjectIdField(max_length=80)  # index true?
    n_init = db.IntField(max_length=8)
    n_tasks = db.IntField(max_length=20)
    n_experiments = db.IntField()
    max_k = db.IntField()
    covars = db.StringField()
    columns = db.StringField()
    filename = db.StringField()  # needed?
    s3_file_key = db.StringField()
    start_time = db.IntField()  # or check db.DateTimeField()
    scale = db.BooleanField()
    task_id = db.StringField(max_length=80)  # number or an ID?
    aic = db.FloatField()
    bic = db.FloatField()
    labels = db.StringField()  # of ListField with WTForms??
    elapsed_time = db.DateTimeField()  # No timestamp type?
    elapsed_read_time = db.DateTimeField()
    elapsed_processing_time = db.DateTimeField()

