#!/usr/bin/env bash

# Config NGINX
sudo cp /home/ubuntu/kmeans-service/frontend/frontend_nginx_config /etc/nginx/sites-available/frontend
sudo ln -s /etc/nginx/sites-available/frontend /etc/nginx/sites-enabled
sudo service nginx restart

# Config frontend upstart script
sudo cp /home/ubuntu/kmeans-service/frontend/frontend.conf /etc/init/frontend.conf
sudo service frontend start
