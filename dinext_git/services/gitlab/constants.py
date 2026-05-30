"""Shared GitLab integration constants for Dinext Git."""

from __future__ import annotations

ARTIFACT_TYPES = (
	"branch",
	"commit",
	"merge_request",
	"pipeline",
	"job",
	"deployment",
	"release",
	"tag",
)

DELETED_ARTIFACT_STATUS = "deleted"

WEBHOOK_EVENTS = (
	"push",
	"merge_request",
	"pipeline",
)

WORK_ITEM_DOCTYPES = (
	"Task",
	"Issue",
)

ALIAS_TYPES = (
	"Dinext Key",
	"Jira Legacy Key",
)

WORKFLOW_EVENTS = (
	"branch_created",
	"branch_linked",
	"mr_opened",
	"mr_review_started",
	"mr_changes_requested",
	"mr_approved",
	"mr_merged",
	"pipeline_failed",
	"pipeline_succeeded",
	"deployment_succeeded",
)

WEBHOOK_STATUS_VALUES = (
	"missing",
	"active",
	"drifted",
	"disabled",
	"failed",
)

LINK_SOURCES = (
	"branch_name",
	"commit_message",
	"mr_title",
	"mr_description",
	"pipeline_ref",
	"deployment_ref",
	"release_ref",
	"reconcile",
	"migration",
	"branch_create",
)

MR_REVIEW_STATES = (
	"unreviewed",
	"review_started",
	"reviewed",
	"requested_changes",
	"approved",
	"unapproved",
)
