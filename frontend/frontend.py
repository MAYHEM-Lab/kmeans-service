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

from flask import Flask, request, render_template, redirect, url_for, flash
from werkzeug.utils import secure_filename

from utils import get_item_by_id, job_id_exists
from utils import get_tasks_from_dynamodb, put_first_task_by_job_id
from utils import generate_job_id, generate_id
from utils import format_date_time
from utils import tasks_to_best_results, best_covar_type_tied_k
from utils import plot_cluster_fig, plot_spatial_cluster_fig, plot_aic_bic_fig, png_for_template
from utils import fig_to_png, spatial_columns_exist
from utils import allowed_file, upload_to_s3, s3_to_df

from config import UPLOAD_FOLDER, EXCLUDE_COLUMNS

import pandas as pd

from submit_job import submit_job, submit_task


app = Flask(__name__)
app.secret_key = os.urandom(24)


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


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
        if not job_id_exists(job_id):
            flash('Job ID {} not found!'.format(job_id), category='danger')
            return render_template('index.html')

        tasks = get_tasks_from_dynamodb(job_id)

        n_tasks = tasks[0]['n_tasks']
        n_tasks_submitted = len(tasks)
        per_submitted = '{:.0f}'.format(n_tasks_submitted/n_tasks*100)
        n_tasks_done = len([x for x in tasks if x['task_status'] == 'done'])
        per_done = '{:.0f}'.format(n_tasks_done/n_tasks*100)
        n_tasks_pending = len([x for x in tasks if x['task_status'] == 'pending'])
        per_pending = '{:.0f}'.format(n_tasks_pending/n_tasks*100)
        n_tasks_error = len([x for x in tasks if x['task_status'] == 'error'])
        per_error = '{:.0f}'.format(n_tasks_error/n_tasks*100)

        stats = dict(n_tasks=n_tasks, n_tasks_done=n_tasks_done, per_done=per_done, n_tasks_pending=n_tasks_pending,
                     per_pending=per_pending, n_tasks_error=n_tasks_error, per_error=per_error,
                     n_tasks_submitted=n_tasks_submitted, per_submitted=per_submitted)

        start_time_date, start_time_clock = format_date_time(tasks[0]['start_time'])

        return render_template('status.html', job_id=job_id, stats=stats, per_done=per_done, tasks=tasks,
                               start_time_date=start_time_date, start_time_clock=start_time_clock)


@app.route('/report/', methods=['GET', 'POST'])
@app.route('/report/<job_id>')
def report(job_id=None):
    report_start_time = time.time()
    if request.method == 'POST':
        job_id = int(request.form.get('job_id'))
    elif request.method == 'GET' and job_id is None:
        job_id = int(request.args.get('job_id'))
    if job_id is None:
        flash('Job ID invalid!'.format(job_id), category='danger')
        return render_template('index.html')
    else:
        if not job_id_exists(job_id):
            flash('Job ID {} not found!'.format(job_id), category='danger')
            return render_template('index.html')

        db_start_time = time.time()
        tasks = get_tasks_from_dynamodb(job_id)
        print('report: db time elapsed: {:.2f}s'.format(time.time() - db_start_time))

        n_tasks = tasks[0]['n_tasks']
        n_tasks_done = len([x for x in tasks if x['task_status'] == 'done'])
        if n_tasks != n_tasks_done:
            flash('All tasks not completed yet for job ID: {}'.format(job_id), category='danger')
            redirect(url_for('status', job_id=job_id))

        start_time_date, start_time_clock = format_date_time(tasks[0]['start_time'])

        results_df = tasks_to_best_results(tasks)
        covar_type_tied_k = best_covar_type_tied_k(results_df)

        s3_start_time = time.time()
        s3_file_key = tasks[0]['s3_file_key']
        viz_columns = tasks[0]['columns'][:2]  # Visualization done only for the first two columns
        data = s3_to_df(s3_file_key)
        print('report: s3 download and format time: {:.2f}s'.format(time.time()-s3_start_time))

        plots_start_time = time.time()
        fig = plot_aic_bic_fig(tasks)
        aic_bic_plot = png_for_template(fig_to_png(fig))

        fig = plot_cluster_fig(data, viz_columns, results_df)
        cluster_plot = png_for_template(fig_to_png(fig))

        spatial_cluster_plot = None
        if spatial_columns_exist(data):
            fig = plot_spatial_cluster_fig(data, results_df)
            spatial_cluster_plot = png_for_template(fig_to_png(fig))
        print('report: plot time elapsed: {:.2f}s'.format(time.time()-plots_start_time))
        print('report: report time elapsed: {:.2f}s'.format(time.time()-report_start_time))

        return render_template('report.html', job_id=job_id, covar_type_tied_k=covar_type_tied_k,
                               cluster_plot=cluster_plot, aic_bic_plot=aic_bic_plot,
                               spatial_cluster_plot=spatial_cluster_plot, viz_columns=viz_columns,
                               start_time_date=start_time_date, start_time_clock=start_time_clock,
                               task_0=tasks[0])


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
            # job_id = int(request.form.get('job_id'))
            job_id = generate_job_id()
            s3_file_key = upload_to_s3(filepath, filename, job_id)
            # flash('File "{}" uploaded successfully!'.format(filename), 'success')

            df = pd.read_csv(filepath, nrows=1)
            columns = [c for c in df.columns if c.lower() not in EXCLUDE_COLUMNS]
            os.remove(filepath)

            n_init = int(request.form.get('n_init'))
            n_experiments = int(request.form.get('n_experiments'))
            max_k = int(request.form.get('max_k'))
            covars = request.form.getlist('covars')

            n_tasks = n_experiments * max_k * len(covars)

            # create one entry synchronously
            put_first_task_by_job_id(job_id, n_tasks, filename)
            print('created 1 task synchronously')

            # create all tasks asynchronously
            submit_job.delay(n_init, n_experiments, max_k, covars, columns, s3_file_key, filename, job_id, n_tasks)
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


@app.route('/rerun/', methods=['GET', 'POST'])
@app.route('/rerun/<job_id>/<task_id>', methods=['GET'])
def rerun(job_id=None, task_id=None):
    if request.method == 'POST':
        job_id = int(request.form.get('job_id'))
        task_id = int(request.form.get('task_id'))
    elif request.method == 'GET' and job_id is None:
        job_id = int(request.args.get('job_id'))
        task_id = int(request.args.get('task_id'))

    id = generate_id(job_id, task_id)

    task = get_item_by_id(id)['Item']

    columns = task['columns']
    covar_tied = task['covar_tied']
    covar_type = task['covar_type']
    filename = task['filename']
    job_id = int(task['job_id'])
    k = int(task['k'])
    n_init = int(task['n_init'])
    n_tasks = int(task['n_tasks'])
    s3_file_key = task['s3_file_key']
    start_time = str(time.time())
    task_id = int(task['task_id'])
    task_status = task['task_status']

    submit_task.delay(columns, covar_tied, covar_type, filename, job_id, k, n_init, n_tasks, s3_file_key, start_time,
                      task_id, task_status)

    flash('Rerunning task "{}" for job ID "{}"'.format(task_id, job_id), category='info')
    return redirect(url_for('status', job_id=job_id))


if __name__ == "__main__":
    app.run(debug=True)
