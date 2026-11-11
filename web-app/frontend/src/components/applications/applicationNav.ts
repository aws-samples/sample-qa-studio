import type { SideNavigationProps } from '@cloudscape-design/components/side-navigation';

/**
 * The per-application configuration pages (Variables / Secrets / Datasets).
 * One list drives the side navigation group (App.tsx), the Configuration
 * dropdown on the application detail page and the page breadcrumbs.
 */
export type ApplicationConfigSlug = 'variables' | 'secrets' | 'datasets';

export const APPLICATION_CONFIG_PAGES: ReadonlyArray<{ slug: ApplicationConfigSlug; text: string }> = [
  { slug: 'variables', text: 'Variables' },
  { slug: 'secrets', text: 'Secrets' },
  { slug: 'datasets', text: 'Datasets' },
];

export function applicationConfigHref(applicationId: string, slug: ApplicationConfigSlug): string {
  return `/applications/${applicationId}/${slug}`;
}

const APPLICATION_ROUTE = /^\/applications\/([^/]+)(?:\/.*)?$/;

/** Application id when `pathname` is `/applications/:id` or one of its sub-routes, else null. */
export function matchApplicationRoute(pathname: string): string | null {
  const match = APPLICATION_ROUTE.exec(pathname);
  return match ? match[1] : null;
}

/**
 * The *Applications* side-navigation entry: always the group link; the
 * Variables / Secrets / Datasets children only while an application route is open.
 */
export function applicationNavGroup(pathname: string): SideNavigationProps.ExpandableLinkGroup {
  const applicationId = matchApplicationRoute(pathname);
  return {
    type: 'expandable-link-group',
    text: 'Applications',
    href: '/applications',
    defaultExpanded: true,
    items: applicationId
      ? APPLICATION_CONFIG_PAGES.map((page) => ({
        type: 'link',
        text: page.text,
        href: applicationConfigHref(applicationId, page.slug),
      }))
      : [],
  };
}
