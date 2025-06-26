#!/bin/bash -e

git pull

eval "$(conda shell.bash hook)"
conda activate pubsurveillance

cut -d$'\t' -f3 results.tsv | tail -n +2 | awk "NF" > authors.txt

python ./FindPublications.py

python slackConnector.py --messagefile msg.md --channel "C088LULD5PY"

dateNow=$(date +%Y%m%d)

git add .
git commit -m "Update $dateNow"
git push