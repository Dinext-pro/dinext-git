# Dinext Git

**Dinext Git** — Frappe-приложение для Git/GitLab-центричного контура команд разработки: связь рабочих элементов (`Task`, `Issue`) с ветками, merge request, pipeline и релизами. Долгосрочная цель — замена Jira для dev-команд в экосистеме Dinext.

## Границы приложения

Dinext Git **дополняет**, а не дублирует существующие модули:

| Область | Где реализовано |
|---------|-----------------|
| Проектное управление, таймшиты, Issue-расширения | `dinext_projects` |
| Gantt, burndown, story points | `dinext_project_tasks_gantt` |
| Stage-gate, scope, P&L | `dinext_project_stage_gate`, `dinext_project_scope`, `dinext_projects_pl` |
| Git/GitLab traceability, dev workflow | **Dinext Git** (этот app) |

Целевая модель traceability описана в [`dinext-docs/process/development-management/`](https://dinord.gitlab.yandexcloud.net/dinext/dinext/dinext-docs/-/tree/main/process/development-management): `Issue → branch → MR → tag → manifest → стенд`.

## Roadmap (не реализовано в текущей версии)

- GitLab Settings (URL, token, project mapping)
- Связь `Task` / `Issue` с ветками и merge request
- Статус pipeline / CI на форме задачи
- Dev Workspace в Desk
- Webhooks GitLab → Frappe

## Зависимости

Приложение требует установленные на bench:

- ERPNext (`frappe/erpnext`)
- `dinext/dinext_common`
- `dinext/dinext_projects`

## Установка

```bash
cd /path/to/frappe-bench
bench get-app administrator@dinext.invalid:dinext/dinext/dinext-git.git --branch develop
bench --site your-site.local install-app dinext_git
bench --site your-site.local migrate
bench build --app dinext_git
```

## Разработка

```bash
cd apps/dinext_git
pre-commit install
```

Инструменты: ruff, eslint, prettier (см. `.pre-commit-config.yaml`).

Ветки по [целевой модели Dinext](https://dinord.gitlab.yandexcloud.net/dinext/dinext/dinext-docs/-/blob/main/process/development-management/target-model.md): `feature/*` → `develop` (Dev-bench) → `release/*` → `main` + tag `vYY.MM.DD-XX`.

## License

MIT
