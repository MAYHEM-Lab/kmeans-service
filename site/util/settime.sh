#! /bin/sh

sudo service ntp stop
sudo ntpdate time.ucsb.edu
sudo service ntp start
