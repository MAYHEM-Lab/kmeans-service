"""
Misc. utility functions for formatting, data wrangling, and plotting.

Author: Angad Gill
"""
import io
import os
import random
import time
import base64
import urllib.parse

import boto3

import pandas as pd
import numpy as np
import seaborn as sns
from matplotlib import pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

from flask import make_response
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, SPATIAL_COLUMNS, S3_BUCKET


def format_date_time(start_time_str):
    """ Converts epoch time string to (Date, Time) formatted as ('04 April 2017', '11:01 AM') """
    start_time = time.localtime(float(start_time_str))
    start_time_date = time.strftime("%d %B %Y", start_time)
    start_time_clock = time.strftime("%I:%M %p", start_time)
    return start_time_date, start_time_clock


def float_to_str(num):
    return '{:.4f}'.format(num)


""" Data wrangling functions """


def filter_dict_list_by_keys(dict_list, keys):
    new_dict_list = []
    for d in dict_list:
        new_d = {}
        for k, v in d.items():
            if k in keys:
                new_d[k] = v
        new_dict_list += [new_d]
    return new_dict_list


def tasks_to_best_results(tasks):
    """
    Converts tasks data into a Pandas DataFrame containing best values for k, bic, and labels.
    Response DF contains 'k', 'covar_type', 'covar_tied', 'bic', 'labels'

    """
    # Filter list of dicts to reduce the size of Pandas DataFrame
    df = pd.DataFrame(filter_dict_list_by_keys(tasks, ['k', 'covar_type', 'covar_tied', 'bic', '_id']))

    # Subset df to needed columns and fix types
    df['bic'] = df['bic'].astype('float')
    df['k'] = df['k'].astype('int')

    # For each covar_type and covar_tied, find k that has the best (max.) mean bic
    df_best_mean_bic = df.groupby(['covar_type', 'covar_tied', 'k'], as_index=False).mean()
    df_best_mean_bic = df_best_mean_bic.sort_values('bic', ascending=False)
    df_best_mean_bic = df_best_mean_bic.groupby(['covar_type', 'covar_tied'], as_index=False).first()

    # Get labels from df that correspond to a bic closest to the best mean bic
    df = pd.merge(df, df_best_mean_bic, how='inner', on=['covar_type', 'covar_tied', 'k'], suffixes=('_x', '_y'))
    df = df.assign(bic_diff=abs(df.bic_x - df.bic_y))
    df = df.sort_values('bic_diff')
    df = df.groupby(['covar_type', 'covar_tied', 'k'], as_index=False).first()
    labels = []
    for row in df['_id']:
        labels += [t['labels'] for t in tasks if t['_id'] == row]

    return df['covar_type'].tolist(), df['covar_tied'].tolist(), df['k'].tolist(), labels


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

    per_done = '{:.1f}'.format(n_tasks_done / n_tasks * 100)
    per_pending = '{:.1f}'.format(n_tasks_pending / n_tasks * 100)
    per_error = '{:.1f}'.format(n_tasks_error / n_tasks * 100)

    stats = dict(n_tasks=n_tasks,
                 n_tasks_done=n_tasks_done, per_done=per_done,
                 n_tasks_pending=n_tasks_pending, per_pending=per_pending,
                 n_tasks_error=n_tasks_error, per_error=per_error,
                 n_tasks_submitted=n_tasks_submitted, per_submitted=per_submitted)
    return stats


def filter_by_min_members(tasks, min_members=10):
    filtered_tasks = []
    for task in tasks:
        if np.all(np.bincount(task['labels']) > min_members):
            filtered_tasks += [task]
    return filtered_tasks


""" Plotting functions  """


def plot_aic_bic_fig(tasks):
    sns.set(context='talk')
    # Filter list of dicts to reduce the size of Pandas DataFrame
    df = pd.DataFrame(filter_dict_list_by_keys(tasks, ['k', 'covar_type', 'covar_tied', 'bic', 'aic']))
    df['covar_type'] = [x.capitalize() for x in df['covar_type']]
    df['covar_tied'] = [['Untied', 'Tied'][x] for x in df['covar_tied']]
    df['aic'] = df['aic'].astype('float')
    df['bic'] = df['bic'].astype('float')
    df = pd.melt(df, id_vars=['k', 'covar_type', 'covar_tied'], value_vars=['aic', 'bic'], var_name='metric')
    f = sns.factorplot(x='k', y='value', col='covar_type', row='covar_tied', hue='metric', data=df,
                       row_order=['Tied', 'Untied'], col_order=['Full', 'Diag', 'Spher'], legend=True, legend_out=True,
                       n_boot=100)
    f.set_titles("{col_name}-{row_name}")
    f.set_xlabels("Num. of Clusters (k)")
    return f.fig


def plot_cluster_fig(data, columns, covar_type_tied_labels_k, show_ticks=True):
    """ Creates a 3x2 plot scatter plot using the first two columns """
    sns.set(context='talk', style='white')
    columns = columns[:2]

    fig = plt.figure()
    placement = {'full': {True: 1, False: 4}, 'diag': {True: 2, False: 5}, 'spher': {True: 3, False: 6}}

    lim_left = data[columns[0]].min()
    lim_right = data[columns[0]].max()
    lim_bottom = data[columns[1]].min()
    lim_top = data[columns[1]].max()

    for covar_type, covar_tied, labels, k in covar_type_tied_labels_k:
        plt.subplot(2, 3, placement[covar_type][covar_tied])
        plt.scatter(data[columns[0]], data[columns[1]], c=labels, cmap=plt.cm.rainbow, s=10)
        plt.xlabel(columns[0])
        plt.ylabel(columns[1])
        plt.xlim(left=lim_left, right=lim_right)
        plt.ylim(bottom=lim_bottom, top=lim_top)
        if show_ticks is False:
            plt.xticks([])
            plt.yticks([])
        plt.title('{}-{}, k={}'.format(covar_type.capitalize(), ['Untied', 'Tied'][covar_tied], k))
    plt.tight_layout()
    return fig


def plot_correlation_fig(data):
    """ Creates a correlation heat map """
    sns.set(context='talk', style='white')
    fig = plt.figure()
    sns.heatmap(data.corr(), vmin=-1, vmax=1)
    plt.tight_layout()
    return fig


def plot_count_fig(tasks):
    """ Creates a 3x2 plot of the number (count) of data points for each k in each covar. """
    sns.set(context='talk')
    df = pd.DataFrame(filter_dict_list_by_keys(tasks, ['k', 'covar_type', 'covar_tied']))
    df = df.loc[:, ['k', 'covar_type', 'covar_tied', 'bic', 'aic']]
    df['covar_type'] = [x.capitalize() for x in df['covar_type']]
    df['covar_tied'] = [['Untied', 'Tied'][x] for x in df['covar_tied']]
    f = sns.factorplot(x='k', kind='count', col='covar_type', row='covar_tied', data=df,
                      row_order=['Tied', 'Untied'], col_order=['Full', 'Diag', 'Spher'], legend=True, legend_out=True,
                      palette='Blues_d')
    f.set_titles("{col_name}-{row_name}")
    return f.fig


def plot_spatial_cluster_fig(data, covar_type_tied_labels_k):
    """ Creates a 3x2 plot spatial plot using labels as the color """
    sns.set(context='talk', style='white')
    data.columns = [c.lower() for c in data.columns]
    fig = plt.figure()
    placement = {'full': {True: 1, False: 4}, 'diag': {True: 2, False: 5}, 'spher': {True: 3, False: 6}}

    lim_left = data['longitude'].min()
    lim_right = data['longitude'].max()
    lim_bottom = data['latitude'].min()
    lim_top = data['latitude'].max()
    for covar_type, covar_tied, labels, k in covar_type_tied_labels_k:
        plt.subplot(2, 3, placement[covar_type][covar_tied])
        plt.scatter(data['longitude'], data['latitude'], c=labels, cmap=plt.cm.rainbow, s=10)
        plt.xlim(left=lim_left, right=lim_right)
        plt.ylim(bottom=lim_bottom, top=lim_top)
        plt.xticks([])
        plt.yticks([])
        plt.xlabel('Longitude')
        plt.ylabel('Latitude')
        plt.title('{}-{}, k={}'.format(covar_type.capitalize(), ['Untied', 'Tied'][covar_tied], k))
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
    s3_file_key = generate_s3_file_key(job_id, filename)
    s3 = boto3.resource('s3')
    s3.meta.client.upload_file(filepath, S3_BUCKET, s3_file_key)
    return s3_file_key


def s3_to_df(s3_file_key):
    """ Downloads file from S3 and converts it to a Pandas DataFrame. """
    s3 = boto3.client('s3')
    # Add random number to file name to avoid collisions with other processes on the same machine
    file_name = '/tmp/{}_{}'.format(s3_file_key.replace('/', '_'), random.randint(1, 1e6))
    s3.download_file(S3_BUCKET, s3_file_key, file_name)
    df = pd.read_csv(file_name)
    os.remove(file_name)
    return df
