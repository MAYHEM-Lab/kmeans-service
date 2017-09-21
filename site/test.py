"""
Test the code that performs analysis (executed by Celery).
copied from worker.py; no database or celery setup or use is employed.

Author: Angad Gill, Chandra Krintz
"""
import time,argparse,sys
from sf_kmeans import sf_kmeans
from utils import s3_to_df, float_to_str
from sklearn import preprocessing
import pandas as pd
import itertools

def run_kmeans(data, n_clusters, covar_type, covar_tied, n_init):
    """
    Creates an instance of the `kmeans` object and runs `fit` using the data.

    Parameters
    ----------
    data: Pandas DataFrame
        Data containing only the columns to be used for `fit`
    n_clusters: int
    covar_type: str
    covar_tied: bool
    n_init: int

    Returns
    -------
    float, float, list(int)
        aic, bic, labels
    """
    #print('running kmeans for k={} init={} covar={} tied={}'.format(n_clusters,n_init,covar_type,covar_tied))
    kmeans = sf_kmeans.SF_KMeans(n_clusters=n_clusters, covar_type=covar_type, covar_tied=covar_tied, n_init=n_init,
                                 verbose=0,min_members=50)
    kmeans.fit(data)
    aic, bic = kmeans.aic(data), kmeans.bic(data)
    labels = [int(l) for l in kmeans.labels_]
    return aic, bic, labels

#@app.task
def work_task(job_id, task_id, k, covar_type, covar_tied, n_init, s3_file_key, columns, scale, use_mongo=True):
    """
    Performs the processing needed to complete a task. Downloads the task parameters and the file. Runs K-Means `fit`
    and updates the database with results.

    Sets `task_status` in the database to 'done' if completed successfully, else to 'error'.

    Parameters
    ----------
    job_id: str
    task_id: int
    k: int
    covar_type: str
    covar_tied: bool
    n_init: int
    s3_file_key: str
    columns: list(str)
    scale: bool

    Returns
    -------
    str
        'Done'
    """
    try:
        #print('job_id:{}, task_id:{}'.format(job_id, task_id))
        start_time = time.time()
        start_read_time = time.time()
        if not use_mongo: #s3_file_key contains the df already (testing)
            data = s3_file_key
        else: #we need to get it from s3 (running the service)
            data = s3_to_df(s3_file_key)
        elapsed_read_time = time.time() - start_read_time

        start_processing_time = time.time()
        data = data.loc[:, columns]
        if scale:
            data = preprocessing.scale(data)
        aic, bic, labels = run_kmeans(data, k, covar_type, covar_tied, n_init)
        elapsed_processing_time = time.time() - start_processing_time

        elapsed_time = time.time() - start_time

        elapsed_time = float_to_str(elapsed_time)
        elapsed_read_time = float_to_str(elapsed_read_time)
        elapsed_processing_time = float_to_str(elapsed_processing_time)
        if use_mongo:
            response = mongo_no_context_update_task(job_id, task_id, aic, bic, labels, elapsed_time, elapsed_read_time, elapsed_processing_time)
        else: 
            res = [aic,bic,elapsed_time,elapsed_read_time,elapsed_processing_time]
            #print('aic:{}, bic:{}'.format(aic, bic))
            #print('elapsed_time:{}, elapsed_read_time:{}, elapsed_processing_time:{}'.format(elapsed_time, elapsed_read_time, elapsed_processing_time))
            return res

    except Exception as e:
        if use_mongo:
            response = mongo_no_context_update_task_status(job_id, task_id, 'error')
        raise Exception(e)
    #return 'Done'
    return []

def main():
    global DEBUG
    parser = argparse.ArgumentParser(description='K-means test')
    parser.add_argument('csvfname',action='store',help='name of csv file in working dir')
    args = parser.parse_args()


    if args.csvfname=='normal.csv':
        columns = ['Dimension 1', 'Dimension 2']
    elif args.csvfname=='CP_NO.csv':
        #columns = ['Latitude', 'Longitude','EC1','EC2','Elevation']
        columns = ['EC1','EC2','Elevation']
    else:
        print('Error, unexepected filename')
        sys.exit(1)
    s3_file_key = pd.read_csv(args.csvfname)
    scale = True

    job_id = "1"
    n_init = 50 #number of different random initial centroid selections
    #work_task("1","1",3,"full",True,n_init,s3_file_key,columns,scale,False)

    task_id = 0
    bestbic = bic = -9999999
    bestcombo = []
    combo = []
    for L in range(0, len(columns)+1):
        for subset in itertools.combinations(columns, L):
            if len(subset) > 1:
                bic = -9999999
                combo = []
                for covar_tied in [True,False]:
                    for covar_type in ['full','diag','spher','global']:
                        for k in range(1,20):
                            task_id += 1
                            res = work_task(job_id,task_id,k,covar_type,covar_tied,n_init,s3_file_key,subset,scale,False)
                            if res[1] > bic:
                                bic = res[1]
                                combo = [job_id,task_id,k,covar_type,covar_tied,n_init,subset,scale]
                                print('new bic for combo: {}:{}'.format(bic,combo))
                print('best bic for combo: {}:{}'.format(bic,combo))
                if bic > bestbic:
                    bestbic = bic
                    bestcombo = combo
                
    print('runs: {}, n_init: {}'.format(task_id,n_init))
    print('best bic overall: {}'.format(bestbic))
    print('best bic combo: {}'.format(bestcombo))
    sys.exit(1)
    

if __name__ == '__main__':
  main()
