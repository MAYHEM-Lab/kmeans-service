"""
Simple server with interface allowing users to submit data for processing and to see status and reports when ready.

The purpose of the Frontend is to do the following:
1. Provide an interface for users to upload their data files to the Backend Storage.
2. Provide an interface for users to view the status and results of the analysis.
3. Generate all the tasks (individual K-Means fit runs) needed to complete a job.
4. Generate necessary plots and tables needed for 1. and 2.
5. Allow users to rerun tasks that failed.

Architecture:
Frontend Flask server --> Celery Worker
    |           |               |   ^
    v           v               |   |
Eucalyptus S3  MongoDB  <-------+   |
    |                           |   |
    |                           |   |
    +---------------------------+---+

Author: Angad Gill
"""
import matplotlib
import numpy as np
matplotlib.use('Agg')  # needed to ensure that plotting works on a server with no display

import os

from flask import request, render_template, redirect, url_for, flash, make_response
from flask_app import app
from werkzeug.utils import secure_filename

from utils import format_date_time, tasks_to_best_results, task_stats, filter_by_min_members
from utils import plot_cluster_fig, plot_single_cluster_fig, plot_aic_bic_fig, plot_count_fig, plot_correlation_fig, fig_to_png
from utils import allowed_file, upload_to_s3, s3_to_df

from database import mongo_job_id_exists, mongo_get_job, mongo_create_job, mongo_get_tasks, mongo_get_tasks_by_args
from database import mongo_add_s3_file_key, mongo_get_task
from worker import create_tasks, rerun_task
from config import UPLOAD_FOLDER, EXCLUDE_COLUMNS, SPATIAL_COLUMNS


@app.route('/', methods=['GET'])
def index():
    """
    Home page

    Returns
    -------
    html
    """
    return render_template('index.html', exclude_columns=EXCLUDE_COLUMNS)


@app.route('/status/', methods=['GET', 'POST'])
@app.route('/status/<job_id>')
def status(job_id=None):
    """
    Pull information on all tasks for a job from MongoDB and render as a table

    Parameters
    ----------
    job_id: str

    Returns
    -------
    html
    """
    if request.method == 'POST':
        job_id = request.form['job_id']
        if job_id:
            return redirect(url_for('status', job_id=job_id))
        else:
            flash("Invalid job ID!", 'danger')
            return render_template('index.html')
    if job_id is None:
        job_id = request.args.get('job_id', None)
    if job_id is None:
        flash('Job ID invalid!'.format(job_id), category='danger')
        return render_template('index.html')
    else:
        if not mongo_job_id_exists(job_id):
            flash('Job ID {} not found!'.format(job_id), category='danger')
            return render_template('index.html')

        # job_id is valid
        job = mongo_get_job(job_id)
        tasks = mongo_get_tasks(job_id)
        stats = task_stats(job['n_tasks'], tasks)
        start_time_date, start_time_clock = format_date_time(job['start_time'])
        return render_template('status.html', job_id=job_id, stats=stats, tasks=tasks, job=job,
                               start_time_date=start_time_date, start_time_clock=start_time_clock)


@app.route('/report/', methods=['GET', 'POST'])
@app.route('/report/<job_id>')
def report(job_id=None):
    """
    Generate report for a job

    Parameters
    ----------
    job_id: str
    x_axis: str
        Name of column from user dataset to be used for the x axis of the plot
    y_axis: str
        Name of column from user dataset to be used for the y axis of the plot
    min_members: int, optional
        Minimum number of members required in all clusters in an experiment to consider the experiment for the report.

    Returns
    -------
    html
    """
    if request.method == 'POST':
        job_id = request.form.get('job_id')
        x_axis = request.form.get('x_axis', None)
        y_axis = request.form.get('y_axis', None)
        min_members = request.form.get('min_members', None)
    elif request.method == 'GET':
        if job_id is None:
            job_id = request.args.get('job_id')
        x_axis = request.args.get('x_axis', None)
        y_axis = request.args.get('y_axis', None)
        min_members = request.args.get('min_members', None)
    if job_id is None:
        flash('Job ID invalid!'.format(job_id), category='danger')
        return render_template('index.html')
    if not mongo_job_id_exists(job_id):
        flash('Job ID {} not found!'.format(job_id), category='danger')
        return render_template('index.html')

    # job_id is valid
    job = mongo_get_job(job_id)
    n_tasks = job['n_tasks']
    tasks = mongo_get_tasks(job_id)
    n_tasks_done = len([x for x in tasks if x['task_status'] == 'done'])
    if n_tasks != n_tasks_done:
        flash('All tasks not completed yet for job ID: {}'.format(job_id), category='danger')
        return redirect(url_for('status', job_id=job_id))

    # all tasks are done
    if min_members is None:
        min_members = 10
    else:
        min_members = int(min_members)
    tasks = filter_by_min_members(tasks, min_members=min_members)
    start_time_date, start_time_clock = format_date_time(job['start_time'])

    covar_types, covar_tieds, ks, labels, bics, task_ids = tasks_to_best_results(tasks)

    if x_axis is None or y_axis is None:
        # Visualize the first two columns that are not on the exclude list
        viz_columns = [c for c in job['columns'] if c.lower().strip() not in EXCLUDE_COLUMNS][:2]
    else:
        viz_columns = [x_axis, y_axis]

    data = s3_to_df(job['s3_file_key'])
    columns = list(data.columns)
    spatial_columns = [c for c in columns if c.lower() in SPATIAL_COLUMNS][:2]

    # recommendations for all covariance types
    covar_type_tied_k = {}
    for covar_type in covar_types:
        covar_type_tied_k[covar_type.capitalize()] = {}

    for covar_type, covar_tied, k in zip(covar_types, covar_tieds, ks):
        covar_type_tied_k[covar_type.capitalize()][['Untied', 'Tied'][covar_tied]] = k

    # task_id for all recommended assignments
    covar_type_tied_task_id = {}
    for covar_type in covar_types:
        covar_type_tied_task_id[covar_type.capitalize()] = {}

    for covar_type, covar_tied, task_id in zip(covar_types, covar_tieds, task_ids):
        covar_type_tied_task_id[covar_type.capitalize()][['Untied', 'Tied'][covar_tied]] = task_id

    # record data about the best clustering
    best_bic_k = bics[np.argmax(bics)]
    best_bic_task_id = task_ids[np.argmax(bics)]

    return render_template('report.html', job_id=job_id, job=job, min_members=min_members,
                           covar_type_tied_k=covar_type_tied_k, covar_type_tied_task_id=covar_type_tied_task_id,
                           columns=columns, viz_columns=viz_columns, spatial_columns=spatial_columns,
                           start_time_date=start_time_date, start_time_clock=start_time_clock, best_bic_k=best_bic_k,
                           best_bic_task_id=best_bic_task_id)


@app.route('/plot/aic_bic/')
def plot_aic_bic():
    """
    Generate the AIC-BIC plot as a PNG

    Parameters
    ----------
    job_id: str
    min_members: int, optional
        Minimum number of members required in all clusters in an experiment to consider the experiment for the report.

    Returns
    -------
    image/png
    """
    job_id = request.args.get('job_id', None)
    min_members = int(request.args.get('min_members', None))
    if job_id is None:
        return None
    tasks = mongo_get_tasks(job_id)
    if min_members is not None:
        tasks = filter_by_min_members(tasks, min_members)
    fig = plot_aic_bic_fig(tasks)
    aic_bic_plot = fig_to_png(fig)
    response = make_response(aic_bic_plot.getvalue())
    response.mimetype = 'image/png'
    return response


@app.route('/plot/count/')
def plot_count():
    """
    Generate the Count plot as a PNG

    Parameters
    ----------
    job_id: str
    min_members: int, optional
        Minimum number of members required in all clusters in an experiment to consider the experiment for the report.

    Returns
    -------
    image/png
    """
    job_id = request.args.get('job_id', None)
    min_members = int(request.args.get('min_members', None))
    if job_id is None:
        return None
    tasks = mongo_get_tasks(job_id)
    if min_members is not None:
        tasks = filter_by_min_members(tasks, min_members)
    fig = plot_count_fig(tasks)
    count_plot = fig_to_png(fig)
    response = make_response(count_plot.getvalue())
    response.mimetype = 'image/png'
    return response


@app.route('/plot/cluster')
@app.route('/plot/cluster/')
def plot_cluster():
    """
    Generate the Cluster plot as a PNG

    Parameters
    ----------
    job_id: str
    x_axis: str
        Name of column from user dataset to be used for the x axis of the plot
    y_axis: str
        Name of column from user dataset to be used for the y axis of the plot

    Returns
    -------
    image/png
    """
    job_id = request.args.get('job_id')
    x_axis = request.args.get('x_axis')
    y_axis = request.args.get('y_axis')
    show_ticks = request.args.get('show_ticks', 'True') == 'True'
    min_members = int(request.args.get('min_members', None))
    plot_best = request.args.get('plot_best', 'True') == 'True'
    if job_id is None or x_axis is None or y_axis is None:
        return None

    job = mongo_get_job(job_id)
    tasks = mongo_get_tasks(job_id)

    if min_members is not None:
        tasks = filter_by_min_members(tasks, min_members)
    covar_types, covar_tieds, ks, labels, bics, task_ids = tasks_to_best_results(tasks)
    s3_file_key = job['s3_file_key']
    viz_columns = [x_axis, y_axis]
    data = s3_to_df(s3_file_key)
    if plot_best:
        fig = plot_single_cluster_fig(data, viz_columns, zip(covar_types, covar_tieds, labels, ks, bics), show_ticks)
    else:
        fig = plot_cluster_fig(data, viz_columns, zip(covar_types, covar_tieds, labels, ks, bics), show_ticks)
    cluster_plot = fig_to_png(fig)
    response = make_response(cluster_plot.getvalue())
    response.mimetype = 'image/png'
    return response


@app.route('/plot/correlation')
@app.route('/plot/correlation/')
def plot_correlation():
    """
    Generate the Correlation heat map as a PNG

    Parameters
    ----------
    job_id: str

    Returns
    -------
    image/png
    """

    job_id = request.args.get('job_id')
    if job_id is None:
        return None
    job = mongo_get_job(job_id)
    s3_file_key = job['s3_file_key']
    data = s3_to_df(s3_file_key)
    fig = plot_correlation_fig(data)
    correlation_plot = fig_to_png(fig)
    response = make_response(correlation_plot.getvalue())
    response.mimetype = 'image/png'
    return response


@app.route('/csv/labels')
@app.route('/csv/labels/')
def download_labels():
    """
    Generate CSV file for label assignment

    Parameters
    ----------
    job_id: str
    task_id: str
        converted to int in this function

    Returns
    -------
    text/csv file
    """

    job_id = request.args.get('job_id')
    if job_id is None:
        return None
    task_id = int(request.args.get('task_id'))
    if task_id is None:
        return None
    task = mongo_get_task(job_id, task_id)
    if task is None:
        return None

    covar_type = task['covar_type']
    covar_tied = task['covar_tied']
    k = task['k']
    export_filename = '{}_{}_{}_{}.csv'.format(job_id, covar_type, covar_tied, k)

    job = mongo_get_job(job_id)
    s3_file_key = job['s3_file_key']
    data = s3_to_df(s3_file_key)

    data = data.assign(Label=task['labels'])
    response = make_response(data.to_csv(index=False))
    response.headers["Content-Disposition"] = "attachment; filename={}".format(export_filename)
    response.headers["Content-Type"] = "text/csv"
    return response


@app.route('/submit', methods=['GET', 'POST'])
def submit():
    """
    Endpoint for HTML form for new job creation. Uploads user file to S3, creates job entry in database, and triggers async creations
    of all tasks needed for the job.

    Parameters
    ----------
    file: html file upload
    n_init: int
    n_experiments: int
    max_k: int
    covars: list(str)
    columns: list(str)
    scale: bool

    Returns
    -------
    redirects to index
    """
    if request.method == 'POST':
        # Ensure that file is part of the post
        if 'file' not in request.files:
            flash("No file part in form submission!", category='danger')
            return redirect(url_for('index'))

        # Ensure that files were selected by user
        file = request.files['file']
        if file.filename == '':
            flash("No selected file!", category='danger')
            return redirect(url_for('index'))

        # Ensure that file type is allowed
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            if not os.path.isdir(UPLOAD_FOLDER):
                os.mkdir(UPLOAD_FOLDER)

            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)

            n_init = int(request.form.get('n_init'))
            n_experiments = int(request.form.get('n_experiments'))
            max_k = int(request.form.get('max_k'))
            covars = request.form.getlist('covars')
            columns = request.form.getlist('columns')
            scale = 'scale' in request.form
            n_tasks = n_experiments * max_k * len(covars)

            # Create the job synchronously
            job_id = mongo_create_job(n_experiments, max_k, columns, filename, n_tasks, scale)

            s3_file_key = upload_to_s3(filepath, filename, job_id)
            response = mongo_add_s3_file_key(job_id, s3_file_key)
            os.remove(filepath)

            # Create all tasks asynchronously
            create_tasks.delay(job_id, n_init, n_experiments, max_k, covars, columns, s3_file_key, scale)
            # print('creating all tasks asynchronously')
            flash('Your request with job ID "{}" and {} tasks are being submitted. Refresh this page for updates.'.format(
                job_id, n_tasks), category='success')

            return redirect(url_for('status', job_id=job_id))

        else:
            filename = secure_filename(file.filename)
            flash('Incorrect file extension for file "{}"!'.format(filename), category='danger')
            return redirect(url_for('index'))
    else:
        return redirect(request.url)


@app.route('/rerun/', methods=['POST'])
def rerun():
    """
    Triggers rerun of tasks.

    Parameters
    ----------
    job_id: str
    task_ids: list(int)

    Returns
    -------
    redirects to status page.
    """
    job_id = request.form.get('job_id')
    task_ids = request.form.get('task_ids')
    task_ids = [int(i) for i in task_ids.split(',')]
    n = len(task_ids)
    for task_id in task_ids:
        rerun_task(job_id, task_id)

    flash('Rerunning {} tasks for job ID "{}"'.format(n, job_id), category='info')
    return redirect(url_for('status', job_id=job_id))


if __name__ == "__main__":
    app.run(debug=True)
