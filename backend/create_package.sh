#!/usr/bin/env bash
rm lambda.zip
cp lambda_numpy_scipy_sklearn.zip.bak lambda.zip
zip -9 lambda.zip lambda_handler.py
find sf_kmeans/ -name '*.pyc' -delete
zip -9r lambda.zip sf_kmeans/
