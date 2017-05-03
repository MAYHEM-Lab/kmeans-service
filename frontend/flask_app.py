"""
Initialize and configure Flask app here

Author: Angad Gill
"""
import os

from flask import Flask
from flask_pymongo import PyMongo

from config import MONGO_URI, MONGO_DBNAME


app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MONGO_DBNAME'] = MONGO_DBNAME
app.config['MONGO_URI'] = MONGO_URI

mongo = PyMongo(app)

