#! /bin/bash -e

#crontab command
#0 7 * * * cd ~/publii && sleep $((RANDOM % 3600)) && ./publii.sh >> publii.log 2>&1

#eval "$(conda shell.bash hook)"
#conda activate pubsurveillance
source ~/publii_venv/bin/activate


if [ "$(basename "$PWD")" = "tests" ]; then
	python ../slackConnector.py --message "[TEST] STARTING TEST... Test ends when you see the message TEST SUCCESS" --channel "C097CKA5U4X"

	mv ../allpubs.json ../allpubs.json.bak
	mv ../results.tsv ../results.tsv.bak
	cp test_allpubs.json ../allpubs.json
	cp test_results.tsv ../results.tsv
	
	cd ../
	  
	cut -d$'\t' -f3 results.tsv | tail -n +2 | awk "NF" > authors.txt
	
	python slackConnector.py --message "[TEST] Processing... This may take up to 30minutes. Feel free to have a coffee break." --channel "C097CKA5U4X"
	#Find publications
	python ./FindPublications.py

	#Post the message into Slack
	python slackConnector.py --message "[TEST] A message that found new publications should appear below." --channel "C097CKA5U4X"
	python slackConnector.py --messagefile msg.md --channel "C097CKA5U4X"
	
	python slackConnector.py --message "[TEST] A message that did not find new publications should appear below" --channel "C097CKA5U4X"
	python slackConnector.py --messagefile msg.md --channel "C097CKA5U4X"
	
	python slackConnector.py --message "[TEST] TEST SUCCESS" --channel "C097CKA5U4X"
	dateNow=$(date +%Y%m%d)
	
	mv allpubs.json.bak allpubs.json
	mv results.tsv.bak results.tsv
	
else
  echo "Please run this script inside the tests folder"
fi