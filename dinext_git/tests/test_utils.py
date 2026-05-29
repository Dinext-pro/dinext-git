from __future__ import annotations

import frappe


def make_project() -> str:
	project_name = f"Dinext Git Test {frappe.generate_hash(length=6)}"
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"name": f"TEST-GIT-PROJ-{frappe.generate_hash(length=6)}",
			"project_name": project_name,
			"status": "Open",
			"project_type": frappe.db.get_value("Project Type", {}, "name"),
			"custom_payment_scheme": frappe.db.get_value("Project Payment Scheme", {}, "name"),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def make_task_type(name: str | None = None) -> str:
	name = name or f"Task Type {frappe.generate_hash(length=6)}"
	if frappe.db.exists("Task Type", name):
		return name

	doc = frappe.get_doc(
		{
			"doctype": "Task Type",
			"name": name,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def make_issue_type(name: str | None = None) -> str:
	name = name or f"Issue Type {frappe.generate_hash(length=6)}"
	if frappe.db.exists("Issue Type", name):
		return name

	doc = frappe.get_doc(
		{
			"doctype": "Issue Type",
			"name": name,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def make_task(project: str | None = None, task_type: str | None = None) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": f"Traceability Task {frappe.generate_hash(length=6)}",
			"project": project,
			"status": "Open",
			"type": task_type,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def make_issue(project: str | None = None, issue_type: str | None = None) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Issue",
			"subject": f"Traceability Issue {frappe.generate_hash(length=6)}",
			"project": project,
			"status": "Open",
			"issue_type": issue_type or frappe.db.get_value("Issue Type", {}, "name"),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def make_gitlab_instance() -> str:
	doc = frappe.get_doc(
		{
			"doctype": "GitLab Instance",
			"name": f"GitLab {frappe.generate_hash(length=6)}",
			"base_url": f"https://gitlab-{frappe.generate_hash(length=6)}.example.com",
			"api_token": "token",
			"webhook_secret": f"secret-{frappe.generate_hash(length=8)}",
			"enabled": 1,
			"verify_ssl": 1,
			"timeout_seconds": 15,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def make_mapping(project: str, instance: str) -> str:
	project_doc = frappe.get_doc("Project", project)
	project_doc.append(
		"custom_git_project_mappings",
		{
			"doctype": "GitLab Project Mapping",
			"gitlab_instance": instance,
			"gitlab_group_path": "dinext",
			"gitlab_project_path": f"dinext/{frappe.generate_hash(length=6)}",
			"default_base_branch": "develop",
			"branch_naming_template": "feature/{key}-{slug}",
			"enabled": 1,
			"is_default": 1 if not (project_doc.get("custom_git_project_mappings") or []) else 0,
		},
	)
	project_doc.save(ignore_permissions=True)
	return project_doc.custom_git_project_mappings[-1].name


def add_type_visibility_rule(project: str, target_doctype: str, type_name: str | None = None) -> str:
	project_doc = frappe.get_doc("Project", project)
	row = {
		"doctype": "GitLab Type Visibility Rule",
		"target_doctype": target_doctype,
	}
	if target_doctype == "Task" and type_name:
		row["task_type"] = type_name
	elif target_doctype == "Issue" and type_name:
		row["issue_type"] = type_name

	project_doc.append("custom_git_type_visibility_rules", row)
	project_doc.save(ignore_permissions=True)
	return project_doc.custom_git_type_visibility_rules[-1].name
