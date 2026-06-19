/**
 * Domain plugin registry.
 *
 * When no domain is loaded, all registries are empty.
 * When a domain stash is loaded (e.g. airops), `forge load` regenerates
 * this file to import and register domain-specific cards, block parsers,
 * tool messages, and dashboard config.
 */

import type { ComponentType } from 'react';

// biome-ignore lint/suspicious/noExplicitAny: domain cards have varied props
export type DomainCardRenderer = ComponentType<any>;

export interface DashboardTableConfig {
  name: string;
  color: string;
}

export interface DashboardConfig {
  tables: DashboardTableConfig[];
}

/** Map of response block type -> React component */
export const domainCardRenderers: Record<string, DomainCardRenderer> = {};

/** Map of tool name -> loading message */
export const domainToolMessages: Record<string, string> = {};

/** Dashboard table configuration */
export const domainDashboardConfig: DashboardConfig | null = null;

/** Allowed tables for API */
export const domainAllowedTables: string[] = [];
