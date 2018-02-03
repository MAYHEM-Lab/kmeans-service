"""
Initialize and configure Flask app here

Author: Angad Gill, Nevena Golubovic
"""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from config import POSTGRES_URI, FLASK_SECRET_KEY
app = Flask(__name__)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = FLASK_SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI']=POSTGRES_URI
db = SQLAlchemy(app)
