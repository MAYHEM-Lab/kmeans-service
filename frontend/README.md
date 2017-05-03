## Localhost Server Setup
```bash
virtualenv venv --python=python3
source venv/bin/activate
pip install -r requirements.txt
python frontend.py
```
Install and run RabbitMQ.

```bash
celery -A submit_job worker --loglevel=info
```

## Production Server Setup from Scratch
There are four servers needed for this web service.
1. Frontend  
2. Backend Queue  
3. Backend Worker  
4. Backend Database  

To make it scalable, all four are setup on different instances on Eucalyptus.
The Frontend server and the Backend-Worker server also also setup so that these
can be auto-scaled behind a load-balancer.

### Frontend
1. Create an Ubuntu (AMI: emi-CF65C654) instance on Eucalyptus ECI cloud.  
2. Login to the instances:   
```bash
ssh -i <key_file>.pem ubuntu@<instances IP>
```
3. Update packages: 
```bash
sudo apt-get -y update && sudo apt-get -y upgrade
```
4. Install required packages: 
```bash
sudo apt-get install -y nginx python-virtualenv python3-tk
```

5. Clone the repo: 
```bash
git clone https://github.com/MAYHEM-Lab/kmeans-service.git
```
6. Provide AWS credentials:
```bash
mkdir ~/.aws
cd ~/.aws/
echo "[default]\nregion = us-west-1" > config
echo "[default]\naws_access_key_id = <add key id>\naws_secret_access_key = <add key>" > credentials
```

7. Install required Python packages:
```bash
cd kmeans-service/frontend
virtualenv venv --python=python3
source venv/bin/activate
pip3 install pip --upgrade
pip3 install -r frontend-requirements.txt
pip3 install gunicorn
```
8. Configure NGINX
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
9. Run the server:  
```bash
sudo service frontend start
```


### Backend
#### Queue
1. Create an Ubuntu (AMI: emi-CF65C654) instance on Eucalyptus ECI cloud.  
2. Login to the instances:   
```bash
ssh -i <key_file>.pem ubuntu@<instances IP>
```
3. Update packages: 
```bash
sudo apt-get -y update && sudo apt-get -y upgrade
```
4. Install RabbitMQ Server:
```bash
sudo apt-get install -y rabbitmq-server
```

#### Worker
1. Create an Ubuntu (AMI: emi-CF65C654) instance on Eucalyptus ECI cloud.  
2. Login to the instances:   
```bash
ssh -i <key_file>.pem ubuntu@<instances IP>
```
3. Update packages: 
```bash
sudo apt-get -y update && sudo apt-get -y upgrade
```
4. Install required packages: 
```bash
sudo apt-get install -y python-virtualenv
```

5. Clone the repo: 
```bash
git clone https://github.com/MAYHEM-Lab/kmeans-service.git
```
6. Provide AWS credentials:
```bash
mkdir ~/.aws
cd ~/.aws/
echo "[default]\nregion = us-west-1" > config
echo "[default]\naws_access_key_id = <add key id>\naws_secret_access_key = <add key>" > credentials
```

7. Install required Python packages:
```bash
cd kmeans-service/frontend
virtualenv venv --python=python3
source venv/bin/activate
pip3 install pip --upgrade
pip3 install -r frontend-requirements.txt
```
9. Configure worker service:
```bash
sudo cp /home/ubuntu/kmeans-service/frontend/worker.conf /etc/init/worker.conf
```
9. Run the server:  
```bash
sudo service worker start
```

#### Database



