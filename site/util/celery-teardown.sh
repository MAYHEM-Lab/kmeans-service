#! /bin/sh

# Kill only the parent Celery process so that it can do a Warm Shutdown.
# Source: https://github.com/celery/celery/issues/2700
# find parent Celery process id
CELERY_PID=$(ps aux --sort=start_time | grep 'celery worker' | grep 'bin/celery' | head -1 | awk '{print $2}')
#echo pid: ${CELERY_PID}
if [ ! -z "${CELERY_PID}" ]; then 
    #echo found a pid!
    # kill parent Celery process
    sudo kill -TERM $CELERY_PID
    # wait for process to be killed
    while sudo kill -0 $CELERY_PID
    do
        sleep 1
    done
fi
