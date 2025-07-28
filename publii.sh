#!/bin/bash -e

handle_error() {
	python slackConnector.py --message "The script errored out. Please see log attached." --file publii.log
}

trap handle_error ERR

git pull

#eval "$(conda shell.bash hook)"
#conda activate pubsurveillance
source ~/publii_venv/bin/activate

#Using the result.tsv file, format the authors.txt file. 
cut -d$'\t' -f3 results.tsv | tail -n +2 | awk "NF" > authors.txt

echo "There are $(wc -l < authors.txt) authors in the list to monitor."

#Find publications
python ./FindPublications.py

#Post the message into Slack
python slackConnector.py --messagefile msg.md --channel "C097CKA5U4X"

dateNow=$(date +%Y%m%d)

git add .
git commit -m "Update $dateNow"
git push

source deactivate
