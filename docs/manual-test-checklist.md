# Manual Test Checklist — User Permissions Feature

## User Management
- [ ] Admin creates a user without team → user sees "Forbidden" on login (known gap: should show landing page)
- [ ] Admin creates a user with team + role → user can log in and see team's apps
- [ ] Admin edits user role (e.g., admin → team_lead) → permissions change on next login
- [ ] Admin edits user team assignment → user sees new team's apps

## Team Management
- [ ] Admin creates a team → team appears in Teams list, Cognito groups created
- [ ] Admin deletes a team → team removed (verify apps are orphaned)
- [ ] Team Lead adds an existing user as member → member appears, can access team's apps
- [ ] Team Lead removes a member → member loses access
- [ ] Team Lead changes member role → permissions update on next login
- [ ] Team Lead cannot assign Admin role (option not available)

## Application Access Control
- [ ] Admin assigns app to team → team members can see it, others cannot
- [ ] Admin reassigns app to different team → old team loses access, new team gains it
- [ ] Team Lead creates app → auto-assigned to their team
- [ ] Non-admin user cannot see apps owned by other teams in Dashboard or Applications
- [ ] Unassigned app (no owner_team_id) → only admins can see it

## Role-Based UI
- [ ] Admin sees: Use Cases, Test Suites, Teams, Users in sidebar
- [ ] Team Lead sees: Dashboard, Applications, Templates, My Team (no Use Cases/Test Suites)
- [ ] Editor/Executor/Viewer sees: Dashboard, Applications, Templates
- [ ] Unassigned user sees: Dashboard (Forbidden), Applications (empty), Templates

## Use Case / Test Suite Boundaries
- [ ] Use cases inside a team's app are visible to team members
- [ ] Creating a use case from within an app → associated with that app
- [ ] **Known gap:** "Add Use Cases to Application" shows all use cases system-wide (needs scoping)

## Shared Access
- [ ] Admin/Team Lead grants shared access to another team → target team can see the app
- [ ] Revoking shared access → target team loses visibility
- [ ] Ceiling rule: Viewer accessing a "Full" shared app → still view-only

## Edge Cases
- [ ] Last admin cannot be removed/demoted (409 error)
- [ ] Duplicate team member add → 400 "already a member"
- [ ] Non-existent user email in Add Member → 404
- [ ] Unassigned user → "Forbidden" on dashboard (known: should show landing page instead)

## MFA / Security (not yet implemented)
- [ ] New user receives email with temp password → must change on first login
- [ ] **Needed:** Email verification / MFA code on first login (Cognito User Pool config change)

---

## Known Issues (fix or document as follow-up)

1. **Unassigned user landing page** — sees "Forbidden" instead of friendly "No Team Access" page. The `UnassignedLanding` component exists but the routing doesn't redirect unassigned users there.
2. **Add Use Cases shows all use cases** — `GET /usecases` is an unscoped flat listing. Needs team filtering.
3. **MFA not enforced** — Cognito User Pool needs MFA configuration enabled.
