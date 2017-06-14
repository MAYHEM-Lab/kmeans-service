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
5. Backend File Store: Eucalyptus S3 is used for this. Eucalyptus access key is required to make this work.

To make it scalable, all four are setup on different instances on Eucalyptus.
The Frontend server and the Backend-Worker server also also setup so that these
can be auto-scaled behind a load-balancer.

### Backend
#### Queue
1. Create an Ubuntu 14.04 Trusty instance (AMI: emi-CF65C654 on ECI cluster or emi-80246ee5 on Aristotle cluster) of
m1.small type with the following ports open: `TCP 22`, `TCP 5672` and, optionally, `TCP 15672`.  
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
5. Install NTP to sync clock:
```bash
sudo apt-get install -y ntp
```
6. [Optional] Enable management plugin so you can use web UI available at port `15672`:
```bash
sudo rabbitmq-plugins enable rabbitmq_management
sudo service rabbitmq-server restart
```
7. Create users:
```bash
sudo rabbitmqctl add_user admin <password>
sudo rabbitmqctl set_user_tags admin administrator
sudo rabbitmqctl add_user kmeans <password>
sudo rabbitmqctl set_permissions -p / kmeans ".*" ".*" ".*"
```
8. Restart RabbitMQ:
```bash
sudo service rabbitmq-server restart
```

#### Database
1. Create an Ubuntu 14.04 Trusty instance (AMI: emi-CF65C654 on ECI cluster or emi-80246ee5 on Aristotle cluster) of 
m1.medium type with the following ports open: `TCP 22` and `TCP 27017`.
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
4. Install NTP to sync clock:
```bash
sudo apt-get install -y ntp
```
5. Install MongoDB (official guide [here](https://docs.mongodb.com/manual/tutorial/install-mongodb-on-ubuntu/)):
```bash
sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 0C49F3730359A14518585931BC711F9BA15703C6
echo "deb [ arch=amd64 ] http://repo.mongodb.org/apt/ubuntu trusty/mongodb-org/3.4 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-3.4.list
sudo apt-get update
sudo apt-get install -y mongodb-org
```
6. Setup users:
```bash
mongo
> use admin
> db.createUser({ user: "admin", pwd: "<password>", roles:["root"]})
> use kmeansservice
> db.createUser({ user: "kmeans", pwd: "<password>", roles: [{ role: "readWrite", db: "kmeansservice" }]})
> exit
```
7. Setup config:
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
    - Change database path: 
    ```
      dbPath: /mnt/mongodb
    ```
8. Create database directory and set owner:
```bash
sudo mkdir /mnt/mongodb
sudo chown -R mongodb:mongodb /mnt/mongodb
```
9. Run MongoDB:
```bash
sudo service mongodb restart
```


#### Worker
1. Create an Ubuntu 14.04 Trusty instance (AMI: emi-CF65C654 on ECI cluster or emi-80246ee5 on Aristotle cluster) of 
c1.xlarge type with the following port open: `TCP 22`.  
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
4. Install NTP to sync clock:
```bash
sudo apt-get install -y ntp
```
5. Install required packages: 
```bash
sudo apt-get install -y python-virtualenv python3-tk git
```
6. Clone the repo: 
```bash
git clone https://github.com/MAYHEM-Lab/kmeans-service.git
```
7. Install required Python packages:
```bash
cd ~/kmeans-service/site
virtualenv venv --python=python3
source venv/bin/activate
pip install pip --upgrade
pip install -r requirements.txt
```
8. Configure worker service:
```bash
#if using upstart
sudo cp /home/ubuntu/kmeans-service/site/worker.conf /etc/init/worker.conf
#if using systemd
sudo cp /home/ubuntu/kmeans-service/site/util/worker.service /etc/systemd/system/
```
9. Set values in `config.py` using usersnames and passwords from the Queue and Database setup:
```
CELERY_BROKER = 'amqp://kmeans:<password>@<RabbitMQ-IP>:5672//'
MONGO_URI = 'mongodb://kmeans:<password>@<MongoDB-IP>:27017/kmeansservice'
EUCA_KEY_ID = "<eucalyptus_key_id>"
EUCA_SECRET_KEY = "<eucalyptus_secret_key>"
```
10. Run the server:  
```bash
#if using upstart
sudo service worker start
#if using systemd
sudo systemctl start worker
```

### Frontend
1. Create an Ubuntu 14.04 Trusty instance (AMI: emi-CF65C654 on ECI cluster or emi-80246ee5 on Aristotle cluster) of
c1.xlarge type with the following ports open: `TCP 22` and `TCP 80`.  
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
4. Install NTP to sync clock:
```bash
sudo apt-get install -y ntp
```
5. Install required Ubuntu packages: 
```bash
sudo apt-get install -y nginx python-virtualenv python3-tk git
```
6. Clone this repo: 
```bash
git clone https://github.com/MAYHEM-Lab/kmeans-service.git
```
7. Install required Python packages:
```bash
cd ~/kmeans-service/site
virtualenv venv --python=python3
source venv/bin/activate
pip install pip --upgrade
pip install -r requirements.txt
```
8. Configure NGINX:
```bash
sudo /etc/init.d/nginx start
sudo rm /etc/nginx/sites-enabled/default
sudo cp nginx.conf /etc/nginx/sites-available/kmeans_frontend
sudo ln -s /etc/nginx/sites-available/kmeans_frontend /etc/nginx/sites-enabled/kmeans_frontend
sudo /etc/init.d/nginx restart
```
9. Create directory for logs:
```bash
mkdir /home/ubuntu/logs
mkdir /home/ubuntu/logs/gunicorn
touch /home/ubuntu/logs/gunicorn/error.log
```
10. Configure frontend service:
```bash
#if using upstart
sudo cp /home/ubuntu/kmeans-service/site/frontend.conf /etc/init/frontend.conf
#if using systemd
sudo cp /home/ubuntu/kmeans-service/site/util/frontend.service /etc/systemd/system/
```
11. Generate a secret key for the Flask server:
```bash
python
>>> import os
>>> os.urandom(24)
'\xcf6\x16\xac?\xdb\x0c\x1fb\x01p;\xa1\xf2/\x19\x8e\xcd\xfc\x07\xc9\xfd\x82\xf4'
```
12. Set values in `config.py` using usersnames and passwords from the Queue and Database setup:
```
FLASK_SECRET_KEY = <secret key generted in 10.>
CELERY_BROKER = 'amqp://kmeans:<password>@<RabbitMQ-IP>:5672//'
MONGO_URI = 'mongodb://kmeans:<password>@<MongoDB-IP>:27017/kmeansservice'
EUCA_KEY_ID = "<eucalyptus_key_id>"
EUCA_SECRET_KEY = "<eucalyptus_secret_key>"
```
13. Run the server:  
```bash
#if using upstart
sudo service frontend start
#if using systemd
sudo systemctl start frontend
```

### File Store
1. Login to [Eucalyptus S3](https://console.aristotle.ucsb.edu/buckets).
2. Click on "Create Bucket".
3. Name it "kmeansservice" and click on "Create Bucket".

## Setting up auto-scaling for Backend Workers
Follow these instructions to setup auto-scaling on [Aristole](https://console.aristotle.ucsb.edu) for the Backend 
Workers, after completing the setup above.

### 1. Create an Image
1. SSH to the Backend Worker instance and run the following commands to prepare it for image creation:
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
2. Go to the [Instances page](https://console.aristotle.ucsb.edu/instances) and find the instance.
3. In the "Actions" column, click on the ellipses ("...") and select "Create image".
4. Type an appropriate name, select a bucket (or create a new one), and click "Create Image".
5. Once the image is created successfully, note down the image ID (AMI).


### 2. Create a Launch Configuration
1. Go to the [Launch Configurations page](https://console.aristotle.ucsb.edu/launchconfigs) and click on "Create New
Launch Configuration".
2. Search for the image create earlier by name or by the AMI and click "Select".
3. Type an appropriate name and select c1.xlarge instance type.
4. Under "User data", select "Enter Text" and paste the following into the text box under it:
```bash
#!/bin/bash
sudo cp /home/ubuntu/kmeans-service/site/worker.conf /etc/init/worker.conf
sudo service worker start
```
5. Click "Next"
6. Select key pair that will be used with these instance and select a security group that has `TCP` port `22` open.
7. Click "Create Launch Configuration"

### 3. Create an Auto-Scale Group
1. Go to the [Scaling Groups page](https://console.aristotle.ucsb.edu/scalinggroups) and click on "Create New Scaling 
Group".
2. Type an appropriate name, set the "Max" to `5`, and click "Next". 
3. Set the "Availability zone(s)" to "race" and click "Create Scaling Group". This will redirect to the page for the 
configuration. 
4. Create a policy to scale up that triggers when the average CPU utilization for the group is over 25% for 1 
minute:
    1. Select the "Scaling Policies" tab and click on "ADD A SCALING POLICY".
    2. Type an appropriate name, e.g., "scale-up-25-per-1-min".
    3. Under "Action", select "Scale up by".
    4. Under "Alarm", click on "Creat alarm".
    5. In the pop-up modal window:
        1. Type an appropriate name, e.g., "25-per-1-min"
        2. In the drop down box next to "When the", select "Average"
        3. In the drop down box next to "Average", select "AWS/EC2 - CPUUtilization"
        4. In the drop down next to "for", select "Scaling group"
        5. In the drop down next to "Scaling group", select the name of the scaling group being created in this setup.
        6. In the drop down box next to "is", select ">="
        7. In the text box for "amount..." type `25`.
        8. In the text box next to "with each measurement lasting", type `1`
    6. Click on "Create Alarm" and then on "Create Scaling Policy".
5. Create a policy to scale down that triggers when the average CPU utilization for the group is under 10% for 5 
minutes:
    1. Select the "Scaling Policies" tab and click on "ADD A SCALING POLICY".
    2. Type an appropriate name, e.g., "scale-down-10-per-5-min".
    3. Under "Action", select "Scale down by".
    4. Under "Alarm", click on "Crete alarm".
    5. In the pop-up modal window:
        1. Type an appropriate name, e.g., "10-per-5-min"
        2. In the drop down box next to "When the", select "Average"
        3. In the drop down box next to "Average", select "AWS/EC2 - CPUUtilization"
        4. In the drop down next to "for", select "Scaling group"
        5. In the drop down next to "Scaling group", select the name of the scaling group being created in this setup.
        6. In the drop down box next to "is", select "<"
        7. In the text box for "amount..." type `10`.
        8. In the text box next to "with each measurement lasting", type `5`
    6. Click on "Create Alarm" and then on "Create Scaling Policy".

