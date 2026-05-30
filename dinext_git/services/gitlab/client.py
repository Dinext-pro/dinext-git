"""Minimal GitLab REST client for Dinext Git."""

from __future__ import annotations

from urllib.parse import quote

import requests

import frappe
from frappe import _

from dinext_git.services.gitlab.store import get_instance


class GitLabClient:
	def __init__(self, instance_name: str, *, api_token: str | None = None):
		self.instance = get_instance(instance_name)
		self.base_url = self.instance["base_url"].rstrip("/")
		self.timeout = self.instance.get("timeout_seconds") or 15
		self.verify = bool(self.instance.get("verify_ssl", 1))
		self.session = requests.Session()
		token = api_token or self.instance["api_token"]
		self.session.headers.update(
			{
				"PRIVATE-TOKEN": token,
				"Content-Type": "application/json",
			}
		)

	def api_url(self, path: str) -> str:
		return f"{self.base_url}/api/v4/{path.lstrip('/')}"

	def request(self, method: str, path: str, **kwargs):
		response = self.session.request(
			method=method,
			url=self.api_url(path),
			timeout=self.timeout,
			verify=self.verify,
			**kwargs,
		)
		if response.status_code >= 400:
			if response.status_code in {401, 403}:
				frappe.throw(
					_(
						"GitLab authorization failed. Check that your token is present, valid, and has access to the selected repository."
					)
				)
			frappe.throw(
				_("GitLab API request failed: {0} {1} -> {2} {3}").format(
					method,
					path,
					response.status_code,
					response.text,
				)
			)
		if response.content:
			return response.json()
		return {}

	def get_project(self, *, project_id: str | int | None = None, project_path: str | None = None):
		if project_id:
			return self.request("GET", f"projects/{project_id}")
		if not project_path:
			frappe.throw(_("GitLab project path or id is required."))
		return self.request("GET", f"projects/{quote(project_path, safe='')}")

	def create_branch(self, project_id: str | int, branch_name: str, ref: str):
		return self.request(
			"POST",
			f"projects/{project_id}/repository/branches",
			params={"branch": branch_name, "ref": ref},
		)

	def get_branch(self, project_id: str | int, branch_name: str):
		response = self.session.request(
			method="GET",
			url=self.api_url(f"projects/{project_id}/repository/branches/{quote(branch_name, safe='')}"),
			timeout=self.timeout,
			verify=self.verify,
		)
		if response.status_code == 404:
			return None
		if response.status_code >= 400:
			if response.status_code in {401, 403}:
				frappe.throw(
					_(
						"GitLab authorization failed. Check that your token is present, valid, and has access to the selected repository."
					)
				)
			frappe.throw(
				_("GitLab API request failed: GET {0} -> {1} {2}").format(
					f"projects/{project_id}/repository/branches/{quote(branch_name, safe='')}",
					response.status_code,
					response.text,
				)
			)
		if response.content:
			return response.json()
		return {}

	def list_branches(self, project_id: str | int):
		return self.request("GET", f"projects/{project_id}/repository/branches", params={"per_page": 100})

	def list_project_hooks(self, project_id: str | int):
		return self.request("GET", f"projects/{project_id}/hooks")

	def create_project_hook(self, project_id: str | int, payload: dict):
		return self.request("POST", f"projects/{project_id}/hooks", json=payload)

	def update_project_hook(self, project_id: str | int, hook_id: str | int, payload: dict):
		return self.request("PUT", f"projects/{project_id}/hooks/{hook_id}", json=payload)

	def get_project_hook(self, project_id: str | int, hook_id: str | int):
		return self.request("GET", f"projects/{project_id}/hooks/{hook_id}")

	def list_merge_requests(self, project_id: str | int, *, updated_after: str | None = None):
		params = {"per_page": 100}
		if updated_after:
			params["updated_after"] = updated_after
		return self.request("GET", f"projects/{project_id}/merge_requests", params=params)

	def list_pipelines(self, project_id: str | int, *, updated_after: str | None = None):
		params = {"per_page": 100}
		if updated_after:
			params["updated_after"] = updated_after
		return self.request("GET", f"projects/{project_id}/pipelines", params=params)

	def get_pipeline(self, project_id: str | int, pipeline_id: str | int):
		return self.request("GET", f"projects/{project_id}/pipelines/{pipeline_id}")

	def get_pipeline_jobs(self, project_id: str | int, pipeline_id: str | int):
		return self.request("GET", f"projects/{project_id}/pipelines/{pipeline_id}/jobs")

	def list_releases(self, project_id: str | int):
		return self.request("GET", f"projects/{project_id}/releases", params={"per_page": 100})
