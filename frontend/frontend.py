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

from flask import Flask, request, make_response
from flask import render_template

import boto3
from boto3.dynamodb.conditions import Attr

import io

from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
import seaborn as sns

import pandas as pd

DYNAMO_URL = 'https://dynamodb.us-west-1.amazonaws.com'
DYNAMO_TABLE = 'test_table'
DYNAMO_REGION = 'us-west-1'
S3_BUCKET = 'kmeansservice'

app = Flask(__name__)


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/status/')
@app.route('/status/<job_id>')
def status(job_id=None):
    """ Pull information on all tasks for a job from DynamoDB and render as a table """
    if job_id:
        tasks = get_tasks(job_id)
        n_tasks = len(tasks)
        n_tasks_done = len([x for x in tasks if x['task_status']=='done'])
        per_done = '{:.1f}'.format(n_tasks_done/n_tasks*100)
        return render_template('status.html', job_id=job_id, n_tasks=n_tasks, n_tasks_done=n_tasks_done,
                               per_done=per_done, tasks=tasks)
    else:
        return 'Need job_id'


def get_tasks(job_id):
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

    df = pd.DataFrame(get_tasks(job_id))
    df = df.loc[:, ['k', 'covar_type', 'covar_tied', 'bic', 'aic']]
    df['covar_type'] = [x.capitalize() for x in df['covar_type']]
    df['covar_tied'] = [['Untied', 'Tied'][x] for x in df['covar_tied']]
    df['aic'] = df['aic'].astype('float')
    df['bic'] = df['bic'].astype('float')

    df = pd.melt(df, id_vars=['k', 'covar_type', 'covar_tied'], value_vars=['aic', 'bic'], var_name='metric')
    print(df.head())
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


@app.route('/submit', methods=['POST', 'GET'])
def submit():
    return request.form.get('data')


if __name__ == "__main__":
    app.run(debug=True)
