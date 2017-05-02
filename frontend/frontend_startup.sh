#!/usr/bin/env bash

# Config NGINX
cp /home/kmeans-service/frontend/frontend_nginx_config /etc/nginx/sites-available/frontend
ln -s /etc/nginx/sites-available/frontend /etc/nginx/sites-enabled
sudo service nginx restart

# Config frontend upstart script
cp /home/kmeans-service/frontend/frontend.conf /etc/init/frontend.conf
sudo service frontend start
