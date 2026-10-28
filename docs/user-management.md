# User Management Guide

This guide explains how to manage users, teams, and access control in QA Studio.

## Concepts

### Teams

Teams are the primary unit of access control. An application belongs to a team, and only members of that team (plus admins) can see and interact with it.

### Roles

There are five roles, from most to least privileged. Admin is studio-wide; the other four are team roles:

| Role | Can do |
|------|--------|
| **Admin** | Everything. Studio-wide access to all teams, apps, users. Can create/delete teams, assign users, reassign apps. |
| **Team Lead** | Manage their team's members (add/remove, change roles up to Team Lead). Create, edit and delete the applications their team owns. Grant shared access. Cannot delete teams or assign Admin role. |
| **Editor** | Create and edit use cases and test suites within their team's apps. Delete execution history. Create OAuth clients bound to their team. Cannot create, edit or delete applications. |
| **Executor** | Run (execute) use cases and test suites, and read secret values while doing so. Cannot create or modify them. |
| **Viewer** | Read-only access to their team's apps, use cases, and results. |

**Important:** Admin is a studio-wide, *teamless* role — not a per-team assignment. When you create a user with the Admin role, QA Studio places them in the global `admins` Cognito group and ignores any team selection. A user with Admin has full access to the entire system, regardless of team membership. The other four roles (Team Lead, Editor, Executor, Viewer) are always scoped to a specific team.

Admin can only be granted from **Administration > Users** (`POST /users`, `PATCH /users/{id}`). The team member endpoints (`POST /teams/{id}/members`, `PATCH /teams/{id}/members/{userId}`) accept only the four team roles and reject `admin` with 400, for admins and Team Leads alike. Only the `admins` group grants admin: a `team-{id}-admin` group, if one is left over from an older release, grants nothing.

Roles are cumulative: each role inherits every permission of the roles below it (Team Lead ⊇ Editor ⊇ Executor ⊇ Viewer). This matters for feature visibility — for example, because Editor carries the OAuth client permissions, Team Leads inherit them too.

**Team Lead vs Admin.** A Team Lead's authority stops at their own team: members, the team's applications, and the team's shared-access grants. An Admin bypasses every team check, manages users and teams, reassigns applications, and is the only role that can open orphan resources (applications, use cases or test suites with no owning team). Being Team Lead of several teams never adds up to Admin.

| Team role value | Cognito group | Rank |
|---|---|---|
| `team_lead` | `team-{id}-team_lead` | 4 |
| `editor` | `team-{id}-editor` | 3 |
| `executor` | `team-{id}-executor` | 2 |
| `viewer` | `team-{id}-viewer` | 1 |
| `admin` (studio-wide, not a team role) | `admins` | bypasses team checks |

### Applications, Use Cases, and Test Suites

The access hierarchy is:

```
Team
 └── Application (owned by team via "owner_team_id")
      ├── Use Cases (inherit app's team ownership)
      └── Test Suites (inherit app's team ownership)
```

- **Applications** are the ownership boundary. Each app belongs to one team.
- **Use cases** and **test suites** live inside applications. Access is controlled at the application level — if you can see the app, you can see its contents (subject to your role's permissions).
- Users navigate to their team's apps, then manage use cases and test suites from within.

## Admin Workflows

### Creating a User

1. Go to **Administration > Users**
2. Click **Create User**
3. Enter the user's email address
4. Optionally select a team and role (you can assign later)
5. Click **Create User**

The user receives a temporary password via email. If no team is assigned, the user will see an empty dashboard until they're added to a team.

### Creating a Team

1. Go to **Administration > Teams**
2. Click **Create Team**
3. Enter a team name and optional description
4. Click **Create Team**

This creates the team and provisions 4 Cognito role groups: `team-{id}-team_lead`, `team-{id}-editor`, `team-{id}-executor` and `team-{id}-viewer`. Deleting a team also deletes a legacy `team-{id}-admin` group if one exists.

### Adding Members to a Team

1. Go to **Administration > Teams** and click a team name
2. Go to the **Members** tab
3. Click **Add Member**
4. Enter the user's email (they must already exist — created via Create User)
5. Select a role
6. Click **Add Member**

### Assigning an Application to a Team

New applications can be assigned at creation time via the Team dropdown. For existing applications:

1. Go to **Applications** and click the app name
2. Click **Assign to team** (visible to admins only)
3. Select the target team
4. Click **Reassign**

Once assigned, only that team's members (and admins) can see and interact with the application.

### Editing a User's Role

1. Go to **Administration > Users**
2. Click **Edit** next to the user
3. Change the team and/or role
4. Click **Save**

## Team Lead Workflows

Team Leads can manage their own team without needing an Admin.

### Adding Members

1. Go to **My Team** (sidebar)
2. Click **Add Member**
3. Enter the user's email and select a role (cannot assign Admin)

### Creating Applications

1. Go to **Applications** > **Create Application** (the button is shown only to Team Leads and Admins)
2. Pick one of the teams you lead in the Team dropdown (required)
3. The app will be owned by that team

Only the Team Lead of the owning team (or an Admin) can edit or delete the app afterwards. See [Application management](#application-management).

### Managing Use Cases and Test Suites

Navigate through **Applications** → click your app → manage use cases and test suites from the app's detail page.

## How Access Control Works

### What each role sees in the sidebar

| Role | Sidebar items |
|------|--------------|
| Admin | Dashboard, Applications, Use Cases, Test Suites, Templates, Teams, Users, OAuth Clients |
| Team Lead | Dashboard, Applications, Templates, My Team, OAuth Clients |
| Editor | Dashboard, Applications, Templates, OAuth Clients |
| Executor / Viewer | Dashboard, Applications, Templates |
| Unassigned (no team) | Empty dashboard with "Forbidden" — contact admin |

**Notes:**
- The **Use Cases** and **Test Suites** top-level links are admin-only. Non-admins reach use cases and test suites by navigating into an application.
- **OAuth Clients** appears for any user with the `api/oauth-clients.read`/`.write` scope — which the Editor role carries and Team Lead inherits — as well as for admins. It is *not* admin-only.

### Application visibility

- **Admins** see all applications across all teams
- **Non-admins** see only applications owned by their team
- **Unassigned users** see nothing
- `GET /teams/{id}/applications` requires membership in that team (or Admin)

### Application management

| Action | Who | Notes |
|--------|-----|-------|
| Create (`POST /applications`) | Team Lead of the team in `teamId`, or Admin | `teamId` is required (400 without it, 404 for an unknown team). Editors get 403. |
| Update (`PATCH /applications/{id}`) | Team Lead of the owning team, or Admin | Shared access never allows it, even at **Full**. |
| Delete (`DELETE /applications/{id}`) | Team Lead of the owning team, or Admin | Returns 204. Revokes the app's shared-access grants. Its use cases lose `application_id` and become orphans (Admin-only). |
| Reassign (`POST /applications/{id}/reassign`) | Admin | |
| Attach / detach use cases (`POST /applications/{id}/usecases`) | Editor on the app **and** edit on each use case's current app | Stops pulling another team's use cases into your app. |

**`base_url` audit.** Changing an application's `base_url` redirects every test of that app, so each change is written to the permission audit log as `app_base_url_change` with `details.old` and `details.new`. Updates that keep the same `base_url` aren't logged.

### Use case / test suite access

Access is inherited from the parent application:

| Action | Required role |
|--------|--------------|
| View use cases / results | Viewer or above |
| Execute use cases / suites, report execution status and artifacts | Executor or above |
| Read secret values | Executor or above (see [Secret values](#secret-values)) |
| Create / edit use cases, steps, variables, hooks, headers, secrets, schedules | Editor or above |
| Delete execution history (`DELETE .../executions/{executionId}`) | Editor or above |
| Delete use cases | Editor or above (must be creator or Admin) |

Every use case, execution, step, variable, schedule, artifact (including upload URLs), live view, wizard session and suite execution route resolves the owning application from the record and checks the caller's role in the owning team. An execution must belong to the use case in the path (`/usecase/{id}/executions/{executionId}`); a mismatched pair returns 404. Unknown IDs return 404, and other teams get 403.

**Orphan use cases and test suites** (no `application_id`) are Admin-only. Creating a use case now always needs an application: `POST /usecase`, `POST /import`, `POST /wizard/start` and `POST /templates/{id}/apply` require `application_id` and edit on that app. Moving a use case or suite to another app needs edit on the target app; clearing `application_id` is Admin-only. An Admin assigns or deletes existing orphans.

**Test suites** can only contain use cases of the suite's owning team (Admins exempt). Adding another team's use case returns 403.

#### Creator-retains-edit

There is one exception to the "Editor or above to edit" rule. The user who
**created** a use case keeps the ability to **edit** it even if their role later
drops below Editor (for example, they're moved to Executor or Viewer). This
override:

- grants **edit only** — never **delete**, and
- applies **only while the creator is still a member of the owning team**.

If the creator leaves the team, the override no longer applies. Admins always
bypass this logic.

#### Per-test-case visibility overrides

Individual use cases can carry an optional visibility override that **narrows**
who can see them within a team. An override restricts visibility to a specific
set of users (`allowed_subs`) and/or roles (`allowed_roles`). Overrides can only
*reduce* access — they never grant more than a user's team membership already
provides. Admins bypass overrides and can always see the use case. If no
override is set, standard role-based access applies.

Overrides are enforced on **view**:

- `GET /usecase/{id}`, its executions and other view routes return **404**
  (not 403) for a hidden use case, so its existence isn't leaked.
- `GET /usecases` and `GET /test-suites/{suite_id}/usecases` drop hidden use
  cases (one batched lookup per page).
- `allowed_roles` is matched against the caller's role in the **owning** team.
  A caller who reaches the app only through shared access has no owning-team
  role, so a role-restricted override hides the use case from them.
- If the override lookup fails, the use case is hidden (fail closed).
- Edit and execute follow the normal role and share rules. The worker isn't
  narrowed by overrides.

There is no API endpoint to set an override yet; records are written directly.

### Secret values

`GET /usecase/{id}/secrets/{secret_key}/value` returns a decrypted secret, so it
is limited to callers that are about to run the test:

| Caller | Allowed when |
|--------|--------------|
| User | Has `api/usecases.execute` and **execute** on the owning app: Executor+ of the owning team, or a shared team granted Execute or Full (ceiling rule applies) |
| OAuth client (M2M) | Bound to the owning team (or a team with Execute/Full share) and holds `api/usecases.execute` |
| Worker | Presents the execution token of a `pending` or `running` execution of this use case |
| Admin | Always |

Viewers, unbound OAuth clients and other teams get 403. `secret_key` must match
`^[A-Za-z0-9_.-]{1,128}$` (400 otherwise). Each read is logged with the caller,
use case and key, never the value. Listing secret **keys**
(`GET /usecase/{id}/secrets`) needs view; creating, updating and deleting
secrets need edit (`DELETE` returns 204).

### OAuth clients (M2M)

Every OAuth client is bound to one team, and its access is evaluated like a
team member's:

- `POST /oauth-clients` requires `teamId`. The caller must be Editor+ in that
  team (or Admin).
- The client's team role is the caller's role capped at **Editor** (an Admin's
  client is bound as Editor). Allowed client roles: `editor`, `executor`,
  `viewer`.
- `api/admin` and `api/teams.manage` can't be granted to an OAuth client, even
  by an Admin (400). The authorizer also strips both from any client token, so
  legacy clients that hold them lose them.
- A client can still only receive scopes its creator holds.
- **Unbound clients fail closed.** A client whose `OAUTH_CLIENTS` record has no
  `team_id` (created before this release) gets no team role, so every
  team-owned resource returns 403. Re-create it with a team.
- Listing: Admins see all clients; others see clients bound to teams where they
  are Editor+.
- Delete (204) and rotate: the creator, a Team Lead of the client's team, or an
  Admin. Rotation keeps the team binding and refuses clients that still hold
  `api/admin` or `api/teams.manage`.

### Worker execution token

The cloud worker uses one shared M2M client, so its identity alone grants
nothing. When `execute_usecase` starts an ECS task (`Scheduled` or
`OnDemandHeadless`), it mints a random token, stores only its SHA-256 hash on the
execution record, and passes the token to the task. The worker sends it as the
`X-QA-Execution-Token` header. The API accepts the worker only on the routes the
runner needs, only for that execution (and its use case or suite execution), and
only while the execution is `pending` or `running`. See
[architecture](architecture.md#worker-execution-capability) for the flow.

### Shared Access

Teams can grant other teams access to their applications:

1. Go to Team Detail > **Shared Access** tab
2. Click **Grant Access**
3. Select the target team and access level (View, Execute, or Full)

The **ceiling rule** applies: a user's effective permission on a shared app = min(their_role_permissions, shared_access_level). For example, a Viewer accessing an app shared with "Full (edit)" access remains view-only.

You cannot share an application with the team that already owns it — QA Studio rejects a grant where the target team equals the owning team. Sharing is also validated to confirm the application is actually owned by the granting team before the grant is created.

### Safeguards

- **Last-admin guard.** QA Studio counts the members of the global `admins`
  Cognito group and refuses to demote or delete the final one. Changing the last
  admin to a team role (`PATCH /users/{id}`) fails with 409 "Cannot demote the
  last admin", and deleting them (`DELETE /users/{username}`) fails with 409
  "Cannot delete the last admin". If the check itself fails, the request is
  refused (500) rather than applied. This prevents you from locking yourself out
  of studio-wide administration.
- **Gap-free role changes.** When a member's role changes, QA Studio adds the new
  role's Cognito group before removing the old one, so the user never briefly
  loses access mid-change.
- **Audit logging.** Permission changes — granting/revoking shared access, role
  changes, application `base_url` changes (`app_base_url_change`), and similar actions — are recorded to an audit log with the actor's
  identity, the action, and the affected target, so administrative changes are
  traceable.

## Unassigned Users

Users created without a team assignment:
- Can log in (Cognito account exists)
- See an empty/forbidden dashboard
- Cannot access any applications, use cases, or test suites
- Must be added to a team by an Admin or Team Lead before they can do anything

## First-time rollout

v1.3 is secure by default. Access that used to be open (team-bound checks on
every resource route, team-bound OAuth clients, the worker execution token) is
now closed until granted.

### What existing users see after upgrading

| Existing user | After the upgrade |
|---|---|
| Studio admin (`admins` Cognito group) | Unchanged. Full access to everything, including applications, use cases and suites that have no team yet. The upgrade never changes `admins` membership. |
| Regular user (legacy `users` Cognito group) | Can log in, but sees empty lists until an admin adds them to a team and assigns that team's applications. Nobody is promoted to admin. |
| Team member (`team-{id}-{role}`, installs that already used teams) | Keeps access to their team's resources, per role. |
| Legacy team "admin" (`team-{id}-admin`) | Converted to `team_lead` of that team by the [Team admin migration](#team-admin-migration). |

Existing applications without an owning team, and use cases or suites without
an application, are admin-only until assigned. Admins set up teams, add users
and assign applications after the upgrade (see
[Data that starts out closed](#data-that-starts-out-closed)). Tell regular users
before upgrading that they'll have no visible resources until then.

### Upgrade steps

Plan the upgrade in this order:

1. **Drain running executions.** Executions started before the upgrade have no
   `worker_token_hash`, so once the API stack deploys their worker calls (status,
   steps, artifacts, secret values) get 403 and the run fails. Wait until no
   execution is `pending` or `running`, and pause schedules during the deploy if
   needed.
2. **Preview the migration.** Run `npm run migrate:team-admin` (from `web-app/`)
   with the deploy credentials. It's a dry run by default and prints what it
   would change plus the incident-review report. See
   [Team admin migration](#team-admin-migration).
3. **Deploy.** `npm run deploy` runs `npm run migrate:team-admin -- --apply`
   right after `deploy:api`. It's idempotent, so re-running the deploy is safe.
   To run it by hand: `npm run migrate:team-admin -- --apply`.
4. **Re-create unbound CI OAuth clients.** Clients created before this release
   have no team and get 403 on every team-owned resource. The migration report
   lists them ("OAuth clients without a team (unbound)") with their creator.
   The **OAuth Clients** page shows them as "Unbound (no access)". Create a
   new client with the right team and scopes, update the CI secret store, then
   delete the old client.
5. **Update callers that create use cases.** `POST /import`,
   `POST /wizard/start` and `POST /templates/{id}/apply` now require
   `application_id`; `qa-studio tests import` and `tests create --from-journey`
   need `--application-id`. Wizard `step`, `restart` and `command` calls need
   `usecaseId` in the body (the web UI already sends it).
6. **Assign orphans.** Use cases and test suites without an application are now
   Admin-only. An Admin assigns them to an app or deletes them.
7. **Run the incident review** below.
8. **Run the UI suites** below.

### Incident review

Before this release a Team Lead could make anyone, including themselves, a
studio admin (security finding C-1), and any authenticated user could read other
teams' secret values. After the upgrade:

1. **Audit log search.** Search the `perm_audit` log for `member_add` and
   `role_change` entries that set role `admin` and whose actor wasn't an admin
   at the time. Treat each one as a potential escalation.
2. **`admins` group review.** Compare the current members of the `admins`
   Cognito group (printed by the migration report) against the people who
   should be admins. Demote anyone else in **Administration > Users**.
3. **Privileged OAuth clients.** Review every OAuth client holding `api/admin`
   or `api/teams.manage` (printed by the migration report; look up who created
   each one in its `OAUTH_CLIENTS` record, `created_by`). The authorizer no longer honors those
   scopes for clients, but delete the clients and rotate any secrets they could
   have read.
4. **Secrets.** If the audit turns up a suspicious actor, rotate the use case
   secrets of the teams they could reach.

### UI suites to run after deploy

Run the qa-studio suites that cover the changed flows (`qa-studio suites list`,
then `qa-studio run --suite-id <id>`), or the matching test cases in
`testcases/app/`:

- Login and navigation: `login`, `validate_homescreen`, `validate_left_menu`
- Users and roles: `add_delete_user`, `validate_user_page`
- Use cases: `create_blank_usecase`, `create_clone_use_case`,
  `use_case_edit_form`, `validate_create_use_case_options`,
  `create_usecase_with_cache`
- Templates and import: `create_from_template`, `create_delete_template`,
  `validate_templates_page`
- Execution end to end: `network_assertion_full_flow` (cloud run with the worker
  execution token)

Also check by hand what the suites don't cover yet: a Team Lead creating an
application, an Editor not seeing **Create Application**, creating an OAuth
client with a Team, and another team getting 403/404 when opening a use case by
link.

### Data that starts out closed

- **Existing applications** have no owning team, so they are treated as unowned
  and are visible only to admins until explicitly assigned to a team.
- **Existing admins** (users in the `admins` Cognito group) retain full access
  immediately — nothing changes for them.
- **Existing non-admin users** have no team membership, so they see empty lists
  until an admin sets up teams and assigns them + the relevant applications.

This is a deliberate, fail-closed rollout: access is granted intentionally
rather than left open. Expect a short setup window during which non-admin users
have no visible resources — communicate this before upgrading.

**Admin setup after upgrade:**
1. Log in as an admin (the bootstrap admin from the auth stack always qualifies).
2. Create teams (Administration → Teams).
3. Assign users to teams with appropriate roles (Administration → Users).
4. Assign applications to teams (app detail → "Assign to team").

Once an app is assigned to a team, its members gain access per their role. Until
then it remains admin-only.

## Team admin migration

Older releases created a `team-{id}-admin` group per team and let Team Leads assign it, which made the member a studio-wide admin (security finding C-1). `npm run deploy` runs `npm run migrate:team-admin -- --apply` after the API deploy to clean this up. The script is idempotent, so it's safe on every deploy and on fresh installs.

What it does, per team (and per leftover `team-*-admin` group whose team no longer exists):

1. Every membership record (`TEAM#{id}/MEMBER#{sub}`) with role `admin` becomes `team_lead`, and the user is added to `team-{id}-team_lead`. The update is conditional on the record still being `admin`, so it never creates records.
2. The `team-{id}-admin` group is deleted. A user who was in that group without an `admin` membership record loses the group and is not promoted (DynamoDB is the system of record); the report lists them.
3. The obsolete `ADMIN_COUNT/GLOBAL` counter record is deleted (the last-admin guard now counts the `admins` group).

It then prints a report for incident review: affected users, current members of `admins`, OAuth clients holding `api/admin` or `api/teams.manage`, and OAuth clients whose `OAUTH_CLIENTS` record has no `team_id`. It only reports clients; it never changes or deletes them.

Former team admins become Team Leads. If someone should stay a studio admin, an admin re-promotes them in **Administration > Users**. Review the `perm_audit` log for `member_add` / `role_change` entries that set `admin` and were made by non-admin actors.

Usage: `npm run migrate:team-admin` (dry run) or `npm run migrate:team-admin -- --apply`, from `web-app/`. Any unexpected error exits 1, which also fails `npm run deploy`.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--apply` | boolean | `false` (dry run) | Write the changes. Without it the script only prints what it would do and the report. |

| Setting | Source | Description |
|---------|--------|-------------|
| `baseName` | `configuration.json` | Selects the `{baseName}-auth` and `{baseName}-storage` stacks |
| Region | `AWS_REGION`, then `AWS_DEFAULT_REGION`, then `defaultRegion` in `configuration.json` | Region the stacks live in |
| User pool ID | `UserPoolIdOutput` output of `{baseName}-auth` | Cognito user pool to migrate |
| Table name | `dynamodbTable` output of `{baseName}-storage` | DynamoDB table to migrate |

The AWS credentials used for the deploy need `cognito-idp:ListGroups`, `ListUsersInGroup`, `CreateGroup`, `AdminAddUserToGroup`, `DeleteGroup`, `ListUserPoolClients`, `DescribeUserPoolClient`, and `dynamodb:Query`, `GetItem`, `UpdateItem`, `DeleteItem` on the table, plus `cloudformation:DescribeStacks`.

## FAQ

**Q: Can a user belong to multiple teams?**
A: The data model supports it (multiple membership records), but the current UI assumes one team per user.

**Q: What happens to apps when a team is deleted?**
A: Applications lose their `owner_team_id` and become invisible to non-admins. An admin should reassign them first.

**Q: Can I change the owner of an application?**
A: Yes — admins can click "Assign to team" on any application's detail page.

**Q: Why does a new user see "Forbidden"?**
A: They have no team assignment, so they have no scopes. The dashboard API requires `api/applications.read` which they don't have. Add them to a team to grant access.

**Q: Can I make someone an Admin of just one team?**
A: No. Admin is studio-wide and teamless. Granting Admin gives access to everything, regardless of team. If you want the highest team-scoped role, use Team Lead.

**Q: I can't demote our only admin — why?**
A: The last-admin guard blocks demoting the final admin so the studio can't be left without administration. Promote another user to Admin first, then demote the original.

**Q: Our CI pipeline started getting 403 after the upgrade — why?**
A: Its OAuth client was created before clients were bound to a team, so it has no team role. Create a new client with a Team in **OAuth Clients** and switch CI to it. See [OAuth clients (M2M)](#oauth-clients-m2m).

**Q: A cloud run that was in progress during the upgrade failed with 403 — why?**
A: It started before the worker execution token existed. Re-run it. Drain running executions before future upgrades of this kind.

**Q: A Viewer/Executor can still edit one use case — is that a bug?**
A: Probably not. The user who created a use case keeps edit (not delete) access to it even below Editor, as long as they remain in the owning team. See [Creator-retains-edit](#creator-retains-edit).
