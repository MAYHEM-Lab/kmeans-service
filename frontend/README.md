## To run local
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
