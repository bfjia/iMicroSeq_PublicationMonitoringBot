#!/bin/bash -e

#crontab command
#0 7 * * * /bin/bash -c 'cd ~/iMicroSeq_PublicationMonitoringBot && sleep $((RANDOM % 3600)) && ./publii.sh >> publii.log 2>&1'


handle_error() {
	python slackConnector.py --message "The script errored out. Please see log attached." --file publii.log --channel "C09D86E4T5H"
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

#Post the message into the correct slack channel
if grep -q "\[INFO\]" msg.md && grep -q "No new publication found." msg.md; then
    python slackConnector.py --messagefile msg.md --channel "C09D86E4T5H"
else
    python slackConnector.py --messagefile msg.md --channel "C097CKA5U4X"

	#Since there's new publications, lets insert them into Google Sheets as well
	python GoogleSheetAPIConnector.py

fi

#While in QA, post the logs too. 
python slackConnector.py --message "Logs are temporarily attached for debugging purposes only, if needed." --channel "C09D86E4T5H" --file publii.log

dateNow=$(date +%Y%m%d)

git add .
git commit -m "Update $dateNow"
git push

source deactivate
