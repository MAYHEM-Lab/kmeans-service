"""
Initialize and configure Flask app here

Author: Angad Gill, Nevena Golubovic
"""
from flask import Flask
from flask_mongoengine import MongoEngine

from config import MONGO_URI, MONGO_DBNAME, FLASK_SECRET_KEY

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config['MONGODB_SETTINGS'] = {
    'db': MONGO_DBNAME,
    'host': MONGO_URI
}
db = MongoEngine(app)
