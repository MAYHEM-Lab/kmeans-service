"""
All global Python variables are in this file.

Author: Angad Gill, Nevena Golubovic
"""
S3_BUCKET = 'kmeansservice'
EUCA_S3_HOST = "s3.cloud.aristotle.ucsb.edu"
EUCA_S3_PATH = "/services/Walrus"
UPLOAD_FOLDER = 'data'
ALLOWED_EXTENSIONS = set(['csv'])
EXCLUDE_COLUMNS = ['longitude', 'latitude']  # must be lower case
SPATIAL_COLUMNS = ['longitude', 'latitude']  # must be lower case
MONGO_DBNAME = 'kmeansservice'
FLASK_SECRET_KEY = 'change_this_key'
CELERY_BROKER = 'amqp://localhost//'
POSTGRES_URI = 'postgres://username:password@host:port/db'
EUCA_KEY_ID = ""
EUCA_SECRET_KEY = ""
SNS_TOPIC_ARN = "arn:aws:sns:us-west-2:603495292017:kmeansservice"