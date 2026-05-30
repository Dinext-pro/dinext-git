from __future__ import annotations

import re

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.services.gitlab.matcher import (
	clear_matcher_caches,
	extract_candidate_keys,
	naming_series_to_regex,
	resolve_key,
	resolve_keys,
)
from dinext_git.services.gitlab.normalizer import normalize_merge_request_event, normalize_push_event
from dinext_git.tests.test_utils import make_gitlab_instance, make_issue, make_key_alias, make_mapping, make_project, make_task


class TestMetaAwareMatcher(FrappeTestCase):
	def setUp(self):
		clear_matcher_caches()

	def tearDown(self):
		clear_matcher_caches()

	def test_naming_series_to_regex_matches_standard_task_mask(self):
		regex = naming_series_to_regex("TASK-.YYYY.-.#####")
		self.assertTrue(re.fullmatch(regex, "TASK-2026-00001", flags=re.IGNORECASE))

	def test_naming_series_to_regex_matches_issue_naming_series(self):
		regex = naming_series_to_regex("ISS-.YYYY.-.#####")
		self.assertTrue(re.fullmatch(regex, "ISS-2026-00042", flags=re.IGNORECASE))

	def test_extract_candidate_keys_uses_task_meta_pattern(self):
		project = make_project()
		task = make_task(project)

		keys = extract_candidate_keys(f"feature/{task}-sample", f"{task} implement feature")

		self.assertIn(task.upper(), [key.upper() for key in keys])

	def test_resolve_keys_links_manual_task_name_from_gitlab_text(self):
		project = make_project()
		custom_name = f"PROJ-CUSTOM-{frappe.generate_hash(length=6).upper()}"
		make_task(project, name=custom_name)

		resolved = resolve_keys(f"feature/{custom_name}-hotfix", f"{custom_name} fix regression")

		self.assertEqual(len(resolved), 1)
		self.assertEqual(resolved[0]["doctype"], "Task")
		self.assertEqual(resolved[0]["name"], custom_name)

	def test_resolve_key_uses_development_key_alias(self):
		project = make_project()
		task = make_task(project)
		alias_value = f"LEGACY-{frappe.generate_hash(length=6).upper()}"
		make_key_alias("Task", task, alias_value, alias_type="Jira Legacy Key", project=project)
		clear_matcher_caches()

		resolved = resolve_key(alias_value)

		self.assertTrue(resolved)
		self.assertEqual(resolved["name"], task)
		self.assertEqual(resolved["resolved_by"], "Jira Legacy Key")

	def test_push_event_links_branch_for_manual_task_name(self):
		project = make_project()
		custom_name = f"MANUAL-{frappe.generate_hash(length=6).upper()}"
		make_task(project, name=custom_name)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		payload = {
			"ref": f"refs/heads/feature/{custom_name}-sample",
			"checkout_sha": "abc123",
			"user_name": "Dev User",
			"user_email": "dev@example.com",
			"project": {"web_url": "https://gitlab.example.com/dinext/project"},
			"commits": [
				{
					"id": "abc123",
					"title": "Implement feature",
					"message": f"{custom_name} implement feature",
					"url": "https://gitlab.example.com/commit/abc123",
					"author": {"name": "Dev User", "email": "dev@example.com"},
				}
			],
		}

		result = normalize_push_event(instance, mapping, payload)

		self.assertTrue(result["branch"])
		links = frappe.get_all(
			"Development Artifact Link",
			filters={"artifact": result["branch"]},
			fields=["target_doctype", "target_name", "extracted_key"],
		)
		self.assertEqual(len(links), 1)
		self.assertEqual(links[0]["target_doctype"], "Task")
		self.assertEqual(links[0]["target_name"], custom_name)

	def test_merge_request_event_links_issue_with_meta_naming_series(self):
		project = make_project()
		issue = make_issue(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		payload = {
			"object_attributes": {
				"id": 9001,
				"iid": 12,
				"title": f"{issue} sample merge request",
				"description": f"Implements {issue}",
				"state": "opened",
				"url": "https://gitlab.example.com/merge/12",
				"source_branch": f"feature/{issue}-sample",
				"target_branch": "develop",
			},
			"user": {"name": "Dev User", "email": "dev@example.com"},
		}

		result = normalize_merge_request_event(instance, mapping, payload)

		self.assertTrue(result["merge_request"])
		links = frappe.get_all(
			"Development Artifact Link",
			filters={"artifact": result["merge_request"]},
			fields=["target_doctype", "target_name"],
		)
		self.assertEqual(len(links), 1)
		self.assertEqual(links[0]["target_doctype"], "Issue")
		self.assertEqual(links[0]["target_name"], issue)

	def test_meta_patterns_are_built_from_doctype_meta(self):
		task_patterns = frappe.get_meta("Task").autoname
		self.assertIn("#", task_patterns)

		keys = extract_candidate_keys("feature/TASK-2026-00099-sample")
		self.assertIn("TASK-2026-00099", [key.upper() for key in keys])
