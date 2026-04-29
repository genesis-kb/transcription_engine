import base64
import os
import random
import time
from datetime import datetime, timezone
from urllib.parse import quote

import jwt
import requests

from app import logging
from app.config import settings
from app.transcript import Transcript


logger = logging.get_logger()


class GitHubAPIHandler:
    def __init__(self):
        self.app_id = settings.GITHUB_APP_ID
        self.private_key = settings.GITHUB_PRIVATE_KEY
        self.installation_id = settings.GITHUB_INSTALLATION_ID
        self.access_token = None
        self.token_expires_at = 0
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        self.repos = {
            "transcripts": {
                "owner": settings.GITHUB_REPO_OWNER,
                "name": settings.GITHUB_REPO_NAME,
            },
            "metadata": {
                "owner": settings.GITHUB_REPO_OWNER,
                "name": settings.GITHUB_METADATA_REPO_NAME,
            },
        }

    def _generate_jwt(self):
        now = int(time.time())
        payload = {"iat": now, "exp": now + 600, "iss": self.app_id}
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def _get_installation_access_token(self):
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token

        jwt_token = self._generate_jwt()
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        response = requests.post(
            f"https://api.github.com/app/installations/{self.installation_id}/access_tokens",
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        self.access_token = data["token"]
        expires_at_dt = datetime.strptime(
            data["expires_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        self.token_expires_at = expires_at_dt.timestamp()
        return self.access_token

    def _make_request(self, method, url, **kwargs):
        token = self._get_installation_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        headers.update(kwargs.pop("headers", {}))
        response = requests.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response

    def get_default_branch(self, repo_type):
        url = f"https://api.github.com/repos/{self.repos[repo_type]['owner']}/{self.repos[repo_type]['name']}"
        response = self._make_request("GET", url)
        return response.json()["default_branch"]

    def get_branch_sha(self, repo_type, branch):
        url = f"https://api.github.com/repos/{self.repos[repo_type]['owner']}/{self.repos[repo_type]['name']}/git/ref/heads/{branch}"
        response = self._make_request("GET", url)
        return response.json()["object"]["sha"]

    def create_branch(self, repo_type, branch_name, sha):
        url = f"https://api.github.com/repos/{self.repos[repo_type]['owner']}/{self.repos[repo_type]['name']}/git/refs"
        data = {"ref": f"refs/heads/{branch_name}", "sha": sha}
        response = self._make_request("POST", url, json=data)
        return response.json()

    def create_or_update_file(
        self,
        repo_type,
        file_path,
        content,
        commit_message,
        branch,
        get_sha=False,
    ):
        url = f"https://api.github.com/repos/{self.repos[repo_type]['owner']}/{self.repos[repo_type]['name']}/contents/{quote(file_path)}"
        data = {
            "message": commit_message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if get_sha:
            response = self._make_request("GET", url + f"?ref={branch}")
            data["sha"] = response.json()["sha"]

        response = self._make_request("PUT", url, json=data)
        return response.json()

    def create_pull_request(self, repo_type, title, head, base, body):
        url = f"https://api.github.com/repos/{self.repos[repo_type]['owner']}/{self.repos[repo_type]['name']}/pulls"
        data = {"title": title, "head": head, "base": base, "body": body}
        response = self._make_request("POST", url, json=data)
        return response.json()

    def push_transcripts(
        self, transcripts: list[Transcript], markdown_exporter
    ) -> str | None:
        try:
            default_branch = self.get_default_branch("transcripts")
            branch_sha = self.get_branch_sha("transcripts", default_branch)
            branch_name = (
                f"transcripts-{''.join(random.choices('0123456789', k=6))}"
            )
            self.create_branch("transcripts", branch_name, branch_sha)

            for transcript in transcripts:
                # First commit: Raw transcript
                raw_content = markdown_exporter._create_with_metadata(
                    transcript, content_key="raw"
                )
                self.create_or_update_file(
                    "transcripts",
                    transcript.output_path_with_title + ".md",
                    raw_content,
                    f'ai(transcript): "{transcript.title}" (raw)',
                    branch_name,
                )

                # Second commit: Corrected transcript
                if transcript.outputs.get("corrected_text"):
                    corrected_content = markdown_exporter._create_with_metadata(
                        transcript, content_key="corrected_text"
                    )
                    self.create_or_update_file(
                        "transcripts",
                        transcript.output_path_with_title + ".md",
                        corrected_content,
                        f'ai(transcript): "{transcript.title}" (corrected)',
                        branch_name,
                        get_sha=True,  # We need the SHA of the file to update it
                    )

            pr = self.create_pull_request(
                "transcripts",
                f"ai(transcript): Add {len(transcripts)} transcripts",
                branch_name,
                default_branch,
                f"This PR adds {len(transcripts)} new transcripts generated by [tstbtc](https://github.com/bitcointranscripts/tstbtc).",
            )

            return pr["html_url"]
        except requests.exceptions.RequestException as e:
            logger.error(
                f"An error occurred while interacting with the GitHub API: {e}"
            )
            return None

    def push_metadata(
        self, transcripts: list[Transcript], transcripts_pr_url: str
    ):
        try:
            default_branch = self.get_default_branch("metadata")
            branch_sha = self.get_branch_sha("metadata", default_branch)
            branch_name = (
                f"metadata-{''.join(random.choices('0123456789', k=6))}"
            )
            self.create_branch("metadata", branch_name, branch_sha)

            for transcript in transcripts:
                metadata_files = [
                    transcript.metadata_file,
                    transcript.outputs["transcription_service_output_file"],
                    transcript.outputs.get("dpe_file"),
                ]

                # Group all metadata files for this transcript into a single commit
                commit_files = []
                for file_path in metadata_files:
                    if file_path:
                        with open(file_path, encoding="utf-8") as file:
                            content = file.read()
                        commit_files.append(
                            {
                                "path": os.path.join(
                                    transcript.output_path_with_title,
                                    os.path.basename(file_path),
                                ),
                                "content": content,
                            }
                        )

                if commit_files:
                    self.create_commit_with_multiple_files(
                        "metadata",
                        commit_files,
                        f'ai(transcript): "{transcript.title}" ({transcript.source.loc})',
                        branch_name,
                    )

            pr_body = (
                f"This PR adds metadata for {len(transcripts)} new transcripts generated by tstbtc.\n\n"
                f"Related transcripts PR: {transcripts_pr_url}"
            )

            pr = self.create_pull_request(
                "metadata",
                f"ai(transcript): Add metadata for {len(transcripts)} transcripts",
                branch_name,
                default_branch,
                pr_body,
            )

            return pr["html_url"]
        except requests.exceptions.RequestException as e:
            logger.error(
                f"An error occurred while interacting with the GitHub API for metadata: {e}"
            )
            return None

    def create_commit_with_multiple_files(
        self, repo_type, files, commit_message, branch
    ):
        url = f"https://api.github.com/repos/{self.repos[repo_type]['owner']}/{self.repos[repo_type]['name']}/git/trees"

        # Get the latest commit SHA for the branch
        branch_sha = self.get_branch_sha(repo_type, branch)

        # Create a new tree with the new files
        new_tree = []
        for file in files:
            new_tree.append(
                {
                    "path": file["path"],
                    "mode": "100644",
                    "type": "blob",
                    "content": file["content"],
                }
            )

        tree_data = {"base_tree": branch_sha, "tree": new_tree}
        tree_response = self._make_request("POST", url, json=tree_data)
        new_tree_sha = tree_response.json()["sha"]

        # Create a new commit
        commit_url = f"https://api.github.com/repos/{self.repos[repo_type]['owner']}/{self.repos[repo_type]['name']}/git/commits"
        commit_data = {
            "message": commit_message,
            "tree": new_tree_sha,
            "parents": [branch_sha],
        }
        commit_response = self._make_request(
            "POST", commit_url, json=commit_data
        )
        new_commit_sha = commit_response.json()["sha"]

        # Update the branch reference
        ref_url = f"https://api.github.com/repos/{self.repos[repo_type]['owner']}/{self.repos[repo_type]['name']}/git/refs/heads/{branch}"
        ref_data = {"sha": new_commit_sha}
        self._make_request("PATCH", ref_url, json=ref_data)

        return new_commit_sha
