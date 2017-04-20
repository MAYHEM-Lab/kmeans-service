#!/usr/bin/env bash
aws s3 cp lambda.zip s3://kmeansservice/lambda/lambda.zip
aws lambda update-function-code --region us-west-1 --function-name test_sklearn_scipy_numpy --s3-bucket kmeansservice --s3-key lambda/lambda.zip
