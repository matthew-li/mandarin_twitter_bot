#!/bin/bash
#
# Create tables and indices in the DynamoDB instance running at the
# given endpoint.

ENDPOINT_URL=$1

# Create the Settings table.
aws dynamodb create-table \
    --table-name Settings \
    --attribute-definitions \
        AttributeName=Name,AttributeType=S \
    --key-schema \
        AttributeName=Name,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --endpoint-url $ENDPOINT_URL

# Create the Tweets table.
aws dynamodb create-table \
    --table-name Tweets \
    --attribute-definitions \
        AttributeName=Id,AttributeType=S \
        AttributeName=Date,AttributeType=S \
    --key-schema \
        AttributeName=Id,KeyType=HASH \
        AttributeName=Date,KeyType=RANGE \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --endpoint-url $ENDPOINT_URL

# Create the UnprocessedWords table.
aws dynamodb create-table \
    --table-name UnprocessedWords \
    --attribute-definitions \
        AttributeName=Id,AttributeType=S \
        AttributeName=InsertionTimestamp,AttributeType=N \
    --key-schema \
        AttributeName=Id,KeyType=HASH \
        AttributeName=InsertionTimestamp,KeyType=RANGE \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --endpoint-url $ENDPOINT_URL

# Create a GSI on Date for the Tweets table.
aws dynamodb update-table \
    --table-name Tweets \
    --attribute-definitions \
        AttributeName=Date,AttributeType=S \
        AttributeName=DateEntry,AttributeType=N \
    --global-secondary-index-updates \
        "[ \
           { \
             \"Create\": { \
               \"IndexName\": \"DateIndex\", \
               \"KeySchema\": [ \
                 { \
                   \"AttributeName\": \"Date\", \
                   \"KeyType\": \"HASH\" \
                 }, \
                 { \
                   \"AttributeName\": \"DateEntry\", \
                   \"KeyType\": \"RANGE\" \
                 } \
               ], \
               \"Projection\": { \
                 \"ProjectionType\": \"ALL\" \
               }, \
               \"ProvisionedThroughput\": { \
                 \"ReadCapacityUnits\": 5, \
                 \"WriteCapacityUnits\": 5 \
               } \
             } \
           } \
         ]" \
    --endpoint-url $ENDPOINT_URL
