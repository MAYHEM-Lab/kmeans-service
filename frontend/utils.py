"""
Misc. utility functions and wrapper functions for interacting with DynamoDB.

Author: Angad Gill
"""
import io
import os
import random
import time
import base64
import urllib.parse

import boto3
from botocore.exceptions import ClientError

import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

from flask import make_response

from config import DYNAMO_URL, DYNAMO_TABLE, DYNAMO_REGION, S3_BUCKET
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, SPATIAL_COLUMNS, DYNAMO_RETRY_EXCEPTIONS


def format_date_time(start_time_str):
    """ Converts epoch time string to (Date, Time) formated as ('04 April 2017', '11:01 AM') """
    start_time = time.localtime(float(start_time_str))
    start_time_date = time.strftime("%d %B %Y", start_time)
    start_time_clock = time.strftime("%I:%M %p", start_time)
    return start_time_date, start_time_clock


def float_to_str(num):
    return '{:.4f}'.format(num)


def generate_id(job_id, task_id=0):
    return int('{}'.format(int(job_id))+'{0:04d}'.format(int(task_id)))


def generate_job_id():
    min, max = 100, 1e9
    id = random.randint(min, max)
    while job_id_exists(id):
        id = random.randint(min, max)
    return id


""" DynamoDB wrapper functions """


def get_tasks_from_dynamodb(job_id, max_retries=10):
    """ Get a list of all task entries in DynamoDB for the given job_id. """
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)

    tasks = []
    task_id = 0
    id = generate_id(job_id, task_id)
    item = table.get_item(Key={'id': id})
    if 'Item' not in item:
        return []  # item doesn't exist
    task = item['Item']
    n_tasks = int(task['n_tasks'])

    # Batch getter / reader script:
    keys = [{'id': generate_id(job_id, i)} for i in range(n_tasks)]
    batch_size = 25
    batch_keys = [keys.pop() for _ in range(min(batch_size, len(keys)))]

    retries = 0
    while len(batch_keys) > 0:
        try:
            response = dynamodb.batch_get_item(RequestItems={DYNAMO_TABLE: {'Keys': batch_keys}})

            batch_items = response['Responses'][DYNAMO_TABLE]
            tasks += batch_items

            # Handle unprocessed keys
            if len(response['UnprocessedKeys']) > 0:
                batch_keys = response['UnprocessedKeys'][DYNAMO_TABLE]['Keys']
            else:
                batch_keys = []

            retries = 0

        except ClientError as err:
            if err.response['Error']['Code'] not in DYNAMO_RETRY_EXCEPTIONS:
                raise err
            if retries > max_retries:
                raise Exception('Maximum retries reached with {}'.format(err.response['Error']['Code']))
            print('get_tasks_from_dynamodb. retry count: {}'.format(retries))
            retries += 1
            time.sleep(2 ** retries)

        batch_keys += [keys.pop() for _ in range(min(batch_size - len(batch_keys), len(keys)))]

    return tasks


def job_id_exists(job_id, max_retries=10):
    """ Check to see if a job_id exists; by checking to see if task_id=0 for that job_id exists."""
    id = generate_id(job_id)
    response = get_item_by_id(id, max_retries)
    return 'Item' in response


def get_item_by_id(id, max_retries=10):
    """ Get item by 'id' from DynamoDB """
    key = dict(id=id)
    response = get_item_by_key(key, max_retries)
    return response


def get_item_by_key(key, max_retries=10):
    """ Get item by key from DynamoDB. This method does automatic retries in case of exceptions """
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    success = False
    retries = 0
    while not success:
        try:
            response = table.get_item(Key=key)
            retries = 0
            success = True
        except ClientError as err:
            if err.response['Error']['Code'] not in DYNAMO_RETRY_EXCEPTIONS:
                raise err
            if retries > max_retries:
                raise Exception('Maximum retries reached with {}'.format(err.response['Error']['Code']))
            print('submit_job. retry count: {}'.format(retries))
            retries += 1
            time.sleep(2 ** retries)
    return response


def put_first_task_by_job_id(job_id, n_tasks, filename, max_retries=10):
    """ Put first task for a job in DynamoDB."""
    id = generate_id(job_id, 0)
    item = dict(id=id, job_id=job_id, n_tasks=n_tasks, task_status='pending', filename=filename,
                start_time=str(time.time()))
    return put_item_by_item(item, max_retries)


def put_item_by_item(item, max_retries=10):
    """ Put item in DynamoDB. This method does automatic retries in case of exceptions """
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    success = False
    retries = 0
    response = None
    while not success:
        try:
            response = table.put_item(Item=item)
            retries = 0
            success = True
        except ClientError as err:
            if err.response['Error']['Code'] not in DYNAMO_RETRY_EXCEPTIONS:
                raise err
            if retries > max_retries:
                raise Exception('Maximum retries reached with {}'.format(err.response['Error']['Code']))
            print('submit_job. retry count: {}'.format(retries))
            retries += 1
            time.sleep(2 ** retries)
    return response


def update_at_dynamo(id, aic, bic, elapsed_time, elapsed_read_time, elapsed_processing_time, labels):
    """ Update task entry on DynamoDB with computed values. """
    key = {'id': id}
    update_expression = 'SET aic=:val1, bic=:val2, elapsed_time=:val3, task_status=:val4, elapsed_read_time=:val5, ' \
                        'elapsed_processing_time=:val6, labels=:val7'
    expression_attribute_values = {':val1': aic, ':val2': bic, ':val3': elapsed_time, ':val4': 'done',
                                   ':val5': elapsed_read_time, ':val6': elapsed_processing_time, ':val7': labels}
    response = update_item_by_key(expression_attribute_values, key, update_expression)
    return response


def update_at_dynamo_error(id):
    """ Update task entry on DynamoDB with 'error' status. """
    key = {'id': id}
    update_expression = 'SET task_status = :val1'
    expression_attribute_values = {':val1': 'error'}
    response = update_item_by_key(expression_attribute_values, key, update_expression)
    return response


def update_item_by_key(expression_attribute_values, key, update_expression, max_retries=10):
    """ Updat item in DynamoDB. This method does automatic retries in case of exceptions """
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    success = False
    retries = 0
    response = None
    while not success:
        try:
            response = table.update_item(Key=key, UpdateExpression=update_expression,
                                         ExpressionAttributeValues=expression_attribute_values)
            retries = 0
            success = True
        except ClientError as err:
            if err.response['Error']['Code'] not in DYNAMO_RETRY_EXCEPTIONS:
                raise err
            if retries > max_retries:
                raise Exception('Maximum retries reached with {}'.format(err.response['Error']['Code']))
            print('submit_job. retry count: {}'.format(retries))
            retries += 1
            time.sleep(2 ** retries)
        return response


def delete_items_by_job_id(job_id):
    """ Batch delete all tasks for a job_id """
    item = get_item_by_id(generate_id(job_id))
    if 'Item' not in item:
        print('Job ID {} does not exist'.format(job_id))
        return
    n_tasks = item['Item']['n_tasks']
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    with table.batch_writer() as batch:
        for i in range(n_tasks):
            batch.delete_item(Key={'id': generate_id(job_id, i)})


""" Data wrangling functions """


def tasks_to_best_results(df):
    """
    Converts tasks data into a Pandas DataFrame containing best values for k, bic, and labels.
    Response DF contains 'k', 'covar_type', 'covar_tied', 'bic', 'labels'

    """
    # df = pd.DataFrame(tasks)

    # Subset df to needed columns and fix types
    df = df.loc[:, ['k', 'covar_type', 'covar_tied', 'bic', 'labels']]
    df['bic'] = df['bic'].astype('float')
    df['k'] = df['k'].astype('int')

    # For each covar_type and covar_tied, find k that has the best (max.) mean bic
    df_best_mean_bic = df.groupby(['covar_type', 'covar_tied', 'k'], as_index=False).mean()
    df_best_mean_bic = df_best_mean_bic.sort_values('bic', ascending=False)
    df_best_mean_bic = df_best_mean_bic.groupby(['covar_type', 'covar_tied'], as_index=False).first()

    # Get labels from df that correspond to a bic closest to the best mean bic
    df = pd.merge(df, df_best_mean_bic, how='inner', on=['covar_type', 'covar_tied', 'k'], suffixes=('_x', '_y'))
    df = df.assign(bic_diff = abs(df.bic_x - df.bic_y))
    df = df.sort_values('bic_diff')
    df = df.groupby(['covar_type', 'covar_tied', 'k'], as_index=False).first()

    # Clean up and return df
    df = df.drop(['bic_x','bic_diff'], axis=1)
    df.columns = ['covar_type', 'covar_tied', 'k', 'labels', 'bic']

    return df


def best_covar_type_tied_k(results_df):
    """ Converts a Pandas DataFrame that is grouped and sorted by BIC to a list of tuples. """
    covar_type_tied_k = list(zip(results_df['covar_type'], results_df['covar_tied'], results_df['k']))
    return covar_type_tied_k


def task_stats(n_tasks, tasks):
    n_tasks_submitted = len(tasks)
    per_submitted = '{:.0f}'.format(n_tasks_submitted / n_tasks * 100)
    n_tasks_done, n_tasks_pending, n_tasks_error = 0, 0, 0

    if n_tasks_submitted > 0:
        n_tasks_done = len([x for x in tasks if x['task_status'] == 'done'])
        n_tasks_pending = len([x for x in tasks if x['task_status'] == 'pending'])
        n_tasks_error = len([x for x in tasks if x['task_status'] == 'error'])

    per_done = '{:.0f}'.format(n_tasks_done / n_tasks * 100)
    per_pending = '{:.0f}'.format(n_tasks_pending / n_tasks * 100)
    per_error = '{:.0f}'.format(n_tasks_error / n_tasks * 100)

    stats = dict(n_tasks=n_tasks,
                 n_tasks_done=n_tasks_done, per_done=per_done,
                 n_tasks_pending=n_tasks_pending, per_pending=per_pending,
                 n_tasks_error=n_tasks_error, per_error=per_error,
                 n_tasks_submitted=n_tasks_submitted, per_submitted=per_submitted)
    return stats


""" Plotting functions  """


def plot_aic_bic_fig(df):
    sns.set(context='talk')
    # df = pd.DataFrame(tasks)
    df = df.loc[:, ['k', 'covar_type', 'covar_tied', 'bic', 'aic']]
    df['covar_type'] = [x.capitalize() for x in df['covar_type']]
    df['covar_tied'] = [['Untied', 'Tied'][x] for x in df['covar_tied']]
    df['aic'] = df['aic'].astype('float')
    df['bic'] = df['bic'].astype('float')
    df = pd.melt(df, id_vars=['k', 'covar_type', 'covar_tied'], value_vars=['aic', 'bic'], var_name='metric')
    f = sns.factorplot(x='k', y='value', col='covar_type', row='covar_tied', hue='metric', data=df,
                       row_order=['Tied', 'Untied'], col_order=['Full', 'Diag', 'Spher'], legend=True, legend_out=True)
    f.set_titles("{col_name}-{row_name}")
    return f.fig


def plot_cluster_fig(data, columns, results_df):
    """ Creates a 3x2 plot scatter plot using the first two columns """
    sns.set(context='talk', style='white')
    # df = tasks_to_best_results(tasks)
    columns = columns[:2]

    fig = plt.figure()
    placement = {'full': {True: 1, False: 4}, 'diag': {True: 2, False: 5}, 'spher': {True: 3, False: 6}}
    covar_type_tied_labels_k = zip(results_df['covar_type'], results_df['covar_tied'], results_df['labels'],
                                   results_df['k'])
    for covar_type, covar_tied, labels, k in covar_type_tied_labels_k:
        plt.subplot(2, 3, placement[covar_type][covar_tied])
        plt.scatter(data[columns[0]], data[columns[1]], c=labels, cmap=plt.cm.rainbow, s=10)
        plt.xlabel(columns[0])
        plt.ylabel(columns[1])
        plt.title('{}-{}, k={}'.format(covar_type.capitalize(), ['Untied', 'Tied'][covar_tied], k))
    plt.tight_layout()
    return fig


def plot_spatial_cluster_fig(data, results_df):
    """ Creates a 3x2 plot scatter plot using the first two columns """
    sns.set(context='talk', style='white')
    # df = tasks_to_best_results(tasks)
#     columns = columns[:2]
    data.columns = [c.lower() for c in data.columns]

    fig = plt.figure()
    placement = {'full': {True: 1, False: 4}, 'diag': {True: 2, False: 5}, 'spher': {True: 3, False: 6}}

    lim_left = data['longitude'].min()
    lim_right = data['longitude'].max()
    lim_bottom = data['latitude'].min()
    lim_top = data['latitude'].max()

    for row in results_df.itertuples():
        plt.subplot(2, 3, placement[row.covar_type][row.covar_tied])
        plt.scatter(data['longitude'], data['latitude'], c=row.labels, cmap=plt.cm.rainbow, s=10)
        plt.xlim(left=lim_left, right=lim_right)
        plt.ylim(bottom=lim_bottom, top=lim_top)
        plt.xticks([])
        plt.yticks([])
        plt.xlabel('Longitude')
        plt.ylabel('Latitude')
        plt.title('{}-{}, k={}'.format(row.covar_type.capitalize(), ['Untied', 'Tied'][row.covar_tied], row.k))

    plt.tight_layout()
    return fig


def spatial_columns_exist(data):
    """ Returns True if one of each SPATIAL_COLUMNS exist in data (Pandas DataFrame). """
    columns = [c.lower() for c in data.columns]
    exist = [c in columns for c in SPATIAL_COLUMNS]
    return sum(exist) == 2


def fig_to_png_response(fig):
    """ Converts a matplotlib figure to an http respose png. """
    output = fig_to_png(fig)
    response = make_response(output.getvalue())
    response.mimetype = 'image/png'
    return response


def fig_to_png(fig):
    """ Converts a matplotlib figure to a png (byte stream). """
    canvas = FigureCanvas(fig)
    output = io.BytesIO()
    canvas.print_png(output)
    return output


def png_for_template(png):
    """
    Encodes a png (byte stream) so it can be passed to Jinja HTML template

    Usage in HTML:  <img src="data:image/png;base64,{{output}}"/>
    """
    output = base64.b64encode(png.getvalue())
    output = urllib.parse.quote(output)
    return output


""" File management functions """


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_s3_file_key(job_id, filename):
    return '{}/{}/{}'.format(UPLOAD_FOLDER, job_id, filename)


def upload_to_s3(filepath, filename, job_id):
    # s3_file_key = '{}/{}/{}'.format(UPLOAD_FOLDER, job_id, filename)
    s3_file_key = generate_s3_file_key(job_id, filename)
    s3 = boto3.resource('s3')
    s3.meta.client.upload_file(filepath, S3_BUCKET, s3_file_key)
    return s3_file_key


def s3_to_df(s3_file_key):
    """ Downloads file from S3 and converts it to a Pandas DataFrame. """
    s3 = boto3.client('s3')
    file_name = '/tmp/data_file_{}'.format(random.randint(1, 1e6))
    s3.download_file(S3_BUCKET, s3_file_key, file_name)
    df = pd.read_csv(file_name)
    os.remove(file_name)
    return df
