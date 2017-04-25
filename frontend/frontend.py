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

from flask import Flask, request, make_response, render_template, redirect, url_for, flash
from werkzeug.utils import secure_filename

import boto3
from boto3.dynamodb.conditions import Attr


from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
import seaborn as sns
import pandas as pd

from submit_job import submit_job

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

    if job_id:
        tasks = get_tasks_from_dynamodb(job_id)
        if len(tasks) == 0:
            flash('Job ID {} not found!'.format(job_id), category='danger')
            return render_template('index.html')

        n_tasks = tasks[0]['n_tasks']
        n_tasks_submitted = len(tasks)
        n_tasks_done = len([x for x in tasks if x['task_status'] == 'done'])
        per_done = '{:.1f}'.format(n_tasks_done/n_tasks*100)
        return render_template('status.html', job_id=job_id, n_tasks=n_tasks, n_tasks_submitted=n_tasks_submitted,
                               n_tasks_done=n_tasks_done, per_done=per_done, tasks=tasks)
    else:
        flash('Job ID invalid!'.format(job_id), category='danger')
        return render_template('index.html')


def get_tasks_from_dynamodb(job_id):
    """ Get a list of all task entries in DynamoDB for the given job_id. """
    dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION, endpoint_url=DYNAMO_URL)
    table = dynamodb.Table(DYNAMO_TABLE)
    response = table.scan(FilterExpression=Attr('job_id').eq(int(job_id)))
    tasks = response['Items']
    return tasks


@app.route('/report/<job_id>')
def report(job_id=None):
    return render_template('report.html', job_id=job_id)


@app.route('/plot/<job_id>')
def plot(job_id=None):
    sns.set(context='talk')

    df = pd.DataFrame(get_tasks_from_dynamodb(job_id))
    df = df.loc[:, ['k', 'covar_type', 'covar_tied', 'bic', 'aic']]
    df['covar_type'] = [x.capitalize() for x in df['covar_type']]
    df['covar_tied'] = [['Untied', 'Tied'][x] for x in df['covar_tied']]
    df['aic'] = df['aic'].astype('float')
    df['bic'] = df['bic'].astype('float')

    df = pd.melt(df, id_vars=['k', 'covar_type', 'covar_tied'], value_vars=['aic', 'bic'], var_name='metric')
    f = sns.factorplot(x='k', y='value', col='covar_type', row='covar_tied', hue='metric', data=df,
                       row_order=['Tied', 'Untied'], col_order=['Full', 'Diag', 'Spher'], legend=True, legend_out=True)
    f.set_titles("{col_name} {row_name}")

    fig = f.fig
    return fig_to_png(fig)


def fig_to_png(fig):
    canvas = FigureCanvas(fig)
    output = io.BytesIO()
    canvas.print_png(output)
    response = make_response(output.getvalue())
    response.mimetype = 'image/png'
    return response


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
            s3_file_key = upload_to_s3(filepath, filename, job_id)
            flash('File "{}" uploaded successfully!'.format(filename), 'success')

            df = pd.read_csv(filepath, nrows=1)
            columns = [c for c in df.columns if c.lower() not in EXCLUDE_COLUMNS]
            os.remove(filepath)

            n_init = int(request.form.get('n_init'))
            n_experiments = int(request.form.get('n_experiments'))
            max_k = int(request.form.get('max_k'))
            covars = request.form.getlist('covars')

            n_tasks = n_experiments * max_k * len(covars)

            submit_job.delay(n_init, n_experiments, max_k, covars, columns, s3_file_key, job_id)
            flash('Your request with job ID {} with {} tasks is being submitted. Please visit this URL in a few '
                  'seconds: {}.'.format(job_id, n_tasks, url_for('status', job_id=job_id, _external=True)), 'info')
            return redirect(url_for('index'))

        else:
            filename = secure_filename(file.filename)
            flash('Incorrect file extension for file "{}"!'.format(filename), 'danger')
            return redirect(url_for('index'))

    else:
        return redirect(request.url)


if __name__ == "__main__":
    app.run(debug=True)
