#!/bin/bash
#
# Create a zip file in /tmp containing the contents of the given
# directory.

SRC_DIR=$1
TMP_DIR="/tmp/lambda_code"

mkdir -p $TMP_DIR

rsync -a $SRC_DIR $TMP_DIR --exclude .git/ --exclude __pycache__/

cd $TMP_DIR/$(basename $SRC_DIR)
zip -r "${TMP_DIR}.zip" ./*

rm -rf $TMP_DIR
