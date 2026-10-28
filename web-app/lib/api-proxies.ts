/**
 * Top-level API resources whose nested paths are served by a `{proxy+}` child.
 *
 * API Gateway allows only one variable path part per parent. Older stacks had
 * explicit children such as `/applications/{id}`; CloudFormation creates the
 * new `{proxy+}` before deleting them, which fails ("A sibling ({id}) of this
 * resource already has a variable path part"). `scripts/deploy-api.ts` first
 * deploys with the `apiDeferredProxies` context set to the affected names,
 * which omits those proxies (deleting the old children), then deploys normally.
 */
export const PROXY_RESOURCES = ['applications', 'teams'] as const;

export type ProxyResource = typeof PROXY_RESOURCES[number];

export const API_DEFERRED_PROXIES_CONTEXT_KEY = 'apiDeferredProxies';

/** Parse the comma-separated context value; unknown names are rejected. */
export function parseDeferredProxies(value?: string): Set<ProxyResource> {
  if (value === undefined || value.trim() === '') {
    return new Set();
  }
  const names = value.split(',').map(n => n.trim()).filter(Boolean);
  const unknown = names.filter(n => !(PROXY_RESOURCES as readonly string[]).includes(n));
  if (unknown.length > 0) {
    throw new Error(`${API_DEFERRED_PROXIES_CONTEXT_KEY} contains unknown resource(s): ${unknown.join(', ')}`);
  }
  return new Set(names as ProxyResource[]);
}

interface TemplateResource {
  Type: string;
  Properties?: { PathPart?: string; ParentId?: unknown };
}

/**
 * Return the proxy resources whose deployed parent still has a non-proxy
 * variable child (e.g. `/applications/{id}`), i.e. the ones that must be
 * deferred for one deploy.
 */
export function findConflictingProxies(resources: Record<string, TemplateResource>): ProxyResource[] {
  const apiResources = Object.entries(resources).filter(([, r]) => r.Type === 'AWS::ApiGateway::Resource');
  const parentRef = (r: TemplateResource): string | undefined => {
    const p = r.Properties?.ParentId as { Ref?: string } | undefined;
    return p && typeof p === 'object' ? p.Ref : undefined;
  };
  const isTopLevel = (r: TemplateResource) => {
    const ref = parentRef(r);
    return ref === undefined || resources[ref]?.Type !== 'AWS::ApiGateway::Resource';
  };
  const conflicts: ProxyResource[] = [];
  for (const name of PROXY_RESOURCES) {
    const parent = apiResources.find(([, r]) => r.Properties?.PathPart === name && isTopLevel(r));
    if (!parent) continue;
    const [parentId] = parent;
    const hasOldVariableChild = apiResources.some(([, r]) => {
      const part = r.Properties?.PathPart ?? '';
      return parentRef(r) === parentId && part.startsWith('{') && part !== '{proxy+}';
    });
    if (hasOldVariableChild) conflicts.push(name);
  }
  return conflicts;
}
