import {
  CommandSender,
  formatReport,
  resolveTargets,
  runMigration,
} from '../migrate-team-admin-role';

type Item = Record<string, any>;

const WRITE_COMMANDS = new Set([
  'AdminAddUserToGroupCommand',
  'CreateGroupCommand',
  'DeleteGroupCommand',
  'UpdateItemCommand',
  'DeleteItemCommand',
  'PutItemCommand',
]);

function awsError(name: string): Error {
  const error = new Error(name);
  error.name = name;
  return error;
}

/** In-memory Cognito user pool that answers the commands the migration sends. */
class FakeCognito implements CommandSender {
  calls: Array<{ name: string; input: any }> = [];
  groups = new Map<string, Set<string>>();
  users = new Map<string, { sub: string; email?: string }>();
  clients: Array<{ ClientId: string; ClientName: string; AllowedOAuthScopes?: string[] }> = [];
  groupPageSize = 100;

  addUser(username: string, email?: string) {
    this.users.set(username, { sub: username, email });
  }

  addToGroup(group: string, username: string) {
    if (!this.groups.has(group)) this.groups.set(group, new Set());
    this.groups.get(group)!.add(username);
  }

  async send(command: any): Promise<any> {
    const name = command.constructor.name;
    const input = command.input;
    this.calls.push({ name, input });
    switch (name) {
      case 'ListGroupsCommand': {
        const all = [...this.groups.keys()].sort();
        const start = input.NextToken ? Number(input.NextToken) : 0;
        const end = start + this.groupPageSize;
        return {
          Groups: all.slice(start, end).map((GroupName) => ({ GroupName })),
          NextToken: end < all.length ? String(end) : undefined,
        };
      }
      case 'ListUsersInGroupCommand': {
        const members = this.groups.get(input.GroupName);
        if (!members) throw awsError('ResourceNotFoundException');
        return {
          Users: [...members].map((username) => {
            const u = this.users.get(username);
            const Attributes = [{ Name: 'sub', Value: u?.sub ?? username }];
            if (u?.email) Attributes.push({ Name: 'email', Value: u.email });
            return { Username: username, Attributes };
          }),
        };
      }
      case 'CreateGroupCommand':
        if (this.groups.has(input.GroupName)) throw awsError('GroupExistsException');
        this.groups.set(input.GroupName, new Set());
        return {};
      case 'AdminAddUserToGroupCommand':
        if (!this.groups.has(input.GroupName)) throw awsError('ResourceNotFoundException');
        this.groups.get(input.GroupName)!.add(input.Username);
        return {};
      case 'DeleteGroupCommand':
        if (!this.groups.delete(input.GroupName)) throw awsError('ResourceNotFoundException');
        return {};
      case 'ListUserPoolClientsCommand':
        return { UserPoolClients: this.clients.map(({ ClientId, ClientName }) => ({ ClientId, ClientName })) };
      case 'DescribeUserPoolClientCommand':
        return { UserPoolClient: this.clients.find((c) => c.ClientId === input.ClientId) };
      default:
        throw new Error(`FakeCognito: unexpected ${name}`);
    }
  }

  writes() {
    return this.calls.filter((c) => WRITE_COMMANDS.has(c.name));
  }
}

/** In-memory single-table DynamoDB supporting the narrow query shapes the migration uses. */
class FakeDynamo implements CommandSender {
  calls: Array<{ name: string; input: any }> = [];
  items = new Map<string, Item>();
  /** Role to swap in just before an UpdateItem runs (simulates a concurrent change). */
  raceRole?: string;

  put(item: Record<string, string>) {
    const av: Item = {};
    for (const [k, v] of Object.entries(item)) av[k] = { S: v };
    this.items.set(`${item.pk}|${item.sk}`, av);
  }

  get(pk: string, sk: string): Item | undefined {
    return this.items.get(`${pk}|${sk}`);
  }

  async send(command: any): Promise<any> {
    const name = command.constructor.name;
    const input = command.input;
    this.calls.push({ name, input });
    const values = input.ExpressionAttributeValues ?? {};
    switch (name) {
      case 'QueryCommand': {
        let items = [...this.items.values()].filter((i) => i.pk.S === values[':pk'].S);
        if (values[':prefix']) items = items.filter((i) => i.sk.S.startsWith(values[':prefix'].S));
        if (input.FilterExpression === '#r = :admin') items = items.filter((i) => i.role?.S === 'admin');
        if (input.FilterExpression === 'attribute_not_exists(team_id)') items = items.filter((i) => !i.team_id);
        return { Items: items };
      }
      case 'UpdateItemCommand': {
        const item = this.get(input.Key.pk.S, input.Key.sk.S);
        if (item && this.raceRole) item.role = { S: this.raceRole };
        if (!item || item.role?.S !== values[':admin'].S) throw awsError('ConditionalCheckFailedException');
        item.role = values[':lead'];
        return {};
      }
      case 'GetItemCommand':
        return { Item: this.get(input.Key.pk.S, input.Key.sk.S) };
      case 'DeleteItemCommand': {
        const key = `${input.Key.pk.S}|${input.Key.sk.S}`;
        const old = this.items.get(key);
        this.items.delete(key);
        return { Attributes: old };
      }
      default:
        throw new Error(`FakeDynamo: unexpected ${name}`);
    }
  }

  writes() {
    return this.calls.filter((c) => WRITE_COMMANDS.has(c.name));
  }
}

const POOL = 'us-east-1_pool';
const TABLE = 'studio-data';

/**
 * team-a: lead-1 holds a legacy admin membership (and the -admin group);
 *         ed-1 is an editor who is (wrongly) in the -admin group too.
 * team-b: no legacy admins; its -admin group is empty.
 * team-gone: orphan -admin group whose team record no longer exists.
 */
function seed() {
  const cognito = new FakeCognito();
  const dynamo = new FakeDynamo();

  dynamo.put({ pk: 'TEAMS', sk: 'TEAM#team-a', id: 'team-a' });
  dynamo.put({ pk: 'TEAMS', sk: 'TEAM#team-b', id: 'team-b' });
  dynamo.put({ pk: 'TEAM#team-a', sk: 'MEMBER#lead-1', role: 'admin', user_sub: 'lead-1' });
  dynamo.put({ pk: 'TEAM#team-a', sk: 'MEMBER#ed-1', role: 'editor', user_sub: 'ed-1' });
  dynamo.put({ pk: 'TEAM#team-b', sk: 'MEMBER#view-1', role: 'viewer', user_sub: 'view-1' });
  dynamo.put({ pk: 'ADMIN_COUNT', sk: 'GLOBAL', count: '3' });
  dynamo.put({ pk: 'OAUTH_CLIENTS', sk: 'c-bound', client_id: 'c-bound', client_name: 'ci', team_id: 'team-a' });
  dynamo.put({ pk: 'OAUTH_CLIENTS', sk: 'c-unbound', client_id: 'c-unbound', client_name: 'old-ci', created_by: 'sub-x' });

  for (const [user, email] of [
    ['lead-1', 'lead@example.com'],
    ['ed-1', 'ed@example.com'],
    ['root', 'root@example.com'],
  ]) {
    cognito.addUser(user, email);
  }
  cognito.addToGroup('admins', 'root');
  cognito.addToGroup('team-team-a-admin', 'lead-1');
  cognito.addToGroup('team-team-a-admin', 'ed-1');
  cognito.addToGroup('team-team-a-editor', 'ed-1');
  cognito.groups.set('team-team-a-team_lead', new Set());
  cognito.groups.set('team-team-b-admin', new Set());
  cognito.groups.set('team-team-gone-admin', new Set());
  cognito.clients = [
    { ClientId: 'c-admin', ClientName: 'escalated', AllowedOAuthScopes: ['api/admin'] },
    { ClientId: 'c-tm', ClientName: 'teams', AllowedOAuthScopes: ['api/teams.manage', 'api/usecases.read'] },
    { ClientId: 'c-plain', ClientName: 'plain', AllowedOAuthScopes: ['api/usecases.execute'] },
  ];
  return { cognito, dynamo };
}

function run(cognito: FakeCognito, dynamo: FakeDynamo, apply: boolean) {
  return runMigration({ cognito, dynamo, userPoolId: POOL, tableName: TABLE, apply });
}

describe('runMigration (dry run)', () => {
  it('writes nothing and reports what it would change', async () => {
    const { cognito, dynamo } = seed();

    const report = await run(cognito, dynamo, false);

    expect(cognito.writes()).toEqual([]);
    expect(dynamo.writes()).toEqual([]);
    expect(report.demoted).toEqual([{ teamId: 'team-a', userSub: 'lead-1', email: 'lead@example.com' }]);
    expect(report.removedWithoutPromotion).toEqual([{ teamId: 'team-a', userSub: 'ed-1', email: 'ed@example.com' }]);
    expect(report.deletedGroups.sort()).toEqual(['team-team-a-admin', 'team-team-b-admin', 'team-team-gone-admin']);
    expect(report.adminCounterPresent).toBe(true);
    expect(dynamo.get('TEAM#team-a', 'MEMBER#lead-1')!.role.S).toBe('admin');
    expect(cognito.groups.has('team-team-a-admin')).toBe(true);
  });
});

describe('runMigration (--apply)', () => {
  it('demotes admin memberships to team_lead in DynamoDB and Cognito', async () => {
    const { cognito, dynamo } = seed();

    await run(cognito, dynamo, true);

    expect(dynamo.get('TEAM#team-a', 'MEMBER#lead-1')!.role.S).toBe('team_lead');
    expect(cognito.groups.get('team-team-a-team_lead')!.has('lead-1')).toBe(true);
  });

  it('adds the team_lead group before updating the membership record', async () => {
    const { cognito, dynamo } = seed();
    const order: string[] = [];
    const cognitoSend = cognito.send.bind(cognito);
    const dynamoSend = dynamo.send.bind(dynamo);
    cognito.send = async (c: any) => {
      order.push(c.constructor.name);
      return cognitoSend(c);
    };
    dynamo.send = async (c: any) => {
      order.push(c.constructor.name);
      return dynamoSend(c);
    };

    await run(cognito, dynamo, true);

    expect(order.indexOf('AdminAddUserToGroupCommand')).toBeLessThan(order.indexOf('UpdateItemCommand'));
  });

  it('deletes every team-*-admin group, including orphans', async () => {
    const { cognito, dynamo } = seed();

    await run(cognito, dynamo, true);

    const remaining = [...cognito.groups.keys()].filter((g) => g.endsWith('-admin'));
    expect(remaining).toEqual([]);
    expect(cognito.groups.has('admins')).toBe(true);
  });

  it('does not promote a -admin group member whose membership is not admin', async () => {
    const { cognito, dynamo } = seed();

    const report = await run(cognito, dynamo, true);

    expect(dynamo.get('TEAM#team-a', 'MEMBER#ed-1')!.role.S).toBe('editor');
    expect(cognito.groups.get('team-team-a-team_lead')!.has('ed-1')).toBe(false);
    expect(report.removedWithoutPromotion.map((u) => u.userSub)).toEqual(['ed-1']);
  });

  it('creates the team_lead group when it is missing', async () => {
    const { cognito, dynamo } = seed();
    cognito.groups.delete('team-team-a-team_lead');

    await run(cognito, dynamo, true);

    expect(cognito.groups.get('team-team-a-team_lead')!.has('lead-1')).toBe(true);
  });

  it('deletes the ADMIN_COUNT/GLOBAL record', async () => {
    const { cognito, dynamo } = seed();

    const report = await run(cognito, dynamo, true);

    expect(report.adminCounterPresent).toBe(true);
    expect(dynamo.get('ADMIN_COUNT', 'GLOBAL')).toBeUndefined();
  });

  it('never upserts: the membership update is conditional on an existing admin record', async () => {
    const { cognito, dynamo } = seed();

    await run(cognito, dynamo, true);

    const update = dynamo.calls.find((c) => c.name === 'UpdateItemCommand')!;
    expect(update.input.ConditionExpression).toBe('attribute_exists(pk) AND #r = :admin');
    expect(update.input.Key).toEqual({ pk: { S: 'TEAM#team-a' }, sk: { S: 'MEMBER#lead-1' } });
  });

  it('skips a membership whose role changed concurrently', async () => {
    const { cognito, dynamo } = seed();
    dynamo.raceRole = 'viewer';

    const report = await run(cognito, dynamo, true);

    expect(report.demoted).toEqual([]);
    expect(dynamo.get('TEAM#team-a', 'MEMBER#lead-1')!.role.S).toBe('viewer');
  });

  it('is idempotent: a second run changes nothing', async () => {
    const { cognito, dynamo } = seed();
    await run(cognito, dynamo, true);
    cognito.calls = [];
    dynamo.calls = [];

    const report = await run(cognito, dynamo, true);

    expect(report.demoted).toEqual([]);
    expect(report.removedWithoutPromotion).toEqual([]);
    expect(report.deletedGroups).toEqual([]);
    expect(report.adminCounterPresent).toBe(false);
    expect(cognito.writes()).toEqual([]);
    // Only the idempotent counter delete is sent again.
    expect(dynamo.writes().map((c) => c.name)).toEqual(['DeleteItemCommand']);
  });

  it('propagates unexpected errors so the deploy fails loudly', async () => {
    const { cognito, dynamo } = seed();
    const send = cognito.send.bind(cognito);
    cognito.send = async (c: any) => {
      if (c.constructor.name === 'DeleteGroupCommand') throw awsError('AccessDeniedException');
      return send(c);
    };

    await expect(run(cognito, dynamo, true)).rejects.toThrow('AccessDeniedException');
  });
});

describe('runMigration report', () => {
  it('lists studio admins, privileged OAuth clients and unbound OAuth clients', async () => {
    const { cognito, dynamo } = seed();

    const report = await run(cognito, dynamo, false);

    expect(report.studioAdmins).toEqual([{ username: 'root', email: 'root@example.com' }]);
    expect(report.privilegedClients).toEqual([
      { clientId: 'c-admin', clientName: 'escalated', scopes: ['api/admin'] },
      { clientId: 'c-tm', clientName: 'teams', scopes: ['api/teams.manage'] },
    ]);
    expect(report.unboundClients).toEqual([{ clientId: 'c-unbound', clientName: 'old-ci', createdBy: 'sub-x' }]);
  });

  it('follows ListGroups pagination', async () => {
    const { cognito, dynamo } = seed();
    cognito.groupPageSize = 1;

    const report = await run(cognito, dynamo, false);

    expect(report.deletedGroups).toContain('team-team-gone-admin');
    expect(cognito.calls.filter((c) => c.name === 'ListGroupsCommand').length).toBeGreaterThan(1);
  });

  it('formats a dry-run report', async () => {
    const { cognito, dynamo } = seed();

    const text = formatReport(await run(cognito, dynamo, false));

    expect(text).toContain('DRY RUN');
    expect(text).toContain('Memberships (dry run) would be demoted admin -> team_lead: 1');
    expect(text).toContain('lead@example.com [lead-1]');
    expect(text).toContain('OAuth clients without a team (unbound): 1');
  });

  it('formats an applied report', async () => {
    const { cognito, dynamo } = seed();

    const text = formatReport(await run(cognito, dynamo, true));

    expect(text).toContain('(applied)');
    expect(text).toContain('Memberships demoted admin -> team_lead: 1');
    expect(text).toContain('ADMIN_COUNT/GLOBAL record deleted');
  });
});

describe('resolveTargets', () => {
  function fakeCfn(outputs: Record<string, Record<string, string>>): CommandSender & { calls: string[] } {
    const calls: string[] = [];
    return {
      calls,
      async send(command: any) {
        const stack = command.input.StackName;
        calls.push(stack);
        const out = outputs[stack] ?? {};
        return {
          Stacks: [{ Outputs: Object.entries(out).map(([OutputKey, OutputValue]) => ({ OutputKey, OutputValue })) }],
        };
      },
    };
  }

  it('reads the user pool and table from the auth and storage stack outputs', async () => {
    const cfn = fakeCfn({
      'studio-auth': { UserPoolIdOutput: POOL },
      'studio-storage': { dynamodbTable: TABLE },
    });

    await expect(resolveTargets(cfn, 'studio')).resolves.toEqual({ userPoolId: POOL, tableName: TABLE });
    expect(cfn.calls).toEqual(['studio-auth', 'studio-storage']);
  });

  it('fails when an output is missing', async () => {
    const cfn = fakeCfn({ 'studio-auth': { UserPoolIdOutput: POOL } });

    await expect(resolveTargets(cfn, 'studio')).rejects.toThrow('dynamodbTable');
  });
});
