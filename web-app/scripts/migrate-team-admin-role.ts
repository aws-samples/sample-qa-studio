#!/usr/bin/env ts-node
/**
 * Migrate the legacy team-scoped admin role (security finding C-1).
 *
 * Older releases created a `team-{teamId}-admin` Cognito group per team and let
 * Team Leads assign it. That group granted studio-wide admin. Admin is now only
 * the global `admins` group, so this script:
 *
 *   1. demotes every team membership with role `admin` to `team_lead`
 *      (DynamoDB `TEAM#{id}/MEMBER#{sub}` record + `team-{id}-team_lead` group),
 *   2. deletes every `team-{id}-admin` group (which also drops its members),
 *   3. deletes the obsolete `ADMIN_COUNT/GLOBAL` counter record,
 *   4. prints a report for incident review: affected users, current `admins`
 *      members, OAuth clients holding `api/admin` or `api/teams.manage`, and
 *      OAuth clients without a `team_id` (unbound).
 *
 * DynamoDB is the system of record: a user who is in a `-admin` group but whose
 * membership record isn't `admin` loses the group and is NOT promoted; they are
 * listed under "removed without promotion".
 *
 * Idempotent. Dry run by default; pass `--apply` to write.
 *
 *   npm run migrate:team-admin             # dry run
 *   npm run migrate:team-admin -- --apply  # write changes
 *
 * The user pool and table are resolved from the deployed `{baseName}-auth` and
 * `{baseName}-storage` stack outputs (baseName and region from configuration.json,
 * region overridable with AWS_REGION / AWS_DEFAULT_REGION).
 */
import { CloudFormationClient, DescribeStacksCommand } from '@aws-sdk/client-cloudformation';
import {
  AdminAddUserToGroupCommand,
  CognitoIdentityProviderClient,
  CreateGroupCommand,
  DeleteGroupCommand,
  DescribeUserPoolClientCommand,
  ListGroupsCommand,
  ListUserPoolClientsCommand,
  ListUsersInGroupCommand,
} from '@aws-sdk/client-cognito-identity-provider';
import {
  AttributeValue,
  DeleteItemCommand,
  DynamoDBClient,
  GetItemCommand,
  QueryCommand,
  UpdateItemCommand,
} from '@aws-sdk/client-dynamodb';
import { loadConfig } from '../lib/config';

/** Minimal client surface used here, so tests can pass a fake `send`. */
export interface CommandSender {
  send(command: any): Promise<any>;
}

export interface MigrationOptions {
  cognito: CommandSender;
  dynamo: CommandSender;
  userPoolId: string;
  tableName: string;
  apply: boolean;
}

export interface UserRef {
  teamId: string;
  userSub: string;
  email?: string;
}

export interface ClientRef {
  clientId: string;
  clientName?: string;
  scopes?: string[];
  createdBy?: string;
}

export interface MigrationReport {
  apply: boolean;
  /** Memberships demoted from admin to team_lead (or that would be, in dry run). */
  demoted: UserRef[];
  /** Users in a team-{id}-admin group without an admin membership record. */
  removedWithoutPromotion: UserRef[];
  /** team-{id}-admin groups deleted (or that would be). */
  deletedGroups: string[];
  adminCounterPresent: boolean;
  studioAdmins: Array<{ username: string; email?: string }>;
  privilegedClients: ClientRef[];
  unboundClients: ClientRef[];
}

export const ADMINS_GROUP = 'admins';
export const PRIVILEGED_SCOPES = ['api/admin', 'api/teams.manage'];
const LEGACY_ADMIN_GROUP_RE = /^team-(.+)-admin$/;
const ADMIN_COUNTER_KEY = { pk: { S: 'ADMIN_COUNT' }, sk: { S: 'GLOBAL' } };

function isNamed(error: unknown, name: string): boolean {
  return (error as { name?: string } | undefined)?.name === name;
}

/** Collect every page of a paginated call. `next` returns the token for the next page. */
async function paginate<T>(
  fetchPage: (token: string | undefined) => Promise<{ items: T[]; next?: string }>,
): Promise<T[]> {
  const all: T[] = [];
  let token: string | undefined;
  do {
    const page = await fetchPage(token);
    all.push(...page.items);
    token = page.next;
  } while (token);
  return all;
}

async function queryAll(
  dynamo: CommandSender,
  input: Record<string, unknown>,
): Promise<Array<Record<string, AttributeValue>>> {
  let startKey: Record<string, AttributeValue> | undefined;
  const items: Array<Record<string, AttributeValue>> = [];
  do {
    const res = await dynamo.send(new QueryCommand({ ...input, ExclusiveStartKey: startKey } as any));
    items.push(...(res.Items ?? []));
    startKey = res.LastEvaluatedKey;
  } while (startKey);
  return items;
}

async function listTeamIds(dynamo: CommandSender, tableName: string): Promise<string[]> {
  const items = await queryAll(dynamo, {
    TableName: tableName,
    KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
    ExpressionAttributeValues: { ':pk': { S: 'TEAMS' }, ':prefix': { S: 'TEAM#' } },
    ProjectionExpression: 'sk',
  });
  return items.map((i) => (i.sk?.S ?? '').slice('TEAM#'.length)).filter(Boolean);
}

async function listLegacyAdminGroupTeamIds(cognito: CommandSender, userPoolId: string): Promise<string[]> {
  const groups = await paginate<{ GroupName?: string }>(async (token) => {
    const res = await cognito.send(new ListGroupsCommand({ UserPoolId: userPoolId, NextToken: token }));
    return { items: res.Groups ?? [], next: res.NextToken };
  });
  return groups
    .map((g) => LEGACY_ADMIN_GROUP_RE.exec(g.GroupName ?? '')?.[1])
    .filter((id): id is string => Boolean(id));
}

/** Members of a group, or null if the group doesn't exist. */
async function listGroupUsers(
  cognito: CommandSender,
  userPoolId: string,
  groupName: string,
): Promise<Array<{ username: string; sub: string; email?: string }> | null> {
  try {
    const users = await paginate<any>(async (token) => {
      const res = await cognito.send(
        new ListUsersInGroupCommand({ UserPoolId: userPoolId, GroupName: groupName, NextToken: token }),
      );
      return { items: res.Users ?? [], next: res.NextToken };
    });
    return users.map((u) => {
      const attrs: Record<string, string> = {};
      for (const a of u.Attributes ?? []) attrs[a.Name] = a.Value;
      return { username: u.Username ?? '', sub: attrs.sub ?? u.Username ?? '', email: attrs.email };
    });
  } catch (error) {
    if (isNamed(error, 'ResourceNotFoundException')) return null;
    throw error;
  }
}

async function listAdminMemberships(dynamo: CommandSender, tableName: string, teamId: string): Promise<string[]> {
  const items = await queryAll(dynamo, {
    TableName: tableName,
    KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
    FilterExpression: '#r = :admin',
    ExpressionAttributeNames: { '#r': 'role' },
    ExpressionAttributeValues: {
      ':pk': { S: `TEAM#${teamId}` },
      ':prefix': { S: 'MEMBER#' },
      ':admin': { S: 'admin' },
    },
    ProjectionExpression: 'sk',
  });
  return items.map((i) => (i.sk?.S ?? '').slice('MEMBER#'.length)).filter(Boolean);
}

async function ensureGroup(cognito: CommandSender, userPoolId: string, groupName: string, teamId: string) {
  try {
    await cognito.send(
      new CreateGroupCommand({
        UserPoolId: userPoolId,
        GroupName: groupName,
        Description: `Team ${teamId} - team_lead role`,
      }),
    );
  } catch (error) {
    if (!isNamed(error, 'GroupExistsException')) throw error;
  }
}

/** Demote one membership. Returns false if the record is no longer `admin`. */
async function demoteMembership(opts: MigrationOptions, teamId: string, userSub: string): Promise<boolean> {
  const { cognito, dynamo, userPoolId, tableName } = opts;
  const teamLeadGroup = `team-${teamId}-team_lead`;
  // Add the new group first so the user never loses team-lead access mid-change.
  await ensureGroup(cognito, userPoolId, teamLeadGroup, teamId);
  await cognito.send(
    new AdminAddUserToGroupCommand({ UserPoolId: userPoolId, Username: userSub, GroupName: teamLeadGroup }),
  );
  try {
    await dynamo.send(
      new UpdateItemCommand({
        TableName: tableName,
        Key: { pk: { S: `TEAM#${teamId}` }, sk: { S: `MEMBER#${userSub}` } },
        UpdateExpression: 'SET #r = :lead',
        // Never upsert, and never overwrite a role changed since the query.
        ConditionExpression: 'attribute_exists(pk) AND #r = :admin',
        ExpressionAttributeNames: { '#r': 'role' },
        ExpressionAttributeValues: { ':lead': { S: 'team_lead' }, ':admin': { S: 'admin' } },
      }),
    );
    return true;
  } catch (error) {
    if (isNamed(error, 'ConditionalCheckFailedException')) return false;
    throw error;
  }
}

async function deleteGroup(cognito: CommandSender, userPoolId: string, groupName: string): Promise<void> {
  try {
    await cognito.send(new DeleteGroupCommand({ UserPoolId: userPoolId, GroupName: groupName }));
  } catch (error) {
    if (!isNamed(error, 'ResourceNotFoundException')) throw error;
  }
}

async function migrateTeam(opts: MigrationOptions, teamId: string, report: MigrationReport): Promise<void> {
  const { cognito, dynamo, userPoolId, tableName, apply } = opts;
  const legacyGroup = `team-${teamId}-admin`;
  const groupUsers = await listGroupUsers(cognito, userPoolId, legacyGroup);
  const emailBySub = new Map((groupUsers ?? []).map((u) => [u.sub, u.email]));

  const adminSubs = await listAdminMemberships(dynamo, tableName, teamId);
  for (const userSub of adminSubs) {
    if (!apply || (await demoteMembership(opts, teamId, userSub))) {
      report.demoted.push({ teamId, userSub, email: emailBySub.get(userSub) });
    }
  }

  if (groupUsers === null) return;
  const demotedSubs = new Set(adminSubs);
  for (const u of groupUsers) {
    if (!demotedSubs.has(u.sub)) {
      report.removedWithoutPromotion.push({ teamId, userSub: u.sub, email: u.email });
    }
  }
  if (apply) await deleteGroup(cognito, userPoolId, legacyGroup);
  report.deletedGroups.push(legacyGroup);
}

async function handleAdminCounter(opts: MigrationOptions): Promise<boolean> {
  const { dynamo, tableName, apply } = opts;
  if (apply) {
    const res = await dynamo.send(
      new DeleteItemCommand({ TableName: tableName, Key: ADMIN_COUNTER_KEY, ReturnValues: 'ALL_OLD' }),
    );
    return Boolean(res.Attributes);
  }
  const res = await dynamo.send(new GetItemCommand({ TableName: tableName, Key: ADMIN_COUNTER_KEY }));
  return Boolean(res.Item);
}

async function listPrivilegedClients(cognito: CommandSender, userPoolId: string): Promise<ClientRef[]> {
  const clients = await paginate<{ ClientId?: string; ClientName?: string }>(async (token) => {
    const res = await cognito.send(
      new ListUserPoolClientsCommand({ UserPoolId: userPoolId, MaxResults: 60, NextToken: token }),
    );
    return { items: res.UserPoolClients ?? [], next: res.NextToken };
  });
  const privileged: ClientRef[] = [];
  for (const c of clients) {
    const res = await cognito.send(new DescribeUserPoolClientCommand({ UserPoolId: userPoolId, ClientId: c.ClientId }));
    const scopes: string[] = res.UserPoolClient?.AllowedOAuthScopes ?? [];
    const held = scopes.filter((s) => PRIVILEGED_SCOPES.includes(s));
    if (held.length > 0) {
      privileged.push({ clientId: c.ClientId ?? '', clientName: c.ClientName, scopes: held });
    }
  }
  return privileged;
}

async function listUnboundClients(dynamo: CommandSender, tableName: string): Promise<ClientRef[]> {
  const items = await queryAll(dynamo, {
    TableName: tableName,
    KeyConditionExpression: 'pk = :pk',
    FilterExpression: 'attribute_not_exists(team_id)',
    ExpressionAttributeValues: { ':pk': { S: 'OAUTH_CLIENTS' } },
  });
  return items.map((i) => ({
    clientId: i.client_id?.S ?? i.sk?.S ?? '',
    clientName: i.client_name?.S,
    createdBy: i.created_by?.S,
  }));
}

export async function runMigration(opts: MigrationOptions): Promise<MigrationReport> {
  const { cognito, dynamo, userPoolId, tableName, apply } = opts;
  const report: MigrationReport = {
    apply,
    demoted: [],
    removedWithoutPromotion: [],
    deletedGroups: [],
    adminCounterPresent: false,
    studioAdmins: [],
    privilegedClients: [],
    unboundClients: [],
  };

  const teamIds = new Set([
    ...(await listTeamIds(dynamo, tableName)),
    ...(await listLegacyAdminGroupTeamIds(cognito, userPoolId)),
  ]);
  for (const teamId of [...teamIds].sort()) {
    await migrateTeam(opts, teamId, report);
  }

  report.adminCounterPresent = await handleAdminCounter(opts);
  report.studioAdmins = ((await listGroupUsers(cognito, userPoolId, ADMINS_GROUP)) ?? []).map((u) => ({
    username: u.username,
    email: u.email,
  }));
  report.privilegedClients = await listPrivilegedClients(cognito, userPoolId);
  report.unboundClients = await listUnboundClients(dynamo, tableName);
  return report;
}

export function formatReport(report: MigrationReport): string {
  const verb = report.apply ? '' : '(dry run) would be ';
  const user = (u: UserRef) => `  - team ${u.teamId}: ${u.email ?? '(no email)'} [${u.userSub}]`;
  const lines = [
    `Team admin role migration ${report.apply ? '(applied)' : '(DRY RUN, pass --apply to write)'}`,
    '',
    `Memberships ${verb}demoted admin -> team_lead: ${report.demoted.length}`,
    ...report.demoted.map(user),
    `Users ${verb}removed from a team-*-admin group without promotion: ${report.removedWithoutPromotion.length}`,
    ...report.removedWithoutPromotion.map(user),
    `Legacy groups ${verb}deleted: ${report.deletedGroups.length}`,
    ...report.deletedGroups.map((g) => `  - ${g}`),
    `ADMIN_COUNT/GLOBAL record ${report.adminCounterPresent ? `${verb}deleted` : 'not present'}`,
    '',
    'For incident review:',
    `Members of the '${ADMINS_GROUP}' group (studio admins): ${report.studioAdmins.length}`,
    ...report.studioAdmins.map((a) => `  - ${a.email ?? '(no email)'} [${a.username}]`),
    `OAuth clients holding ${PRIVILEGED_SCOPES.join(' or ')}: ${report.privilegedClients.length}`,
    ...report.privilegedClients.map((c) => `  - ${c.clientName ?? '(no name)'} [${c.clientId}]: ${c.scopes?.join(', ')}`),
    `OAuth clients without a team (unbound): ${report.unboundClients.length}`,
    ...report.unboundClients.map(
      (c) => `  - ${c.clientName ?? '(no name)'} [${c.clientId}] created by ${c.createdBy ?? 'unknown'}`,
    ),
  ];
  return lines.join('\n');
}

async function getStackOutput(cfn: CommandSender, stackName: string, outputKey: string): Promise<string> {
  const res = await cfn.send(new DescribeStacksCommand({ StackName: stackName }));
  const value = res.Stacks?.[0]?.Outputs?.find((o: any) => o.OutputKey === outputKey)?.OutputValue;
  if (!value) {
    throw new Error(`Output ${outputKey} not found on stack ${stackName}. Is it deployed?`);
  }
  return value;
}

/** Resolve the user pool and table of the deployed studio from stack outputs. */
export async function resolveTargets(cfn: CommandSender, baseName: string) {
  return {
    userPoolId: await getStackOutput(cfn, `${baseName}-auth`, 'UserPoolIdOutput'),
    // StorageStack emits the table name as the `dynamodbTable` output (BaseStack.log).
    tableName: await getStackOutput(cfn, `${baseName}-storage`, 'dynamodbTable'),
  };
}

async function main(): Promise<void> {
  const config = loadConfig();
  const region = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || config.defaultRegion;
  const apply = process.argv.includes('--apply');
  const { userPoolId, tableName } = await resolveTargets(new CloudFormationClient({ region }), config.baseName);
  const report = await runMigration({
    cognito: new CognitoIdentityProviderClient({ region }),
    dynamo: new DynamoDBClient({ region }),
    userPoolId,
    tableName,
    apply,
  });
  console.log(formatReport(report));
}

if (require.main === module) {
  main().catch((error) => {
    console.error('❌ Team admin role migration failed:', error);
    process.exit(1);
  });
}
