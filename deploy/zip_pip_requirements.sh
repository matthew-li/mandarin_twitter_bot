#!/bin/bash
#
# Create a zip file in /tmp containing installed Python modules listed
# in the given Pip requirements file.

REQUIREMENTS_FILE=$1
TMP_DIR="/tmp/lambda_pip_requirements"
PACKAGES_DIR="${TMP_DIR}/packages/python/lib/python3.8/site-packages"
VENV_DIR="${TMP_DIR}/venv"

mkdir -p $TMP_DIR
mkdir -p $PACKAGES_DIR
mkdir -p $VENV_DIR
python3.8 -m venv $VENV_DIR

. $VENV_DIR/bin/activate
pip install --target $PACKAGES_DIR -r $REQUIREMENTS_FILE
deactivate

cd $PACKAGES_DIR
zip -r "${TMP_DIR}.zip" ./*

rm -rf $TMP_DIR
