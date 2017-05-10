"""
Simple server to serve a user facing interface allowing them to submit data for processing
and to see reports once the they are ready.

Purposes of this server:
1) Provide an interface for users to upload their data files
2) Provide an interface for users to view the results of the analysis
3) Generate necessary assets needed for 1) and 2), such as, job_id and plot images.
4) Generate all the tasks needed to complete a job
5) Future: Re-run tasks that failed

Architecture:
Frontend Flask server ---> Amazon SNS ---> Amazon Lambda or Celery Worker
    |           |         (N/A if using     |       ^
                           Celery Worker)   |       |
    |           |                           |       |
    v           v                           |       |
Amazon         Amazon    <------------------+-------+
S3             DynamoDB                             |
    |                                               |
    +-----------------------------------------------+

Author: Angad Gill
"""
import matplotlib
matplotlib.use('Agg')  # needed to ensure that plotting works on a server with no display

import os
import time
import sys

from flask import request, render_template, redirect, url_for, flash
from flask_app import app
from werkzeug.utils import secure_filename
import pandas as pd

from utils import format_date_time
from utils import tasks_to_best_results, best_covar_type_tied_k, task_stats
from utils import plot_cluster_fig, plot_spatial_cluster_fig, plot_aic_bic_fig, png_for_template
from utils import fig_to_png, spatial_columns_exist
from utils import allowed_file, upload_to_s3, s3_to_df

from database import add_job_to_mongo, mongo_job_id_exists, mongo_get_job, mongo_create_job, mongo_get_tasks
from database import mongo_add_s3_file_key
from worker import create_tasks, rerun_task
from config import UPLOAD_FOLDER, EXCLUDE_COLUMNS


""" Flask routes """


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', exclude_columns=EXCLUDE_COLUMNS)


@app.route('/status/', methods=['GET', 'POST'])
@app.route('/status/<job_id>')
def status(job_id=None):
    """ Pull information on all tasks for a job from DynamoDB and render as a table """

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

        job = mongo_get_job(job_id)
        n_tasks = job['n_tasks']
        filename = job['filename']
        columns = job['columns']
        scale = job.get('scale', False)

        tasks = mongo_get_tasks(job_id)
        stats = task_stats(n_tasks, tasks)
        start_time_date, start_time_clock = format_date_time(job['start_time'])

        return render_template('status.html', job_id=job_id, stats=stats, tasks=tasks, filename=filename, scale=scale,
                               columns=columns, start_time_date=start_time_date, start_time_clock=start_time_clock)


@app.route('/report/', methods=['GET', 'POST'])
@app.route('/report/<job_id>')
def report(job_id=None):
    report_start_time = time.time()
    if request.method == 'POST':
        job_id = request.form.get('job_id')
    elif request.method == 'GET' and job_id is None:
        job_id = request.args.get('job_id')
    if job_id is None:
        flash('Job ID invalid!'.format(job_id), category='danger')
        return render_template('index.html')
    else:
        if not mongo_job_id_exists(job_id):
            flash('Job ID {} not found!'.format(job_id), category='danger')
            return render_template('index.html')

        db_start_time = time.time()
        job = mongo_get_job(job_id)
        n_tasks = job['n_tasks']
        tasks = mongo_get_tasks(job_id)
        print('report: size of tasks object: {:,}'.format(sys.getsizeof(tasks)))
        tasks_df = pd.DataFrame(tasks)
        print('report: size of tasks_df object: {:,}'.format(sys.getsizeof(tasks_df)))
        n_tasks_done = len([x for x in tasks if x['task_status'] == 'done'])

        if n_tasks != n_tasks_done:
            flash('All tasks not completed yet for job ID: {}'.format(job_id), category='danger')
            return redirect(url_for('status', job_id=job_id))
        print('report: db time elapsed: {:.2f}s'.format(time.time() - db_start_time))

        start_time_date, start_time_clock = format_date_time(job['start_time'])

        results_df = tasks_to_best_results(tasks_df)
        print('report: size of results_df object: {:,}'.format(sys.getsizeof(results_df)))
        covar_type_tied_k = best_covar_type_tied_k(results_df)
        print('report: size of covar_type_tied_k object: {:,}'.format(sys.getsizeof(covar_type_tied_k)))

        s3_start_time = time.time()
        filename = job['filename']
        columns = job['columns']
        s3_file_key = job['s3_file_key']
        scale = job.get('scale', False)

        # Visualize the first two columns that are not on the exclude list
        viz_columns= [c for c in job['columns'] if c.lower() not in EXCLUDE_COLUMNS][:2]
        # viz_columns = job['columns'][:2]  # Visualization done only for the first two columns

        data = s3_to_df(s3_file_key)
        print('report: s3 download and format time: {:.2f}s'.format(time.time()-s3_start_time))

        plots_start_time = time.time()
        fig = plot_aic_bic_fig(tasks_df)
        aic_bic_plot = png_for_template(fig_to_png(fig))

        fig = plot_cluster_fig(data, viz_columns, results_df)
        cluster_plot = png_for_template(fig_to_png(fig))

        spatial_cluster_plot = None
        if spatial_columns_exist(data):
            fig = plot_spatial_cluster_fig(data, results_df)
            spatial_cluster_plot = png_for_template(fig_to_png(fig))
        print('report: plot time elapsed: {:.2f}s'.format(time.time()-plots_start_time))
        print('report: report time elapsed: {:.2f}s'.format(time.time()-report_start_time))

        return render_template('report.html', job_id=job_id, filename=filename, columns=columns, scale=scale,
                               covar_type_tied_k=covar_type_tied_k,
                               cluster_plot=cluster_plot, aic_bic_plot=aic_bic_plot,
                               spatial_cluster_plot=spatial_cluster_plot, viz_columns=viz_columns,
                               start_time_date=start_time_date, start_time_clock=start_time_clock)


@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST':
        # Ensure that file is part of the post
        if 'file' not in request.files:
            flash("No file part in form submission!", 'danger')
            return redirect(url_for('index'))

        # Ensure that files were selected by user
        file = request.files['file']
        if file.filename == '':
            flash("No selected file!", 'danger')
            return redirect(url_for('index'))

        # Ensure that file type is allowed
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            if not os.path.isdir(UPLOAD_FOLDER):
                os.mkdir(UPLOAD_FOLDER)

            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            # df = pd.read_csv(filepath, nrows=1)

            # exclude_columns = 'exclude_columns' in request.form
            # if exclude_columns:
            #     columns = [c for c in df.columns if c.lower() not in EXCLUDE_COLUMNS]
            # else:
            #     columns = list(df.columns)

            n_init = int(request.form.get('n_init'))
            n_experiments = int(request.form.get('n_experiments'))
            max_k = int(request.form.get('max_k'))
            covars = request.form.getlist('covars')
            columns = request.form.getlist('columns')
            scale = 'scale' in request.form
            n_tasks = n_experiments * max_k * len(covars)
            print(columns)

            # Create the job synchronously
            job_id = mongo_create_job(n_experiments, max_k, columns, filename, n_tasks, scale)

            s3_file_key = upload_to_s3(filepath, filename, job_id)
            response = mongo_add_s3_file_key(job_id, s3_file_key)
            os.remove(filepath)

            # Create all tasks asynchronously
            create_tasks.delay(job_id, n_init, n_experiments, max_k, covars, columns, s3_file_key, scale)
            print('creating all tasks asynchronously')
            flash('Your request with job ID "{}" and {} tasks is being submitted. Refresh this page for updates.'.format(
                job_id, n_tasks), 'success')

            return redirect(url_for('status', job_id=job_id))

        else:
            filename = secure_filename(file.filename)
            flash('Incorrect file extension for file "{}"!'.format(filename), 'danger')
            return redirect(url_for('index'))

    else:
        return redirect(request.url)


@app.route('/rerun/', methods=['POST'])
def rerun():
    # if request.method == 'POST':
    #     job_id = request.form.get('job_id')
    #     task_id = int(request.form.get('task_id'))
    # elif request.method == 'GET' and job_id is None:
    #     job_id = request.args.get('job_id')
    #     task_id = int(request.args.get('task_id'))
    job_id = request.form.get('job_id')
    task_ids = request.form.get('task_ids')
    task_ids = [int(i) for i in task_ids.split(',')]
    n = len(task_ids)
    print('job_id: {}, task_ids:{}'.format(job_id, task_ids))
    for task_id in task_ids:
        rerun_task.delay(job_id, task_id)

    flash('Rerunning {} tasks for job ID "{}"'.format(n, job_id), category='info')
    return redirect(url_for('status', job_id=job_id))


if __name__ == "__main__":
    app.run(debug=True)
