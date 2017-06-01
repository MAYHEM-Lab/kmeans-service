"""
Initialize and configure Flask app here

Author: Angad Gill
"""
from flask import Flask
from flask_pymongo import PyMongo

from config import MONGO_URI, MONGO_DBNAME, FLASK_SECRET_KEY


app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config['MONGO_DBNAME'] = MONGO_DBNAME
app.config['MONGO_URI'] = MONGO_URI
mongo = PyMongo(app)  # context object for MongoDB

