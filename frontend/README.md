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
1. Create an Ubuntu (Trusty) instance on Eucalyptus.  
2. Login to the instances:   
```bash
ssh -i <key_file>.pem ubuntu@<instances IP>
```
3. Update packages: 
```bash
sudo apt-get update -y
sudo apt-get upgrade -y
```
4. Install required packages: 
```bash
sudo apt-get install git build-essential python3-pip -y
```
5. Clone the repo: 
```bash
git clone https://github.com/MAYHEM-Lab/kmeans-service.git
```
6. Install required Python packages:  
7. Run the server:  
```bash
cd kmeans-service/frontend
python3 -m venv venv
source venv/bin/activate
pip install -r frontend-requirements.txt
python3 frontend.py
```


### Backend
#### Queue


#### Worker
Follow 1. to 5. from Frontend setup


#### Database



