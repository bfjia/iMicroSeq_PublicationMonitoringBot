#!/bin/bash -e

#Daily pipeline. Run by .github/workflows/publii.yml; git handling is done by the workflow.
#Needs env SLACK_BOT_TOKEN (or .secret/pubiioauthtoken), OPENALEX_API_KEY, GOOGLE_SERVICE_ACCOUNT_JSON (or .secret/googleToken).
#Code is in src/, bot state in state/, generated files (msg.md, review.md, summary.md, publii.log) in output/.

PYTHON=${PYTHON:-python}
cd "$(dirname "$0")"
mkdir -p output

#Settings (channels and the isLive go-live switch) are in config.py. Booleans are printed as true/false.
readConfig() {
	$PYTHON -c "import config; v = config.$1; print(str(v).lower() if isinstance(v, bool) else v)"
}
debugChannel=$(readConfig debugChannel)
productionChannel=$(readConfig productionChannel)
isLive=$(readConfig isLive)
echo "[INFO] isLive=$isLive"

handle_error() {
	local exitCode=$?
	trap - ERR   #do not loop if Slack itself fails
	set +e
	local message="The publication bot run failed."
	if [ -n "$GITHUB_RUN_ID" ]; then
		message="$message Run: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
	fi
	if [ -f output/publii.log ]; then
		$PYTHON src/slackConnector.py --message "$message" --file output/publii.log --channel "$debugChannel"
	else
		$PYTHON src/slackConnector.py --message "$message" --channel "$debugChannel"
	fi
	exit $exitCode
}

trap handle_error ERR

#Find publications (writes output/msg.md, output/review.md, output/summary.md, state/delta.json, state/allpubs.json)
$PYTHON src/FindPublications.py

if grep -q "\[INFO\]" output/msg.md && grep -q "No new publication found." output/msg.md; then
	hasNew=false
	$PYTHON src/slackConnector.py --messagefile output/msg.md --channel "$debugChannel"
else
	hasNew=true
	if [ "$isLive" = true ]; then
		$PYTHON src/slackConnector.py --messagefile output/msg.md --channel "$productionChannel"
	else
		$PYTHON src/slackConnector.py --messagefile output/msg.md --channel "$debugChannel"
	fi
fi

#Anything needing human review goes to the debug channel
if [ -s output/review.md ]; then
	$PYTHON src/slackConnector.py --messagefile output/review.md --channel "$debugChannel"
fi

$PYTHON src/slackConnector.py --messagefile output/summary.md --channel "$debugChannel"

#Show the results in the GitHub job summary when available
if [ -n "$GITHUB_STEP_SUMMARY" ]; then
	{
		cat output/summary.md
		echo
		cat output/msg.md
		if [ -s output/review.md ]; then
			echo
			echo "### Review"
			cat output/review.md
		fi
	} >> "$GITHUB_STEP_SUMMARY"
fi

if [ "$hasNew" = true ]; then
	if [ "$isLive" = true ]; then
		$PYTHON src/GoogleSheetAPIConnector.py --live   #production sheet
	else
		$PYTHON src/GoogleSheetAPIConnector.py          #TEST copy of the sheet; never production
	fi
fi
