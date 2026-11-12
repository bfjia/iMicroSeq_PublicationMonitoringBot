#! /bin/bash -e

#crontab command
#0 7 * * * cd ~/publii && sleep $((RANDOM % 3600)) && ./publii.sh >> publii.log 2>&1

#eval "$(conda shell.bash hook)"
#conda activate pubsurveillance
source ~/publii_venv/bin/activate


if [ "$(basename "$PWD")" = "tests" ]; then
	python ../slackConnector.py --message "[TEST] STARTING TEST... Test ends when you see the message TEST SUCCESS" --channel "C09D86E4T5H"

	mv ../allpubs.json ../allpubs.json.bak
	mv ../results.tsv ../results.tsv.bak
	cp test_allpubs.json ../allpubs.json
	cp test_results.tsv ../results.tsv
	
	cd ../
	  
	cut -d$'\t' -f3 results.tsv | tail -n +2 | awk "NF" > authors.txt
	
	python slackConnector.py --message "[TEST] Processing stage 1/2... This may take up to 30minutes. Feel free to have a coffee break." --channel "C09D86E4T5H"
	#Find publications
	python ./FindPublications.py

	#Post the message into Slack
	python slackConnector.py --message "[TEST] A message that found new publications should in the _publications channel" --channel "C09D86E4T5H"
	if grep -q "\[INFO\]" msg.md && grep -q "No new publication found." msg.md; then
		python slackConnector.py --messagefile msg.md --channel "C09D86E4T5H"
	else
		python slackConnector.py --messagefile msg.md --channel "C097CKA5U4X"
	fi

	python slackConnector.py --message "[TEST] Processing stage 2/2... This may take up to 30minutes. Feel free to have a coffee break." --channel "C09D86E4T5H"
	python ./FindPublications.py
	python slackConnector.py --message "[TEST] A message that did not find new publications should appear below" --channel "C09D86E4T5H"
	if grep -q "\[INFO\]" msg.md && grep -q "No new publication found." msg.md; then
		python slackConnector.py --messagefile msg.md --channel "C09D86E4T5H"
	else
		python slackConnector.py --messagefile msg.md --channel "C097CKA5U4X"
	fi
	
	python slackConnector.py --message "[TEST] TEST SUCCESS" --channel "C09D86E4T5H"
	dateNow=$(date +%Y%m%d)
	
	mv allpubs.json.bak allpubs.json
	mv results.tsv.bak results.tsv
	
else
  echo "Please run this script inside the tests folder"
fi
