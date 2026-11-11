#!/bin/bash -e

#Daily pipeline. Run by .github/workflows/publii.yml; git handling is done by the workflow.
#Needs env SLACK_BOT_TOKEN (or .secret/pubiioauthtoken), OPENALEX_API_KEY, GOOGLE_SERVICE_ACCOUNT_JSON (or .secret/googleToken).

PYTHON=${PYTHON:-python}

debugChannel="C09D86E4T5H"       #publication_monitor_debug
productionChannel="C097CKA5U4X"  #publications
#GO-LIVE SWITCH. false (testing): everything posts to the debug channel and rows go to the TEST copy of the Google Sheet.
#true: new publications post to the production channel and rows go to the PRODUCTION Google Sheet.
isLive=false

handle_error() {
	local exitCode=$?
	trap - ERR   #do not loop if Slack itself fails
	set +e
	local message="The publication bot run failed."
	if [ -n "$GITHUB_RUN_ID" ]; then
		message="$message Run: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
	fi
	if [ -f publii.log ]; then
		$PYTHON slackConnector.py --message "$message" --file publii.log --channel "$debugChannel"
	else
		$PYTHON slackConnector.py --message "$message" --channel "$debugChannel"
	fi
	exit $exitCode
}

trap handle_error ERR

#Find publications (writes msg.md, review.md, summary.md, delta.json, allpubs.json)
$PYTHON FindPublications.py

if grep -q "\[INFO\]" msg.md && grep -q "No new publication found." msg.md; then
	hasNew=false
	$PYTHON slackConnector.py --messagefile msg.md --channel "$debugChannel"
else
	hasNew=true
	if [ "$isLive" = true ]; then
		$PYTHON slackConnector.py --messagefile msg.md --channel "$productionChannel"
	else
		$PYTHON slackConnector.py --messagefile msg.md --channel "$debugChannel"
	fi
fi

#Anything needing human review goes to the debug channel
if [ -s review.md ]; then
	$PYTHON slackConnector.py --messagefile review.md --channel "$debugChannel"
fi

$PYTHON slackConnector.py --messagefile summary.md --channel "$debugChannel"

#Show the results in the GitHub job summary when available
if [ -n "$GITHUB_STEP_SUMMARY" ]; then
	{
		cat summary.md
		echo
		cat msg.md
		if [ -s review.md ]; then
			echo
			echo "### Review"
			cat review.md
		fi
	} >> "$GITHUB_STEP_SUMMARY"
fi

if [ "$hasNew" = true ]; then
	if [ "$isLive" = true ]; then
		$PYTHON GoogleSheetAPIConnector.py --live   #production sheet
	else
		$PYTHON GoogleSheetAPIConnector.py          #TEST copy of the sheet; never production
	fi
fi
