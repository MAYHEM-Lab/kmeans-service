# K-Means Service
This is a repository for a scalable web service that analyzes data to determine the best number of clusters for it, 
using K-Means algorithm with Mahalanois distance and Bayesian Information Criterion.

Author: Angad Gill

## Architecture
The system consists of a total of five services:
- _Frontend_: The frontend is provided by a Python Flask server (`frontend.py`) paired with Gunicorn and NGINX. 
- _Backend_: There are two options for the backend:  
  1. Worker: Python Celery to perform all analysis tasks asynchronously (`worker.py`).
  2. Queue: RabbitMQ to broker messages between the Frontend and Workers.
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


## Localhost Server Setup
1. Install and run RabbitMQ and MongoDB.
2. Run the development server
```bash
virtualenv venv --python=python3
source venv/bin/activate
pip install -r requirements.txt
python frontend.py
```
3. Run Celery worker.
```bash
celery worker -A worker --loglevel=info
```

## Production Server Setup from Scratch
There are four servers needed for this web service.
1. Frontend  
2. Backend Queue  
3. Backend Worker  
4. Backend Database  
In addition, Amazon S3 is used to store the files uploaded by users. 
AWS access key is required to make this work.
Amazon S3 is used by the Frontend and the Backend Worker.

To make it scalable, all four are setup on different instances on Eucalyptus.
The Frontend server and the Backend-Worker server also also setup so that these
can be auto-scaled behind a load-balancer.

### Backend
#### Queue
1. Create an Ubuntu Trusty instance (AMI: emi-CF65C654 on ECI cluster or emi-80246ee5 on Aristotle cluster) 
with the following ports open: `TCP 22`, `TCP 5672` and, optionally, `TCP 15672`.  
2. Login to the instances:   
```bash
ssh -i <key_file>.pem ubuntu@<instances IP>
```
3. Update packages: 
```bash
sudo apt-get -y update && sudo apt-get -y upgrade
```
   - At the GRUB update prompt which reads: `A new version of /boot/grub/menu.lst`, 
   select: `keep the local version currently installed`.
4. Install RabbitMQ Server:
```bash
sudo apt-get install -y rabbitmq-server
```
5. [Optional] Enable management plugin so you can use web UI available at port `15672`:
```bash
sudo rabbitmq-plugins enable rabbitmq_management
sudo service rabbitmq-server restart
```
6. Create users:
```bash
sudo rabbitmqctl add_user admin <password>
sudo rabbitmqctl set_user_tags admin administrator
sudo rabbitmqctl add_user kmeans <password>
sudo rabbitmqctl set_permissions -p / kmeans ".*" ".*" ".*"
```
7. Restart RabbitMQ:
```bash
sudo service rabbitmq-server restart
```

#### Database
1. Create an Ubuntu Trusty instance (AMI: emi-CF65C654 on ECI cluster or emi-80246ee5 on Aristotle cluster)
  with the following ports open: `TCP 22` and `TCP 27017`.
2. Login to the instances:   
```bash
ssh -i <key_file>.pem ubuntu@<instances IP>
```
3. Update packages: 
```bash
sudo apt-get -y update && sudo apt-get -y upgrade
```
4. Install MongoDB (official guide [here](https://docs.mongodb.com/manual/tutorial/install-mongodb-on-ubuntu/)):
```bash
sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 0C49F3730359A14518585931BC711F9BA15703C6
echo "deb [ arch=amd64 ] http://repo.mongodb.org/apt/ubuntu trusty/mongodb-org/3.4 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-3.4.list
sudo apt-get update
sudo apt-get install -y mongodb-org
```
5. Setup users:
```bash
mongo
> use admin
> db.createUser({ user: "admin", pwd: "<password>", roles:["root"]})
> use kmeansservice
> db.createUser({ user: "kmeans", pwd: "<password>", roles: [{ role: "readWrite", db: "kmeansservice" }]})
> exit
```
6. Enable authorization:
    - Open up `mongod.conf`
     ```bash
    sudo vi /etc/mongod.conf
    ```
    - Set the following two parameters:
    ```
      bindIp: 0.0.0.0
    ```
    ```
    security:
      authorization: enabled
    ```
7. Run MongoDB:
```bash
sudo service mongod restart
```


#### Worker
1. Create an Ubuntu Trusty instance (AMI: emi-CF65C654 on ECI cluster or emi-80246ee5 on Aristotle cluster) 
with the following port open: `TCP 22`.  
2. Login to the instances:   
```bash
ssh -i <key_file>.pem ubuntu@<instances IP>
```
3. Update packages: 
```bash
sudo apt-get -y update && sudo apt-get -y upgrade
```
   - At the GRUB update prompt which reads: `A new version of /boot/grub/menu.lst`, 
   select: `keep the local version currently installed`.
4. Install required packages: 
```bash
sudo apt-get install -y python-virtualenv python3-tk git
```
5. Clone the repo: 
```bash
git clone https://github.com/MAYHEM-Lab/kmeans-service.git
```
6. Provide AWS credentials:
```bash
mkdir ~/.aws
cd ~/.aws/
echo -e "[default]\nregion = us-west-1" > config
echo -e "[default]\naws_access_key_id = <add key id>\naws_secret_access_key = <add key>" > credentials
```
7. Install required Python packages:
```bash
cd ~/kmeans-service/frontend
virtualenv venv --python=python3
source venv/bin/activate
pip install pip --upgrade
pip install -r requirements.txt
```
8. Configure worker service:
```bash
sudo cp /home/ubuntu/kmeans-service/frontend/worker.conf /etc/init/worker.conf
```
9. Set values in `config.py` using usersnames and passwords from the Queue and Database setup:
```
CELERY_BROKER = 'amqp://kmeans:<password>@<RabbitMQ-IP>:5672//'
MONGO_URI = 'mongodb://kmeans:<password@<MongoDB-IP>:27017/kmeansservice'
```
10. Run the server:  
```bash
sudo service worker start
```

### Frontend
1. Create an Ubuntu Trusty instance (AMI: emi-CF65C654 on ECI cluster or emi-80246ee5 on Aristotle cluster) 
with the following ports open: `TCP 22` and `TCP 80`.  
2. Login to the instances:   
```bash
ssh -i <key_file>.pem ubuntu@<instances IP>
```
3. Update packages: 
```bash
sudo apt-get -y update && sudo apt-get -y upgrade
```
   - At the GRUB update prompt which reads: `A new version of /boot/grub/menu.lst`, 
   select: `keep the local version currently installed`.
4. Install required Ubuntu packages: 
```bash
sudo apt-get install -y nginx python-virtualenv python3-tk git
```
5. Clone this repo: 
```bash
git clone https://github.com/MAYHEM-Lab/kmeans-service.git
```
6. Provide AWS credentials:
```bash
mkdir ~/.aws
cd ~/.aws/
echo -e "[default]\nregion = us-west-1" > config
echo -e "[default]\naws_access_key_id = <add key id>\naws_secret_access_key = <add key>" > credentials
```
7. Install required Python packages:
```bash
cd ~/kmeans-service/frontend
virtualenv venv --python=python3
source venv/bin/activate
pip install pip --upgrade
pip install -r requirements.txt
```
8. Configure NGINX:
```bash
sudo /etc/init.d/nginx start
sudo rm /etc/nginx/sites-enabled/default
sudo cp frontend_nginx_config /etc/nginx/sites-available/kmeans_frontend
sudo ln -s /etc/nginx/sites-available/kmeans_frontend /etc/nginx/sites-enabled/kmeans_frontend
sudo /etc/init.d/nginx restart
```
9. Configure frontend service:
```bash
sudo cp /home/ubuntu/kmeans-service/frontend/frontend.conf /etc/init/frontend.conf
```
10. Generate a secret key for the Flask server:
```bash
python
>>> import os
>>> os.urandom(24)
'\xcf6\x16\xac?\xdb\x0c\x1fb\x01p;\xa1\xf2/\x19\x8e\xcd\xfc\x07\xc9\xfd\x82\xf4'
```
11. Set values in `config.py` using usersnames and passwords from the Queue and Database setup:
```
FLASK_SECRET_KEY = <secret key generted in 10.>
CELERY_BROKER = 'amqp://kmeans:<password>@<RabbitMQ-IP>:5672//'
MONGO_URI = 'mongodb://kmeans:<password@<MongoDB-IP>:27017/kmeansservice'
```
12. Run the server:  
```bash
sudo service frontend start
```


