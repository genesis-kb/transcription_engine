#!/bin/bash
# Read EVALUATOR.md for more information on the usage of this script

source .env
bitcointranscripts="$BITCOINTRANSCRIPTS_DIR"

# Check if bitcointranscripts variable is empty
if [ -z "$bitcointranscripts" ]; then
  echo "Error: 'BITCOINTRANSCRIPTS_DIR' is not defined in the .env file."
  exit 1
fi

# Check if the Markdown file and number of commits are provided as arguments
if [ $# -ne 2 ]; then
  echo "Usage: $0 <PR_number> <number_of_commits_in_the_PR>"
  exit 1
fi

PR="$1"
pr_url="https://github.com/bitcointranscripts/bitcointranscripts/pull/$PR"
num_commits="$2" # number of existing commits

# Fetch the transcript ID using the PR url
transcript_id=$(tstbtc queue get-reviews pending | jq -r --arg pr_url "$pr_url" '.[] | select(.pr_url == $pr_url) | .transcriptId')
if [ "$transcript_id" = "" ]; then
    # PR is already merged, request 'expired' reviews
    transcript_id=$(tstbtc queue get-reviews expired | jq -r --arg pr_url "$pr_url" '.[] | select(.pr_url == $pr_url) | .transcriptId')
fi

# Fetch transcript body using the obtained transcript ID
transcript=$(tstbtc queue get-transcript "$transcript_id" | jq -r '.originalContent')
body=$(echo "$transcript" | jq -r '.body')
title=$(echo "$transcript" | jq -r '.title')
transcript_by=$(echo "$transcript" | jq -r '.transcript_by')
media=$(echo "$transcript" | jq -r '.media')
tags=$(echo "$transcript" | jq -r '.tags | @json')
speakers=$(echo "$transcript" | jq -r '.speakers | @json')
categories=$(echo "$transcript" | jq -r '.categories | @json')
date=$(echo "$transcript" | jq -r '.date')

# Change directory to the source control directory
cd "$bitcointranscripts" || { echo "Directory not found"; exit 1; }

# Checkout PR
git fetch upstream pull/"$PR"/head && git checkout FETCH_HEAD
# Check the exit status, because this command fails if
# the bitcointranscripts directory has untracked working tree files
if [ $? -ne 0 ]; then
    exit 1  # Exit the script 
fi

# Identify the added file in the last commit of the branch
added_file=$(git diff-tree --no-commit-id --name-only -r $(git rev-parse HEAD) | head -n 1)

if [ -z "$added_file" ]; then
  echo "No added or modified files found in the last commit"
  exit 1
fi

temp_file=$(mktemp)  # Create a temporary file
# Create the markdown file with the desired format
cat << EOF > $temp_file
---
title: "$title"
transcript_by: $transcript_by
media: $media
tags: $tags
speakers: $speakers
categories: $categories
date: $date
---
$body
EOF

mv "$temp_file" "$added_file"  # Create a new file named 'added_file' with the updated content

# Stage the new file
git add "$added_file"

# Create a temporary commit with the new file
git commit -m "Temporary commit with added file"

# Rebase interactively to insert the new commit before the last commit
git rebase -i "HEAD~$(expr $num_commits + 1)"
# solve merge conflicts 
git add "$added_file"
GIT_EDITOR=true git rebase --continue
git checkout --theirs -- "$added_file"
git add "$added_file"
GIT_EDITOR=true git rebase --continue

# hard reset to my commit to make it easier to review diff
git reset --soft "HEAD~$num_commits"
git reset HEAD
