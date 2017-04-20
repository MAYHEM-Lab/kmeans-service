# Create a library packge for Amazon Lambda
Instructions to create a package with all the libraries needed to run `lambda_handler.py`  
Credits: https://medium.com/@maebert/machine-learning-on-aws-lambda-5dc57127aee1

Create a EC2 instance using Amazon Linux (2GB RAM) and run the following on it.

```bash
sudo yum -y update
sudo yum -y upgrade
sudo yum -y groupinstall "Development Tools"
sudo yum -y install blas
sudo yum -y install lapack
sudo yum -y install atlas-sse3-devel
sudo yum install python27-devel python27-pip gcc
```

```bash
virtualenv ~/stack 
source ~/stack/bin/activate
sudo $VIRTUAL_ENV/bin/pip2.7 install pip --upgrade
sudo $VIRTUAL_ENV/bin/pip2.7 install --no-binary :all: numpy
sudo $VIRTUAL_ENV/bin/pip2.7 install --no-binary :all: scipy
sudo $VIRTUAL_ENV/bin/pip2.7 install --no-binary :all: sklearn
```


```bash
sudo -E bash
find $VIRTUAL_ENV/lib*/python2.7/site-packages/ -name *.so | xargs strip
exit
```

```bash
pushd $VIRTUAL_ENV/lib/python2.7/site-packages/
zip -r -9 -q ~/lambda.zip *
popd
pushd $VIRTUAL_ENV/lib64/python2.7/site-packages/
zip -r -9 -q ~/lambda.zip *
popd
```

```bash
mkdir lib
cp /usr/lib64/atlas-sse3/liblapack.so.3 lib/.
cp /usr/lib64/atlas-sse3/libptf77blas.so.3 lib/.
cp /usr/lib64/atlas-sse3/libf77blas.so.3 lib/.
cp /usr/lib64/atlas-sse3/libptcblas.so.3 lib/.
cp /usr/lib64/atlas-sse3/libcblas.so.3 lib/.
cp /usr/lib64/atlas-sse3/libatlas.so.3 lib/.
cp /usr/lib64/atlas-sse3/libptf77blas.so.3 lib/.
cp /usr/lib64/libgfortran.so.3 lib/.
cp /usr/lib64/libquadmath.so.0 lib/.
zip -r -9 -q ~/lambda.zip lib/
```

```bash
scp -i pemfile.pem ec2-user@<EC2 instance public IP>:~/lambda.zip lambda.zip
```