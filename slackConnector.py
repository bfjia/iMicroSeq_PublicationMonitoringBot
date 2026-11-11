#Thin CLI over slack_sdk. Token from env SLACK_BOT_TOKEN, falling back to .secret/pubiioauthtoken.
#requires pip package slack-sdk
import os
import argparse
import sys
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

maxChunkLength = 3500

def getToken():
    token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    if token:
        return token
    if os.path.exists(".secret/pubiioauthtoken"):
        with open(".secret/pubiioauthtoken", 'r') as fh:
            token = fh.readline().strip()
        if token:
            return token
    print("[ERROR] Slack token not found. Set SLACK_BOT_TOKEN or place the oauth token in .secret/pubiioauthtoken (do not push it into git).")
    sys.exit(1)

def splitLongLine(line, maxLength):
    return [line[i:i+maxLength] for i in range(0, len(line), maxLength)]

def splitMessage(text, maxLength=maxChunkLength):
    #split on blank lines first, then on lines, then hard-cut anything still too long
    chunks = []
    current = ""
    for paragraph in text.split("\n\n"):
        if len(paragraph) > maxLength:
            pieces = []
            for line in paragraph.split("\n"):
                pieces.extend(splitLongLine(line, maxLength))
            sep = "\n"
        else:
            pieces = [paragraph]
            sep = "\n\n"
        for piece in pieces:
            candidate = piece if current == "" else current + sep + piece
            if len(candidate) <= maxLength:
                current = candidate
            else:
                if current != "":
                    chunks.append(current)
                current = piece
    if current.strip() != "":
        chunks.append(current)
    return chunks

def sendMessage(client, channelID, fileList, threadTS, messageText):
    ts = 0
    chunks = splitMessage(messageText) if messageText.strip() != "" else []
    for file in fileList:
        upload = client.files_upload_v2(file=file, filename=os.path.basename(file))
        link = " <" + upload['file']['permalink'] + "| > "
        if len(chunks) > 0:
            chunks[-1] = chunks[-1] + link
        else:
            chunks.append(link)
    for chunk in chunks:
        response = client.chat_postMessage(channel=channelID, text=chunk, thread_ts=threadTS, unfurl_links=False, unfurl_media=False)
        ts = response['ts']
    return ts

if __name__ == "__main__":
    parser = argparse.ArgumentParser("Duoli - Duotang's slack integration.")

    parser.add_argument("--message", type=str, default=None,
                        help="The message to be sent")
    parser.add_argument("--file", action='extend', nargs="+", default=[],
                        help="path to the file to be uploaded, can specify multiple")
    parser.add_argument("--messagefile", type=str, default=None,
                        help="The filepath for a text file to be sent as the message")
    parser.add_argument("--channel", type=str, default="C09D86E4T5H",
                        help="Specify the channel that the message should be sent to, default: publication_monitor_debug")
    parser.add_argument("--thread", type=str, default=None,
                        help="Specify the thread that the message should be sent to")

    args = parser.parse_args()

    if args.messagefile is not None:
        with open(args.messagefile, 'r') as fh:
            messageText = fh.read()
    else:
        messageText = args.message or ""

    if messageText.strip() == "" and len(args.file) == 0:
        print("[INFO] Empty message and no files, skipping Slack post.")
        sys.exit(0)

    client = WebClient(token=getToken())
    try:
        ts = sendMessage(client, args.channel, args.file, args.thread, messageText)
    except SlackApiError as e:
        print("[ERROR] Error sending message: {}".format(e))
        sys.exit(1)

    print(ts)
