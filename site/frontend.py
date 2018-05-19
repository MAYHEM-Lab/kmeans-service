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

Author: Angad Gill, Nevena Golubovic
"""
from datetime import datetime
import matplotlib
import numpy as np
import os
matplotlib.use('Agg')  # ensure that plotting works on a server with no display
from flask import request, render_template, redirect, url_for, flash, make_response
from flask_app import app
from werkzeug.utils import secure_filename

from utils import tasks_to_best_results, task_stats, tasks_to_best_task
from utils import plot_cluster_fig, plot_single_cluster_fig, plot_aic_bic_fig
from utils import plot_count_fig, plot_correlation_fig, get_viz_columns
from utils import allowed_file, upload_to_s3, s3_to_df, job_to_data, fig_to_png
from worker import create_tasks, rerun_task
from config import UPLOAD_FOLDER, EXCLUDE_COLUMNS, SPATIAL_COLUMNS
from models import Job, Task
from flask_app import db

COVAR_TYPES = ['full', 'diag', 'spher']
COVAR_TIDES = ['Untied', 'Tied']


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
        job = db.session.query(Job).filter_by(job_id=job_id).first()
        if job is None:
            flash('Job ID {} not found!'.format(job_id), category='danger')
            return render_template('index.html')
        # TODO don't load everything, load labels only per request.
        tasks = db.session.query(Task).filter_by(job_id=job_id).all()
        stats = task_stats(job.n_tasks, tasks)
        start_time = job.start_time.strftime("%Y-%m-%d %H:%M")
        return render_template('status.html', job_id=job.job_id, stats=stats,
                               tasks=tasks, job=job,
                               start_time=start_time)


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
        Minimum number of members required in all clusters in an experiment to
        consider the experiment for the report.

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

    job = db.session.query(Job).filter_by(job_id=job_id).first()
    if job is None:
        flash('Job ID {} not found!'.format(job_id), category='danger')
        return render_template('index.html')

    if job.n_tasks != db.session.query(Task).filter_by(job_id=job_id,
            task_status='done').count():
        flash('All tasks not completed yet for job ID: {}'.format(job_id),
              category='danger')
        return redirect(url_for('status', job_id=job.id))

    # all tasks are done
    if min_members is None:
        min_members = 40

    start_time = job.start_time.strftime("%Y-%m-%d %H:%M")
    best_tasks = tasks_to_best_results(job_id, min_members)

    viz_columns = get_viz_columns(job, x_axis, y_axis)
    data = s3_to_df(job.s3_file_key)
    columns = list(data.columns)
    spatial_columns = [c for c in columns if c.lower() in SPATIAL_COLUMNS][:2]

    # recommendations for all covariance types
    covar_type_tied_k = {}
    covar_type_tied_task_id = {}
    for covar_type in COVAR_TYPES:
        covar_type_tied_k[covar_type.capitalize()] = {}
        covar_type_tied_task_id[covar_type.capitalize()] = {}
    for task in best_tasks:
        covar_type_tied_k[task.covar_type.capitalize()][['Untied', 'Tied'][
            task.covar_tied]] = task.k
        covar_type_tied_task_id[task.covar_type.capitalize()][['Untied',
            'Tied'][task.covar_tied]] = task.task_id

    # record data about the best clustering
    bics = [task.bic for task in best_tasks]
    best_bic_k = bics[np.argmax(bics)]
    task_ids = [task.task_id for task in best_tasks]
    best_bic_task_id = task_ids[np.argmax(bics)]

    return render_template('report.html', job_id=job_id, job=job,
        min_members=min_members, covar_type_tied_k=covar_type_tied_k,
        covar_type_tied_task_id=covar_type_tied_task_id, columns=columns,
        viz_columns=viz_columns, spatial_columns=spatial_columns,
        start_time=start_time, best_bic_k=best_bic_k,
        best_bic_task_id=best_bic_task_id)


@app.route('/plot/aic_bic/')
def plot_aic_bic():
    """
    Generate the AIC-BIC plot as a PNG

    Parameters
    ----------
    job_id: str
    min_members: int, optional
        Minimum number of members required in all clusters in an experiment to
        consider the experiment for the report.

    Returns
    -------
    image/png
    """
    job_id = request.args.get('job_id', None)
    if job_id is None:
        return None
    # TODO save min members for each task in the DB
    fig = plot_aic_bic_fig(job_id)
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
        Minimum number of members required in all clusters in an experiment to
        consider the experiment for the report.

    Returns
    -------
    image/png
    """
    job_id = request.args.get('job_id', None)
    if job_id is None:
        return None
    # TODO Compute min_members and save in the DB as a field.
    fig = plot_count_fig(job_id)
    count_plot = fig_to_png(fig)
    response = make_response(count_plot.getvalue())
    response.mimetype = 'image/png'
    return response


@app.route('/report/task')
@app.route('/report/task/')
def report_task():
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
    task_id = request.args.get('task_id', None)
    x_axis = request.args.get('x_axis')
    y_axis = request.args.get('y_axis')
    plot_best = request.args.get('plot_best', 'True') == 'True'
    show_ticks = request.args.get('show_ticks', 'True') == 'True'
    if job_id is None:
        return None
    if plot_best:
        k, bic, labels, task_id = tasks_to_best_task(job_id)
    if task_id is None:
        return None
    task_id = int(task_id)
    data = job_to_data(job_id)
    columns = list(data.columns)
    viz_columns = get_viz_columns(db.session.query(Job).filter_by(job_id=job_id).first(), x_axis,
                                  y_axis)
    return render_template('report_task.html', job_id=job_id,
                           task_id=task_id, viz_columns=viz_columns,
                           columns=columns, plot_best=plot_best)


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
    best_tasks = tasks_to_best_results(job_id, min_members)
    viz_columns = [x_axis, y_axis]
    data = job_to_data(job_id)
    fig = plot_cluster_fig(data, viz_columns, best_tasks, show_ticks)
    cluster_plot = fig_to_png(fig)
    response = make_response(cluster_plot.getvalue())
    response.mimetype = 'image/png'
    return response

@app.route('/plot/task')
@app.route('/plot/task/')
def plot_task():
    """
    Generate the Cluster plot with visualization options for a single task.

    Parameters
    ----------
    job_id: str
    task_id: str
    x_axis: str - column from the dataset to be used for plotting
    y_axis: str - column from the dataset to be used for plotting
    show_ticks: boolean
    Returns
    -------
    html
    """
    job_id = request.args.get('job_id')
    task_id = int(request.args.get('task_id'))
    x_axis = request.args.get('x_axis')
    y_axis = request.args.get('y_axis')
    show_ticks = request.args.get('show_ticks', 'True') == 'True'
    if job_id is None or task_id is None:
        return None
    data = job_to_data(job_id)
    task = db.session.query(Task).filter_by(job_id=job_id,
                                            task_id=task_id).first()
    viz_columns = get_viz_columns(db.session.query(Job).filter_by(
        job_id=job_id).first(), x_axis, y_axis)
    fig = plot_single_cluster_fig(data, viz_columns, task.labels,
                                  task.bic, task.k,
                                  show_ticks)
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
    job = db.session.query(Job).filter_by(job_id=job_id).first()
    s3_file_key = job.s3_file_key
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
    task = db.session.query(Task).filter_by(job_id=job_id, task_id=task_id).first()
    if task is None:
        return None

    covar_type = task.covar_type
    covar_tied = task.covar_type
    k = task.k
    export_filename = '{}_{}_{}_{}.csv'.format(job_id, covar_type, covar_tied, k)

    job = db.session.query(Job).filter_by(job_id=job_id).first()
    s3_file_key = job.s3_file_key
    data = s3_to_df(s3_file_key)

    data = data.assign(Label=task.labels)
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
            pr = [n_experiments, max_k, columns, filename, n_tasks,
                      scale]

            # Create the job synchronously
            job = Job(n_experiments=n_experiments, n_init=n_init, max_k=max_k,
                      scale=scale, columns=columns, filename=filename,
                      n_tasks=n_tasks, start_time=datetime.utcnow())
            s3_file_key = upload_to_s3(filepath, filename, job.job_id)
            job.s3_file_key = s3_file_key
            db.session.add(job)
            db.session.commit()
            os.remove(filepath)

            # Create all tasks asynchronously
            create_tasks.apply_async((job.job_id, n_init, n_experiments, max_k,
                covars, columns, s3_file_key, scale), queue = 'high')
            print('creating all tasks asynchronously')
            flash('Your request with job ID "{}" and {} tasks are being submitted. Refresh this page for updates.'.format(
                str(job.job_id), n_tasks), category='success')

            return redirect(url_for('status', job_id=str(job.job_id)))

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
