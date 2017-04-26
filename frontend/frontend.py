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
Frontend Flask server --> Amazon SNS --> Amazon Lambda
    |           |                           |   ^
    v           v                           |   |
Amazon         Amazon    <------------------+   |
S3             DynamoDB                         |
    |                                           |
    +-------------------------------------------+

Author: Angad Gill
"""

import os
import io
import random
import time
import base64
import urllib.parse

from flask import Flask, request, make_response, render_template, redirect, url_for, flash
from werkzeug.utils import secure_filename

import boto3
from boto3.dynamodb.conditions import Attr

from matplotlib import pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.dates import DateFormatter
import seaborn as sns
import pandas as pd

from submit_job import submit_job, generate_id, submit_task

from config import DYNAMO_URL, DYNAMO_TABLE, DYNAMO_REGION, S3_BUCKET

UPLOAD_FOLDER = 'data'
ALLOWED_EXTENSIONS = set(['csv'])
EXCLUDE_COLUMNS = ['longitude', 'latitude']

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
        n_tasks_done = len([x for x in tasks if x['task_status'] == 'done'])
        per_done = '{:.1f}'.format(n_tasks_done/n_tasks*100)
        return render_template('status.html', job_id=job_id, n_tasks=n_tasks, n_tasks_submitted=n_tasks_submitted,
                               n_tasks_done=n_tasks_done, per_done=per_done, tasks=tasks)


def get_tasks_from_dynamodb(job_id):
    """ Get a list of all task entries in DynamoDB for the given job_id. """
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    response = table.scan(FilterExpression=Attr('job_id').eq(int(job_id)))
    tasks = response['Items']
    return tasks


def job_id_exists(job_id):
    """ Get a list of all task entries in DynamoDB for the given job_id. """
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    response = table.scan(FilterExpression=Attr('job_id').eq(int(job_id)))
    return response['Count'] > 0


@app.route('/report/', methods=['GET', 'POST'])
@app.route('/report/<job_id>')
def report(job_id=None):
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

        tasks = get_tasks_from_dynamodb(job_id)

        n_tasks = tasks[0]['n_tasks']
        n_tasks_done = len([x for x in tasks if x['task_status'] == 'done'])
        if n_tasks != n_tasks_done:
            flash('All tasks not completed yet for job ID: {}'.format(job_id), category='danger')
            redirect(url_for('status', job_id=job_id))

        covar_type_tied_k = best_k(tasks)

        fig = plot_aic_bic_fig(tasks)
        aic_bic_plot = fig_to_png(fig)
        aic_bic_plot = png_for_template(aic_bic_plot)

        fig = plot_cluster_fig(tasks)
        cluster_plot = fig_to_png(fig)
        cluster_plot = png_for_template(cluster_plot)

        return render_template('report.html', job_id=job_id, covar_type_tied_k=covar_type_tied_k,
                               aic_bic_plot=aic_bic_plot, cluster_plot=cluster_plot)


def png_for_template(png):
    output = base64.b64encode(png.getvalue())
    output = urllib.parse.quote(output)
    return output


def best_k(tasks):
    df = pd.DataFrame(tasks)
    df = df.loc[:, ['k', 'covar_type', 'covar_tied', 'bic']]
    df = df.sort_values('bic', ascending=False)
    df = df.groupby(['covar_type', 'covar_tied']).first()
    df = df.reset_index()
    covar_type_tied_k = list(zip(df['covar_type'], df['covar_tied'], df['k'].astype('int')))
    return covar_type_tied_k


# @app.route('/plot/<type>/<job_id>')
# def plot(type=None, job_id=None):
#     if type == 'aic_bic':
#         sns.set(context='talk')
#         tasks = get_tasks_from_dynamodb(job_id)
#         fig = plot_aic_bic_fig(tasks)
#         png_response = fig_to_png_response(fig)
#     # if type ==
#     return png_response
#

def plot_aic_bic_fig(tasks):
    sns.set(context='talk')
    df = pd.DataFrame(tasks)
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


def s3_to_df(s3_file_key):
    s3 = boto3.client('s3')
    file_name = '/tmp/data_file'
    s3.download_file(S3_BUCKET, s3_file_key, file_name)
    df = pd.read_csv(file_name)
    os.remove(file_name)
    return df


def plot_cluster_fig(tasks):
    """ Creates a 3x2 plot scatter plot using the first two columns """
    sns.set(context='talk')
    df = pd.DataFrame(tasks)
    df = df.loc[:, ['k', 'covar_type', 'covar_tied', 'bic', 'labels']]
    df = df.sort_values('bic', ascending=False)
    df = df.groupby(['covar_type', 'covar_tied']).first()
    df = df.reset_index()

    s3_file_key = tasks[0]['s3_file_key']
    columns = tasks[0]['columns']
    data = s3_to_df(s3_file_key)

    fig = plt.figure()
    placement = {'full': {True: 1, False: 4}, 'diag': {True: 2, False: 5}, 'spher': {True: 3, False: 6}}
    for covar_type, covar_tied, labels in zip(df['covar_type'], df['covar_tied'], df['labels']):
        plt.subplot(2, 3, placement[covar_type][covar_tied])
        plt.scatter(data[columns[0]], data[columns[1]], c=labels, cmap=plt.cm.rainbow)
        plt.title('{}-{}'.format(covar_type.capitalize(), ['Untied', 'Tied'][covar_tied]))
    plt.tight_layout()
    return fig


def fig_to_png_response(fig):
    output = fig_to_png(fig)
    response = make_response(output.getvalue())
    response.mimetype = 'image/png'
    return response


def fig_to_png(fig):
    canvas = FigureCanvas(fig)
    output = io.BytesIO()
    canvas.print_png(output)
    return output


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def upload_to_s3(filepath, filename, job_id):
    s3_file_key = '{}/{}/{}'.format(UPLOAD_FOLDER, job_id, filename)
    s3 = boto3.resource('s3')
    s3.meta.client.upload_file(filepath, S3_BUCKET, s3_file_key)
    return s3_file_key


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
            job_id = int(request.form.get('job_id'))
            # job_id = generate_job_id()
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

            create_task_on_dynamodb(job_id, 0, n_tasks, filename)  # create one entry synchronously
            submit_job.delay(n_init, n_experiments, max_k, covars, columns, s3_file_key, filename, job_id, n_tasks)
            flash('Your request with job ID "{}" and {} tasks is being submitted. Refresh this page for updates.'.format(
                job_id, n_tasks), 'success')
            # flash('Your request with job ID {} with {} tasks is being submitted. Please visit this URL in a few '
            #       'seconds: {}.'.format(job_id, n_tasks, url_for('status', job_id=job_id, _external=True)), 'info')
            return redirect(url_for('status', job_id=job_id))

        else:
            filename = secure_filename(file.filename)
            flash('Incorrect file extension for file "{}"!'.format(filename), 'danger')
            return redirect(url_for('index'))

    else:
        return redirect(request.url)


def create_task_on_dynamodb(job_id, task_id, n_tasks, filename):
    id = generate_id(job_id, task_id)
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    item = dict(id=id, job_id=job_id, n_tasks=n_tasks, task_status='pending', filename=filename)
    response = table.put_item(Item=item)
    return response


def generate_job_id():
    min, max = 100, 1e9
    id = random.randint(min, max)
    while job_id_exists(id):
        id = random.randint(min, max)
    return id


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

    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    response = table.get_item(Key={'id': id})
    task = response['Item']

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

    submit_task(columns, covar_tied, covar_type, filename, job_id, k, n_init, n_tasks, s3_file_key, start_time,
                      task_id, task_status)

    flash('Rerunning task "{}" for job ID "{}"'.format(task_id, job_id), category='info')
    return redirect(url_for('status', job_id=job_id))


if __name__ == "__main__":
    app.run(debug=True)
