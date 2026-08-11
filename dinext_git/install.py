# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

"""Install / migrate hooks for Dinext Git."""

from dinext_git.setup.dinext_hub import register_dinext_hub_items


def after_install() -> None:
	register_dinext_hub_items()


def after_migrate() -> None:
	register_dinext_hub_items()
