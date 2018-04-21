## Production Server Setup from Scratch
The following components can all be installed on one machine or each can
have its own separate server to allow for more scalability.
Documentation below uses Eucalyptus cloud and was tested on OpenStack
and AWS.

1. Frontend  
2. Backend Queue  
3. Backend Worker  
4. Backend Database  
5. Backend File Store: Eucalyptus S3 is used for this. Eucalyptus access
 key is required to make this work.

Backend-Worker server can be setup so that it can auto-scale behind a
load-balancer. For more details scroll to the end.

Instructions differ for Ubuntu 14 and Ubuntu 16.

### Backend
#### Queue
1. Create a security group for the Queue with the following ports open:
`TCP 22`, `TCP 5672` and, optionally, `TCP 15672`.
```bash
euca-create-group cent-queue -d centaurus-queue-open-22-5672-15672
euca-authorize cent-queue  -p 22 -s 0.0.0.0/0 -P tcp
euca-authorize cent-queue  -p 5672 -s 0.0.0.0/0 -P tcp
euca-authorize cent-queue  -p 15672  -s 0.0.0.0/0 -P tcp
euca-describe-group cent-queue
```
2. Create an Ubuntu Server 16.04 LTS instance
(Aristotle: Ubuntu Server 16.04 LTS Xenial Xerus Image: emi-418f4d99)
**or** an Ubuntu 14.04 Trusty instance (ECI cluster: AMI: emi-CF65C654
Aristotle cluster: emi-80246ee5)
of m1.xlarge (or any other) type:
```bash
 euca-run-instances -k your.key -g cent-queue -t m1.xlarge emi-418f4d99
```
   - To setup a region within Aristotle append the following to the
euca-run-instances command
```bash
 --region admin@cloud.aristotle.ucsb.edu -z aristotle
```
3. Login to the instances:
```bash
ssh -i <key_file>.pem ubuntu@<instances IP>
```
4. Update packages:
```bash
sudo apt-get -y update && sudo apt-get -y upgrade
```

5. Install RabbitMQ Server:
```bash
sudo apt-get install -y rabbitmq-server
```
6. Install NTP to sync clock:
```bash
sudo apt-get install -y ntp
```
7. [Optional] Enable management plugin so you can use web UI available
at port `15672`:
```bash
sudo rabbitmq-plugins enable rabbitmq_management
sudo service rabbitmq-server restart
```
8. Create users:
```bash
sudo rabbitmqctl add_user admin <password>
sudo rabbitmqctl set_user_tags admin administrator
sudo rabbitmqctl add_user kmeans <password>
sudo rabbitmqctl set_permissions -p / kmeans ".*" ".*" ".*"
```
9. Restart RabbitMQ:
```bash
sudo service rabbitmq-server restart
```

#### Database
1. Create a security group for the Database with the following ports
open: `TCP 22`, `TCP ` and, `TCP 5432`.
```bash
euca-create-group cent-db -d centaurus-db-open-22-27017
euca-authorize cent-db  -p 22 -s 0.0.0.0/0 -P tcp
euca-authorize cent-db  -p 5432 -s 0.0.0.0/0 -P tcp
euca-describe-group cent-db
```

2. Create an Ubuntu Server 16.04 LTS instance
(Aristotle: Ubuntu Server 16.04 LTS Xenial Xerus Image: emi-418f4d99)
**or** an Ubuntu 14.04 Trusty instance (ECI cluster: AMI: emi-CF65C654
Aristotle cluster: emi-80246ee5) of m2.2xlarge (or any other) type:
```bash
 euca-run-instances -k your.key -g cent-queue -t m2.2xlarge emi-418f4d99
```
   - To setup a region within Aristotle append the following to the
euca-run-instances command
```bash
 --region admin@cloud.aristotle.ucsb.edu -z aristotle
```
3. Login to the instances:
```bash
ssh -i <key_file>.pem ubuntu@<instances IP>
```
4. Update packages and install NTP to sync clock:
```bash
sudo apt-get -y update && sudo apt-get -y upgrade && sudo apt-get install -y ntp
```

5. Install Postgres ([official guide](https://www.postgresql.org/docs/current/static/tutorial-install.html)):
```bash
sudo apt-get -Y install postgresql postgresql-contrib
```
6. Setup users:
 - after logging in as ubuntu user, create kmeans user:
```bash
sudo -su
sudo adduser kmeans
```
 - test the login
```bash
sudo -i -u kmeans
```
 - create postgres kmeans user
```bash
sudo -i -u postgres
createuser --interactive
name:kmeans
role (superuser): y
```
 - set the password
```bash
sudo -u postgres psql
alter user kmeans with encrypted password 'y0ur_passw0rd';
```
 - test the login
```bash
psql -h localhost  -U kmeans -d kmeans
```

7. Setup config:
 - Open up `/etc/postgresql/your_pg_version/main/pg_hba.conf`
```bash
sudo vi /etc/postgresql/your_pg_version/main/pg_hba.conf
```
 - Set the following lines
```bash
local all all   trust
host all all 0.0.0.0/0 md5
```
 - Open `/etc/postgresql/your_pg_version/main/postgresql.conf`
```bash
sudo vi /etc/postgresql/your_pg_version/main/postgresql.conf
```
 - Set the follwoving parameters:
```bash
listen_addresses = '*'
max_connections = 10000
```

8. Create the database and tables
 - Create database
```bash
createdb kmeans
```
 - Create tables
```bash
CREATE TABLE job (
    job_id serial PRIMARY KEY,
    n_experiments int NOT NULL,
    max_k int NOT NUll,
    n_init int NOT NULL,
    n_tasks int NOT NULL,
    columns text[],
    filename varchar (100) NOT NULL,
    start_time timestamp with time zone,
    scale boolean,
    s3_file_key varchar (200) NOT NULL
);
```
```bash
CREATE TABLE task (
    id serial PRIMARY KEY,
    task_id int,
    job_id serial,
    n_experiments int NOT NULL,
    max_k int,
    n_init int NOT NULL,
    n_tasks int,
    columns text[],
    filename varchar (100),
    start_time timestamp with time zone,
    scale boolean,
    s3_file_key varchar (200) NOT NULL,
    k int NOT NULL,
    covar_type varchar(25) check (covar_type in ('full', 'diag', 'spher')),
    covar_tied boolean,
    task_status varchar(25) check (task_status in ('pending', 'done', 'error')),
    task_index int,
    aic numeric,
    bic numeric,
    labels int[],
    cluster_counts int[],
    centers numeric[],
    cluster_count_minimum int,
    elapsed_time int,
    iteration_num int
    elapsed_read_time int,
    elapsed_processing_time int
);
```

10. Run Postgres:
```bash
sudo systemctl restart postgresql.service
```

11. Other useful commands:
```bash
sudo systemctl status postgresql.service
pg_dump kmeans >  kmeans_backup.out
less  /var/log/postgresql/postgresql-9.5-main.log
```


### File Store
1. Login to [Eucalyptus S3](https://console.aristotle.ucsb.edu/buckets).
2. Click on "Create Bucket".
3. Give it a unique name and click on "Create Bucket".


#### Worker
1. Create a security group for the Worker opened port: `TCP 22`:
```bash
 euca-create-group cent-worker -d centaurus-worker-open-22
 euca-authorize cent-worker  -p 22 -s 0.0.0.0/0 -P tcp
 euca-describe-group cent-worker
```
2. Create an Ubuntu Server 16.04 LTS instance
(Aristotle: Ubuntu Server 16.04 LTS Xenial Xerus Image: emi-418f4d99)
**or** an Ubuntu 14.04 Trusty instance (ECI cluster: AMI: emi-CF65C654
Aristotle cluster: emi-80246ee5) of m2.2xlarge (or any other) type:
```bash
 euca-run-instances -k your.key -g cent-worker -t m2.2xlarge emi-418f4d99
```
   - To setup a region within Aristotle append the following to the
euca-run-instances command
```bash
 --region admin@cloud.aristotle.ucsb.edu -z aristotle
```
2. Login to the instance:
```bash
ssh -i <key_file>.pem ubuntu@<instances IP>
```
3. Update packages, install NTP and required packages:
```bash
sudo apt-get -y update && sudo apt-get -y upgrade && sudo apt-get install -y ntp && sudo apt-get install -y python-virtualenv python3-tk git
```
4. Clone the repo:
```bash
git clone https://github.com/MAYHEM-Lab/kmeans-service.git
```
5. Install required Python packages:
```bash
cd ~/kmeans-service/site
virtualenv venv --python=python3
source venv/bin/activate
pip install pip --upgrade
pip install -r requirements.txt
```
6. Configure worker service:
```bash
#if using upstart - Ubuntu 14.04
sudo cp /home/ubuntu/kmeans-service/site/worker.conf /etc/init/worker.conf
#if using systemd - Ubuntu 16.04
sudo cp /home/ubuntu/kmeans-service/site/util/worker.service /etc/systemd/system/
sudo cp /home/ubuntu/kmeans-service/site/util/celery-teardown.sh /usr/sbin/
```
9. Set (or replace) values in `config.py`:
```
CELERY_BROKER = 'amqp://kmeans:<password>@<RabbitMQ-IP>:5672//'
POSTGRES_URI = 'postgres://kmeans:passwd@<Postgres-IP>:5432/kmeans'
S3_BUCKET = '<unique_s3_bucket_name>'
EUCA_KEY_ID = "<eucalyptus_key_id>"
EUCA_SECRET_KEY = "<eucalyptus_secret_key>"
```
10. Run the server:  
```bash
#if using upstart - Ubuntu 14.04
sudo service worker start
#if using systemd - Ubuntu 16.04
sudo systemctl start worker
```

### Frontend
1. Create a security group for the Fronted with opened ports `TCP 22`
and `TCP 80`.
```bash
euca-create-group cent-frontend -d centaurus-frontend-open-22-80
euca-authorize cent-frontend  -p 22 -s 0.0.0.0/0 -P tcp
euca-authorize cent-frontend  -p 80 -s 0.0.0.0/0 -P tcp
euca-describe-group cent-frontend
```
2. Create an Ubuntu Server 16.04 LTS instance
(Aristotle: Ubuntu Server 16.04 LTS Xenial Xerus Image: emi-418f4d99)
**or** an Ubuntu 14.04 Trusty instance (ECI cluster: AMI: emi-CF65C654
Aristotle cluster: emi-80246ee5) of m2.2xlarge (or any other) type:
```bash
 euca-run-instances -k your.key -g cent-frontend -t m2.2xlarge emi-418f4d99
```
   - To setup a region within Aristotle append the following to the
euca-run-instances command
```bash
 --region admin@cloud.aristotle.ucsb.edu -z aristotle
```
3. Login to the instances:
```bash
ssh -i <key_file>.pem ubuntu@<instances IP>
```
4. Update packages: . Install NTP to sync clock:Install required Ubuntu
packages:
```bash
sudo apt-get -y update && sudo apt-get -y upgrade && sudo apt-get install -y ntp && sudo apt-get install -y nginx python-virtualenv python3-tk git
```
5. Clone this repo:
```bash
git clone https://github.com/MAYHEM-Lab/kmeans-service.git
```
6. Install required Python packages:
```bash
cd ~/kmeans-service/site
virtualenv venv --python=python3
source venv/bin/activate
pip install pip --upgrade
pip install -r requirements.txt
```
7. Configure NGINX:
```bash
sudo /etc/init.d/nginx start
sudo rm /etc/nginx/sites-enabled/default
sudo cp conf/nginx.conf /etc/nginx/sites-available/kmeans_frontend
sudo ln -s /etc/nginx/sites-available/kmeans_frontend /etc/nginx/sites-enabled/kmeans_frontend
sudo /etc/init.d/nginx restart
```
8. Create directory for logs:
```bash
mkdir /home/ubuntu/logs
mkdir /home/ubuntu/logs/gunicorn
touch /home/ubuntu/logs/gunicorn/error.log
```
9. Configure frontend service:
```bash
#if using upstart - Ubuntu 14.04
sudo cp /home/ubuntu/kmeans-service/site/conf/frontend.conf /etc/init/frontend.conf
#if using systemd - Ubuntu 16.04
sudo cp /home/ubuntu/kmeans-service/site/util/frontend.service /etc/systemd/system/
```
10. Generate a secret key for the Flask server:
```bash
python
>>> import os
>>> os.urandom(24)
'\xcf6\x16\xac?\xdb\x0c\x1fb\x01p;\xa1\xf2/\x19\x8e\xcd\xfc\x07\xc9\xfd\x82\xf4'
```
11. Set (or replace) values in `config.py`:
```
FLASK_SECRET_KEY = <secret key generted in 10.>
CELERY_BROKER = 'amqp://kmeans:<password>@<RabbitMQ-IP>:5672//'
POSTGRES_URI = 'postgres://kmeans:passwd@<Postgres-IP>:5432/kmeans'
S3_BUCKET = '<unique_s3_bucket_name>'
EUCA_KEY_ID = "<eucalyptus_key_id>"
EUCA_SECRET_KEY = "<eucalyptus_secret_key>"
```
12. Run the server:
```bash
#if using upstart - Ubuntu 14.04
sudo service frontend start
#if using systemd - Ubuntu 16.04
sudo systemctl start frontend
```

## Setting up auto-scaling for Backend Workers
Follow these instructions to setup auto-scaling on
[Aristole](https://console.aristotle.ucsb.edu) for the Backend Workers,
after completing the setup above. Note the parallel Ubuntu 14 vs 16 commands.

### 1. Create an Image
1. SSH to the Backend Worker instance and run the following commands to
prepare it for image creation:
```bash
sudo service worker stop //systemd: sudo systemctl stop worker 
sudo rm -f /var/log/upstart/worker.log 
sudo rm -f /etc/init/worker.conf
sudo service frontend stop  //systemd: sudo systemctl stop frontend
sudo rm -f /etc/init/frontend.conf
sudo rm -rf /home/ubuntu/logs/
sudo apt-get update; sudo apt-get -y upgrade; sudo apt-get -y dist-upgrade; sudo apt-get -y autoremove
sudo apt-get -y install tzdata ntp zip unzip curl wget cvs git python-pip build-essential
dpkg-reconfigure tzdata
sudo rm -f /etc/udev/rules.d/70*-net.rules
sudo rm -rf /root/linux-rootfs-resize*
sudo rm -rf /root/euca2ools*
sudo rm -rf /var/lib/cloud/instance /var/lib/cloud/instances/i*
rm -f ~/.bash_history
#remove all keys and credentials also!
```
2. Go to the
[Instances page](https://console.aristotle.ucsb.edu/instances)
and find the instance.
3. In the "Actions" column, click on the ellipses ("...") and select
"Create image".
4. Type an appropriate name, select a bucket (or create a new one), and
click "Create Image".
5. Once the image is created successfully, note down the image ID (AMI).


### 2. Create a Launch Configuration
1. Go to the
[Launch Configurations](https://console.aristotle.ucsb.edu/launchconfigs)
and click on "Create New Launch Configuration".
2. Search for the image create earlier by name or by the AMI and click
"Select".
3. Type an appropriate name and select c1.xlarge instance type.
4. Under "User data", select "Enter Text" and paste the following into the text
 box under it:
```bash
#!/bin/bash
sudo cp /home/ubuntu/kmeans-service/site/conf/worker.conf /etc/init/worker.conf
sudo service worker start
```
5. Click "Next"
6. Select key pair that will be used with these instance and select a security
group that has `TCP` port `22` open.
7. Click "Create Launch Configuration"

### 3. Create an Auto-Scale Group
1. Go to the
[Scaling Groups page](https://console.aristotle.ucsb.edu/scalinggroups) and
click on "Create New Scaling Group".
2. Type an appropriate name, set the "Max" to `5`, and click "Next". 
3. Set the "Availability zone(s)" to "race" and click "Create Scaling Group".
This will redirect to the page for the configuration.
4. Create a policy to scale up that triggers when the average CPU utilization
for the group is over 25% for 1 minute:
    1. Select the "Scaling Policies" tab and click on "ADD A SCALING POLICY".
    2. Type an appropriate name, e.g., "scale-up-25-per-1-min".
    3. Under "Action", select "Scale up by".
    4. Under "Alarm", click on "Creat alarm".
    5. In the pop-up modal window:
        1. Type an appropriate name, e.g., "25-per-1-min"
        2. In the drop down box next to "When the", select "Average"
        3. In the drop down box next to "Average", select "AWS/EC2 -
           CPUUtilization"
        4. In the drop down next to "for", select "Scaling group"
        5. In the drop down next to "Scaling group", select the name of the
            scaling group being created in this setup.
        6. In the drop down box next to "is", select ">="
        7. In the text box for "amount..." type `25`.
        8. In the text box next to "with each measurement lasting", type `1`
    6. Click on "Create Alarm" and then on "Create Scaling Policy".
5. Create a policy to scale down that triggers when the average CPU utilization
   for the group is under 10% for 5 minutes:
    1. Select the "Scaling Policies" tab and click on "ADD A SCALING POLICY".
    2. Type an appropriate name, e.g., "scale-down-10-per-5-min".
    3. Under "Action", select "Scale down by".
    4. Under "Alarm", click on "Crete alarm".
    5. In the pop-up modal window:
        1. Type an appropriate name, e.g., "10-per-5-min"
        2. In the drop down box next to "When the", select "Average"
        3. In the drop down box next to "Average", select "AWS/EC2 -
           CPUUtilization"
        4. In the drop down next to "for", select "Scaling group"
        5. In the drop down next to "Scaling group", select the name of the
           scaling group being created in this setup.
        6. In the drop down box next to "is", select "<"
        7. In the text box for "amount..." type `10`.
        8. In the text box next to "with each measurement lasting", type `5`
    6. Click on "Create Alarm" and then on "Create Scaling Policy".
