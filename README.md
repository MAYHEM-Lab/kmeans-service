# K-Means Service
This is a repository for a scalable web service that analyzes data to determine the best number of clusters for it, 
using K-Means algorithm with Mahalanois distance and Bayesian Information Criterion.

Author: Angad Gill

## Architecture

- _Frontend_: The frontend is provided by a Python Flask server (under the `frontend` directory). 
- _Backend_: There are two options for the backend:  
  1. Amazon SNS as a queue and Amazon Lambda as a worker. The code for this is available under the `backend` directory.  
  2. RabbitMQ as a queue and Python Celery as a worker. The code of this is currently under the `frontend` directory. This will be fixed soon.  
- _Storage_: Amazon DynamoDB is used for storing information about all jobs (and tasks). Amazon S3 is used to store files uploaded by users.  

## Purpose
The purpose of the _frontend_ is to do the following:  
1. Provide an interface for users to upload their data files.  
2. Provide an interface for users to view the status and results of the analysis.  
3. Generate all the tasks (individual K-Means fit runs) needed to complete a job.  
4. Generate necessary assets needed for 1. and 2., such as, plot images.  
5. Future: Re-run tasks that failed.

The purpose of the _backend_ is to do the following: 
1. Run the analysis based on the data and parameters provided in the queue (Amazon SNS or RabbitMQ).  
2. When done, update DynamoDB with the analysis results.  

