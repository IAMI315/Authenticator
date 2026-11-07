export type ModuleName = "otp" | "passwords" | "servers";
export type SortDirection = "ascending" | "descending";

export interface NavigationItem {
  id: string;
  label: string;
  count: number;
  kind: "main" | "groups" | "providers";
  icon: string;
  brandKey?: string | null;
  officialUrl?: string | null;
  iconUrl?: string | null;
}

export interface DashboardStat {
  value: string;
  label: string;
  detail: string;
  tone: "blue" | "green" | "orange" | "purple";
}

export interface RecordRow {
  id: string;
  title: string;
  account: string;
  code?: string;
  remaining?: number | null;
  period?: number | null;
  type?: string;
  createdAt: string;
  username?: string;
  password?: string;
  url?: string;
  favorite: boolean;
  pinned: boolean;
  invalid?: boolean;
  highlighted?: boolean;
}

export interface Group {
  id: string;
  name: string;
  count: number;
  system?: boolean;
}

export interface SortState {
  field: string;
  direction: SortDirection;
}

export interface Snapshot {
  ready: boolean;
  locked: boolean;
  busy: boolean;
  module: ModuleName;
  security: string;
  status: string;
  summary: string;
  showPinned: boolean;
  onTop: boolean;
  compactAvailable: boolean;
  navigation: NavigationItem[];
  groups: Group[];
  stats: DashboardStat[];
  rows: RecordRow[];
  sort: SortState;
  apiEndpoint: string;
  autolockMinutes: number;
  otpCodesVisible: boolean;
  passwordsVisible: boolean;
  compactClipboard?: string;
  servers?: ServerProfile[];
  terminalTabs?: ServerTerminalTab[];
}

export interface ServerProfile {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  authKind: "password" | "private_key";
  credentialsConfigured: boolean;
  notes: string;
  trustedFingerprint: string;
  trustedAlgorithm: string;
  createdAt: string;
  updatedAt: string;
}

export interface ServerTerminalTab {
  id: string;
  name: string;
  profileId: string;
  status: string;
}

export interface DynamicRecordRow {
  id: string;
  code?: string;
  remaining?: number | null;
  invalid?: boolean;
  highlighted?: boolean;
}

export interface DynamicSnapshot {
  locked: boolean;
  busy: boolean;
  onTop: boolean;
  status: string;
  structureChanged: boolean;
  rows: DynamicRecordRow[];
}

export interface QueryState {
  module: ModuleName;
  query: string;
  scope: string;
  sort: SortState;
  showPinned: boolean;
}
