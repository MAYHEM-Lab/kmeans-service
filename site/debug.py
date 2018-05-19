from datetime import datetime
import matplotlib
import numpy as np
import os
matplotlib.use('Agg')  # ensure that plotting works on a server with no display
from flask import request, render_template, redirect, url_for, flash, make_response

from werkzeug.utils import secure_filename



from site.utils import tasks_to_best_results, task_stats, tasks_to_best_task
from site.utils import plot_cluster_fig, plot_single_cluster_fig, plot_aic_bic_fig
from site.utils import plot_count_fig, plot_correlation_fig, get_viz_columns
from site.utils import allowed_file, upload_to_s3, s3_to_df, job_to_data, fig_to_png
from site.worker import create_tasks, rerun_task
from site.config import UPLOAD_FOLDER, EXCLUDE_COLUMNS, SPATIAL_COLUMNS
from site.models import Job, Task
from site.flask_app import db

COVAR_TYPES = ['full', 'diag', 'spher']
COVAR_TIDES = ['Untied', 'Tied']

task = db.session.query(Task).filter_by(job_id=19, task_id=0).all()

