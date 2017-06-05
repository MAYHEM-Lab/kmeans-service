# K-Means Service
This is a repository for a scalable web service that analyzes data to determine the best number of clusters for it, 
using K-Means algorithm with Mahalanois distance and Bayesian Information Criterion.

Author: Angad Gill

## Architecture
The system consists of a total of five services:
- _Frontend_: The frontend is provided by a Python Flask server (`site/frontend.py`) paired with Gunicorn and NGINX. 
- _Backend_: There are two options for the backend:  
  1. Worker: Python Celery to perform all analysis tasks asynchronously (`site/worker.py`).
  2. Queue: RabbitMQ as a message broker between the Frontend and Workers.
  3. Database: MongoDB to store all parameters for analyses and results of all tasks associated with each analysis.
  4. Storage: Amazon S3 to store the data file uploaded by users.

## Purpose
The purpose of the _Frontend_ is to do the following:  
1. Provide an interface for users to upload their data files to the Backend Storage.  
2. Provide an interface for users to view the status and results of the analysis.  
3. Generate all the tasks (individual K-Means fit runs) needed to complete a job.  
4. Generate necessary plots and tables needed for 1. and 2.  
5. Allow users to rerun tasks that failed.

The purpose of the _Backend Worker_ is to do the following: 
1. Run the analysis based on the data and parameters provided in the Backedn Queue.  
2. When done, update the Backend Database with the analysis results.  


## Installation  
See `site/README.md`.