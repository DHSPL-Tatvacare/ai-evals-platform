"""Backend-owned permission catalog metadata and helpers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionCatalogEntry:
    id: str
    label: str
    description: str
    group_id: str
    group_label: str
    grantable: bool = True
    owner_only: bool = False


@dataclass(frozen=True)
class PermissionGroup:
    id: str
    label: str
    description: str
    permissions: tuple[PermissionCatalogEntry, ...]


_PLATFORM_GROUP = PermissionGroup(
    id='platform',
    label='Platform',
    description=(
        'Cross-tenant platform-staff actions. Grant only to operators '
        'who manage defaults that apply to every tenant.'
    ),
    permissions=(
        PermissionCatalogEntry(
            id='platform:manage',
            label='Manage platform-wide configuration',
            description=(
                'Manage platform-default settings that apply across every tenant '
                '(e.g. LLM call-site defaults seeded for tenants without their own).'
            ),
            group_id='platform',
            group_label='Platform',
        ),
    ),
)


PERMISSION_GROUPS: tuple[PermissionGroup, ...] = (
    PermissionGroup(
        id='listings',
        label='Listings',
        description='Create and remove listing records.',
        permissions=(
            PermissionCatalogEntry(
                id='listing:manage',
                label='Manage listings',
                description='Create and delete listings for the apps a role can access.',
                group_id='listings',
                group_label='Listings',
            ),
        ),
    ),
    PermissionGroup(
        id='evaluations',
        label='Evaluations',
        description='Run, export, and manage evaluation jobs and runs.',
        permissions=(
            PermissionCatalogEntry(
                id='evaluation:run',
                label='Run evaluations',
                description='Submit evaluation jobs, start workflows, and cancel in-flight runs.',
                group_id='evaluations',
                group_label='Evaluations',
            ),
            PermissionCatalogEntry(
                id='evaluation:manage',
                label='Manage evaluations',
                description='Delete evaluation records and change visibility on owned runs.',
                group_id='evaluations',
                group_label='Evaluations',
            ),
            PermissionCatalogEntry(
                id='evaluation:export',
                label='Export evaluation results',
                description='Download evaluation outputs.',
                group_id='evaluations',
                group_label='Evaluations',
            ),
        ),
    ),
    PermissionGroup(
        id='assets',
        label='Assets',
        description='Manage shareable prompts, schemas, evaluators, chat artifacts, and tags.',
        permissions=(
            PermissionCatalogEntry(
                id='asset:manage',
                label='Manage assets',
                description='Create, edit, delete, and change visibility on prompts, schemas, evaluators, tags, and related assets.',
                group_id='assets',
                group_label='Assets',
            ),
        ),
    ),
    PermissionGroup(
        id='orchestration',
        label='Orchestration',
        description='Create and manage orchestration workflows, connections, datasets, and related runtime actions.',
        permissions=(
            PermissionCatalogEntry(
                id='orchestration:manage',
                label='Manage orchestration',
                description='Create, edit, publish, run, archive, set communication-cap policy, and otherwise mutate orchestration assets and runtime actions.',
                group_id='orchestration',
                group_label='Orchestration',
            ),
        ),
    ),
    PermissionGroup(
        id='reviews',
        label='Reviews',
        description='Review evaluation outcomes and submit human overrides.',
        permissions=(
            PermissionCatalogEntry(
                id='review:manage',
                label='Manage reviews',
                description='Open review surfaces, save drafts, and finalize human review decisions.',
                group_id='reviews',
                group_label='Reviews',
            ),
        ),
    ),
    PermissionGroup(
        id='insights',
        label='Reports and insights',
        description='Generate reports and view analytics surfaces.',
        permissions=(
            PermissionCatalogEntry(
                id='report:run',
                label='Run reports',
                description='Create report runs and derived report artifacts.',
                group_id='insights',
                group_label='Reports and insights',
            ),
            PermissionCatalogEntry(
                id='insights:view',
                label='View analytics',
                description='Access analytics dashboards, summaries, and reporting views.',
                group_id='insights',
                group_label='Reports and insights',
            ),
        ),
    ),
    PermissionGroup(
        id='configuration',
        label='Configuration',
        description='Manage tenant-scoped settings, rules, and app configuration assets.',
        permissions=(
            PermissionCatalogEntry(
                id='configuration:manage',
                label='Manage configuration',
                description='Edit app settings, rule catalogs, and other configuration assets.',
                group_id='configuration',
                group_label='Configuration',
            ),
            PermissionCatalogEntry(
                id='sherlock:manage',
                label='Manage Sherlock verified queries',
                description=(
                    'Create, edit, enable/disable tenant-scoped verified '
                    'question→SQL pairs that the Sherlock data_specialist '
                    'retrieves at turn time. System-tenant rows (seeded from '
                    'JSON) remain read-only via this surface.'
                ),
                group_id='configuration',
                group_label='Configuration',
            ),
        ),
    ),
    PermissionGroup(
        id='cost',
        label='Cost & usage',
        description='View LLM spend, token usage, and manage global pricing lookups.',
        permissions=(
            PermissionCatalogEntry(
                id='cost:view',
                label='View cost & usage',
                description='Access cost dashboards, raw call logs, and current pricing rows.',
                group_id='cost',
                group_label='Cost & usage',
            ),
            PermissionCatalogEntry(
                id='cost:manage',
                label='Manage pricing & refresh catalog',
                description=(
                    'Create/edit pricing rows, refresh pricing from models.dev, '
                    'and run the cost rollup backfill.'
                ),
                group_id='cost',
                group_label='Cost & usage',
            ),
            PermissionCatalogEntry(
                id='analytics:manage',
                label='Administer analytics population',
                description=(
                    'Disable or re-enable mirror->fact mappings, trigger '
                    'historical fact backfill jobs, and inspect '
                    'log_fact_population_run rows.'
                ),
                group_id='cost',
                group_label='Cost & usage',
            ),
        ),
    ),
    PermissionGroup(
        id='scheduled_jobs',
        label='Scheduled jobs',
        description='Create and manage tenant-scoped scheduled job runs.',
        permissions=(
            PermissionCatalogEntry(
                id='schedule:manage',
                label='Manage scheduled jobs',
                description=(
                    'Create, edit, enable/disable, fire-now, and delete scheduled job '
                    'runs within the tenant.'
                ),
                group_id='scheduled_jobs',
                group_label='Scheduled jobs',
            ),
        ),
    ),
    PermissionGroup(
        id='notifications',
        label='Notifications',
        description='Tenant-wide email notification defaults, subscribers, and audit.',
        permissions=(
            PermissionCatalogEntry(
                id='notifications:manage',
                label='Manage notifications',
                description=(
                    'Configure required notifications, audit subscribers, and inspect '
                    'the email send log.'
                ),
                group_id='notifications',
                group_label='Notifications',
            ),
        ),
    ),
    PermissionGroup(
        id='users',
        label='User management',
        description='Manage users, invite links, and role assignment.',
        permissions=(
            PermissionCatalogEntry(
                id='user:manage',
                label='Manage users',
                description='Create, edit, deactivate, delete, and reset passwords for tenant users.',
                group_id='users',
                group_label='User management',
            ),
            PermissionCatalogEntry(
                id='invite_link:manage',
                label='Manage invite links',
                description='Create, deactivate, and inspect invite links. Permanent hard-delete remains owner-only.',
                group_id='users',
                group_label='User management',
            ),
            PermissionCatalogEntry(
                id='role:manage',
                label='Assign roles',
                description='Assign existing roles to users.',
                group_id='users',
                group_label='User management',
            ),
        ),
    ),
    # Platform-staff group sits last — it's a cross-tenant concern and the
    # tenant-scoped admin role editor should surface tenant permissions first.
    _PLATFORM_GROUP,
)

OWNER_ONLY_SURFACES: tuple[dict[str, str], ...] = (
    {
        'id': 'role:lifecycle',
        'label': 'Manage role lifecycle',
        'description': 'Create, update, and delete roles remains owner-only.',
    },
    {
        'id': 'tenant:configuration',
        'label': 'Manage tenant identity and configuration',
        'description': 'Tenant identity and tenant-level configuration remains owner-only.',
    },
    {
        'id': 'platform:bootstrap',
        'label': 'Platform bootstrap actions',
        'description': 'System bootstrapping and platform-only setup actions are not grantable.',
    },
)

PERMISSION_INDEX: dict[str, PermissionCatalogEntry] = {
    permission.id: permission
    for group in PERMISSION_GROUPS
    for permission in group.permissions
}

VALID_PERMISSIONS: frozenset[str] = frozenset(PERMISSION_INDEX.keys())


def get_permission_definition(permission_id: str) -> PermissionCatalogEntry | None:
    return PERMISSION_INDEX.get(permission_id)


def serialize_permission_catalog() -> dict[str, list[dict[str, object]]]:
    return {
        'groups': [
            {
                'id': group.id,
                'label': group.label,
                'description': group.description,
                'permissions': [
                    {
                        'id': permission.id,
                        'label': permission.label,
                        'description': permission.description,
                        'groupId': permission.group_id,
                        'groupLabel': permission.group_label,
                        'grantable': permission.grantable,
                        'ownerOnly': permission.owner_only,
                    }
                    for permission in group.permissions
                ],
            }
            for group in PERMISSION_GROUPS
        ],
        'ownerOnlySurfaces': list(OWNER_ONLY_SURFACES),
    }
