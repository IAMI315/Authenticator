import {
  AddRounded,
  ArrowDownwardRounded,
  ArrowUpwardRounded,
  ChevronLeftRounded,
  ChevronRightRounded,
  ContentCopyRounded,
  DeleteOutlineRounded,
  DownloadRounded,
  EditOutlined,
  ExpandMoreRounded,
  FolderOutlined,
  HelpOutlineRounded,
  KeyRounded,
  LaunchRounded,
  LockOutlined,
  LockOpenRounded,
  MoreHorizRounded,
  MoreVertRounded,
  PasswordRounded,
  PhonelinkLockRounded,
  PinDropRounded,
  PushPinRounded,
  QrCodeScannerRounded,
  SearchRounded,
  SettingsOutlined,
  ShieldRounded,
  StarBorderRounded,
  StarRounded,
  UploadRounded,
  VisibilityOffOutlined,
  VisibilityOutlined,
} from "@mui/icons-material";
import {
  Alert,
  AppBar,
  Avatar,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  CssBaseline,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControl,
  IconButton,
  InputAdornment,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  ThemeProvider,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
  createTheme,
  useMediaQuery,
} from "@mui/material";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type UIEvent } from "react";
import { dynamicSnapshot, invoke, snapshot } from "./bridge";
import type { DynamicRecordRow, Group, ModuleName, NavigationItem, QueryState, RecordRow, Snapshot, SortState } from "./types";
import { nextSort, selectAllRows, toggleRowSelection, virtualRowRange } from "./uiModel";
import { useWorkspaceModule } from "./useWorkspaceModule";
import { AppIcon } from "./AppIcon";

const NAV_WIDTH = 218;
const TABLE_ROW_HEIGHT = 64;
const TABLE_OVERSCAN = 8;
const ServerWorkspace = lazy(() => import("./ServerWorkspace").then((module) => ({ default: module.ServerWorkspace })));
const EMPTY_SNAPSHOT: Snapshot = {
  ready: false,
  locked: false,
  busy: false,
  module: "otp",
  security: "正在读取本地保险库...",
  status: "正在准备界面...",
  summary: "",
  showPinned: true,
  onTop: false,
  compactAvailable: true,
  navigation: [],
  groups: [],
  stats: [],
  rows: [],
  sort: { field: "created", direction: "descending" },
  apiEndpoint: "",
  autolockMinutes: 0,
  otpCodesVisible: true,
  passwordsVisible: true,
};

const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#2684F2" },
    secondary: { main: "#0E9A73" },
    background: { default: "#EEF5FA", paper: "rgba(255,255,255,0.80)" },
    text: { primary: "#17233A", secondary: "#64748B" },
    divider: "rgba(145, 163, 184, 0.24)",
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '"Microsoft YaHei UI", "Segoe UI", sans-serif',
    button: { textTransform: "none", fontWeight: 700, letterSpacing: 0 },
  },
  components: {
    MuiButton: { styleOverrides: { root: { minHeight: 36, borderRadius: 9, boxShadow: "none" } } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
    MuiDialog: { styleOverrides: { paper: { background: "rgba(250,253,255,0.98)", boxShadow: "0 24px 80px rgba(46, 75, 105, 0.22)" } } },
    MuiTableCell: { styleOverrides: { root: { borderColor: "rgba(148,163,184,0.18)" }, head: { color: "#64748B", fontWeight: 800 } } },
  },
});

type DialogKind = "record" | "groups" | "settings" | "unlock" | "password" | "help" | "confirm" | null;

interface RecordForm {
  id?: string;
  issuer: string;
  account: string;
  secret: string;
  otpType: string;
  counter: string;
  period: string;
  digits: string;
  algorithm: string;
  name: string;
  username: string;
  password: string;
  url: string;
  notes: string;
  favorite: boolean;
  pinned: boolean;
  groupIds: string[];
}

const emptyForm = (module: ModuleName, groups: Group[]): RecordForm => ({
  issuer: "",
  account: "",
  secret: "",
  otpType: "totp",
  counter: "0",
  period: "30",
  digits: "6",
  algorithm: "SHA1",
  name: "",
  username: "",
  password: "",
  url: "",
  notes: "",
  favorite: false,
  pinned: false,
  groupIds: groups.filter((group) => group.system).map((group) => group.id),
});

function navIcon(item: NavigationItem) {
  if (item.iconUrl) {
    return <Avatar variant="rounded" src={item.iconUrl} alt="" sx={{ width: 21, height: 21, bgcolor: "transparent", color: "#2563EB", fontSize: 11, fontWeight: 800 }}>
      {item.label.trim().slice(0, 1).toUpperCase() || "?"}
    </Avatar>;
  }
  if (item.icon === "star") return <StarRounded fontSize="small" />;
  if (item.icon === "folder") return <FolderOutlined fontSize="small" />;
  if (item.icon === "grid") return <MoreHorizRounded fontSize="small" />;
  if (item.kind === "providers") return <Avatar variant="rounded" sx={{ width: 21, height: 21, bgcolor: "#E8F1FF", color: "#2563EB", fontSize: 11, fontWeight: 800 }}>{item.label.trim().slice(0, 1).toUpperCase() || "?"}</Avatar>;
  return <ShieldRounded fontSize="small" />;
}

function statTone(tone: string) {
  return {
    blue: ["#EFF6FF", "#2563EB"],
    green: ["#EFFAF4", "#15803D"],
    orange: ["#FFF7ED", "#EA580C"],
    purple: ["#F6F3FF", "#6D4DF2"],
  }[tone] ?? ["#F4F7FA", "#475569"];
}

function formatRemaining(row: RecordRow) {
  if (row.remaining === null || row.remaining === undefined) return "-";
  return `${row.remaining}s`;
}

const compactPage = new URLSearchParams(window.location.search).get("mode") === "compact";

function usePageActivity(): boolean {
  const [active, setActive] = useState(() => (window as Window & { __authenticatorPageActive?: boolean }).__authenticatorPageActive !== false);

  useEffect(() => {
    const onActivity = (event: Event) => {
      const detail = (event as CustomEvent<{ active?: boolean }>).detail;
      setActive(detail?.active !== false);
    };
    window.addEventListener("authenticator-page-activity", onActivity);
    return () => window.removeEventListener("authenticator-page-activity", onActivity);
  }, []);

  return active;
}

export default function App() {
  return compactPage ? <CompactApp /> : <FullApp />;
}

function FullApp() {
  const pageActive = usePageActivity();
  const { module, ready: moduleReady, select: selectModule, error: moduleError } = useWorkspaceModule(pageActive);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [scope, setScope] = useState("all");
  const [sort, setSort] = useState<SortState>({ field: "created", direction: "descending" });
  const [showPinned, setShowPinned] = useState(true);
  const [data, setData] = useState<Snapshot>(EMPTY_SNAPSHOT);
  const [dynamicRows, setDynamicRows] = useState<Record<string, DynamicRecordRow>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [recordForm, setRecordForm] = useState<RecordForm | null>(null);
  const [revealId, setRevealId] = useState<string | null>(null);
  const [revealedPassword, setRevealedPassword] = useState("");
  const [visiblePasswords, setVisiblePasswords] = useState<Record<string, string>>({});
  const [hiddenPasswordIds, setHiddenPasswordIds] = useState<string[]>([]);
  const [otpVisibilityOverrides, setOtpVisibilityOverrides] = useState<string[]>([]);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [moreAnchor, setMoreAnchor] = useState<HTMLElement | null>(null);
  const [exportAnchor, setExportAnchor] = useState<HTMLElement | null>(null);
  const [confirmAction, setConfirmAction] = useState<"delete" | null>(null);
  const [sideNavExpanded, setSideNavExpanded] = useState(false);
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const tableScrollFrame = useRef<number | null>(null);
  const pendingTableScrollTop = useRef(0);
  const [tableScrollTop, setTableScrollTop] = useState(0);
  const [tableViewportHeight, setTableViewportHeight] = useState(0);
  const narrowNavigation = useMediaQuery("(max-width:1119px)");

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 180);
    return () => window.clearTimeout(timer);
  }, [query]);

  const state: QueryState = useMemo(() => ({ module, query: debouncedQuery, scope, sort, showPinned }), [module, debouncedQuery, scope, sort, showPinned]);
  const refresh = useCallback(async () => {
    try {
      const next = await snapshot({ ...state });
      setData(next);
      setDynamicRows({});
      setVisiblePasswords({});
      setError("");
      if (next.locked) {
        setSelected([]);
        setRevealId(null);
        setRevealedPassword("");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法连接本地界面服务");
    }
  }, [state]);

  useEffect(() => {
    if (!moduleReady) return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => window.clearInterval(timer);
  }, [moduleReady, refresh]);

  const refreshDynamic = useCallback(async () => {
    try {
      const next = await dynamicSnapshot({
        ...state,
        rowIds: data.rows.map((row) => row.id),
      });
      if (next.structureChanged) {
        void refresh();
        return;
      }
      setDynamicRows(Object.fromEntries(next.rows.map((row) => [row.id, row])));
      setData((current) => (
        current.locked === next.locked && current.busy === next.busy && current.onTop === next.onTop && current.status === next.status
          ? current
          : { ...current, locked: next.locked, busy: next.busy, onTop: next.onTop, status: next.status }
      ));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法连接本地界面服务");
    }
  }, [data.rows, module, refresh, state]);

  useEffect(() => {
    // Password records have no time-dependent fields. Polling them was
    // rebuilding a large password table once per second for no gain.
    if (!moduleReady || module !== "otp" || data.module !== module) return;
    void refreshDynamic();
    const timer = window.setInterval(() => void refreshDynamic(), 1_000);
    return () => window.clearInterval(timer);
  }, [module, moduleReady, data.module, refreshDynamic]);

  useEffect(() => {
    setScope("all");
    setQuery("");
    setDebouncedQuery("");
    setSort({ field: "created", direction: "descending" });
  }, [module]);

  useEffect(() => {
    setSelected([]);
    setRevealId(null);
    setRevealedPassword("");
    setVisiblePasswords({});
    setHiddenPasswordIds([]);
    setOtpVisibilityOverrides([]);
  }, [module, scope]);

  useEffect(() => {
    setVisiblePasswords({});
    setHiddenPasswordIds([]);
    setRevealId(null);
    setRevealedPassword("");
    setOtpVisibilityOverrides([]);
  }, [data.otpCodesVisible, data.passwordsVisible]);

  useEffect(() => {
    if (pageActive) return;
    setVisiblePasswords({});
    setRevealId(null);
    setRevealedPassword("");
  }, [pageActive]);

  useEffect(() => {
    if (!narrowNavigation) setSideNavExpanded(false);
  }, [narrowNavigation]);

  useEffect(() => {
    const container = tableContainerRef.current;
    if (!container || module === "servers") return undefined;
    const updateViewport = () => setTableViewportHeight(container.clientHeight);
    updateViewport();
    const observer = new ResizeObserver(updateViewport);
    observer.observe(container);
    return () => observer.disconnect();
  }, [module]);

  useEffect(() => () => {
    if (tableScrollFrame.current !== null) window.cancelAnimationFrame(tableScrollFrame.current);
  }, []);

  useEffect(() => {
    const container = tableContainerRef.current;
    if (container) container.scrollTop = 0;
    pendingTableScrollTop.current = 0;
    setTableScrollTop(0);
  }, [module, scope, sort, showPinned, debouncedQuery]);

  const run = async (action: string, payload: Record<string, unknown> = {}, success?: string) => {
    try {
      if (action === "lock" || action === "delete" || action === "save_record") {
        setVisiblePasswords({});
        setRevealId(null);
        setRevealedPassword("");
      }
      const result = await invoke<{ message?: string }>(action, payload);
      if (success || result?.message) setToast(success ?? result.message ?? "操作完成");
      await refresh();
      return result;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "操作失败");
      return undefined;
    }
  };

  const switchToCompact = async () => {
    try {
      await invoke("compact", { module });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法切换到轻量模式");
    }
  };

  const changeModule = async (next: ModuleName) => {
    if (next === module) return;
    if (!await selectModule(next)) return;
    setQuery("");
    setDebouncedQuery("");
    setScope("all");
    setSort({ field: "created", direction: "descending" });
    setRevealId(null);
    setRevealedPassword("");
  };

  const changeSort = (field: string) => setSort((current) => nextSort(current, field));

  const toggleSelected = (id: string, additive = true) => setSelected((current) => toggleRowSelection(current, id, additive));

  const selectAll = () => setSelected((current) => selectAllRows(current, data.rows.map((row) => row.id)));
  const oneSelected = selected.length === 1;
  const activeRow = data.rows.find((row) => row.id === selected[0]);
  const displayRows = useMemo(
    () => data.rows.map((row) => ({ ...row, ...dynamicRows[row.id] })),
    [data.rows, dynamicRows],
  );
  const virtualRange = useMemo(
    () => virtualRowRange(displayRows.length, tableScrollTop, tableViewportHeight, TABLE_ROW_HEIGHT, TABLE_OVERSCAN),
    [displayRows.length, tableScrollTop, tableViewportHeight],
  );
  const renderedRows = useMemo(
    () => displayRows.slice(virtualRange.start, virtualRange.end),
    [displayRows, virtualRange],
  );
  const visiblePasswordIds = useMemo(
    () => renderedRows.filter((row) => !hiddenPasswordIds.includes(row.id)).map((row) => row.id),
    [renderedRows, hiddenPasswordIds],
  );
  useEffect(() => {
    setVisiblePasswords({});
    if (!pageActive || module !== "passwords" || data.locked || !data.passwordsVisible || !visiblePasswordIds.length) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void invoke<{ passwords: Record<string, string> }>("visible_passwords", { ids: visiblePasswordIds })
        .then((result) => { if (!cancelled) setVisiblePasswords(result.passwords); })
        .catch((caught) => { if (!cancelled) setError(caught instanceof Error ? caught.message : "无法读取密码"); });
    }, 40);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [pageActive, module, data.locked, data.passwordsVisible, visiblePasswordIds, data.rows]);
  const handleTableScroll = useCallback((event: UIEvent<HTMLDivElement>) => {
    pendingTableScrollTop.current = event.currentTarget.scrollTop;
    if (tableScrollFrame.current !== null) return;
    tableScrollFrame.current = window.requestAnimationFrame(() => {
      tableScrollFrame.current = null;
      setTableScrollTop((current) => current === pendingTableScrollTop.current ? current : pendingTableScrollTop.current);
    });
  }, []);
  const navigationOpen = !narrowNavigation || sideNavExpanded;
  const navigationWidth = navigationOpen ? NAV_WIDTH : 58;

  const createRecord = () => {
    if (module === "servers") return;
    setRecordForm(emptyForm(module, data.groups));
    setDialog("record");
  };

  const editRecord = async (id = selected[0]) => {
    if (!id) return;
    try {
      const form = await invoke<RecordForm>("record_details", { module, id });
      setRecordForm(form);
      setDialog("record");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法读取记录");
    }
  };

  const saveRecord = async () => {
    if (!recordForm) return;
    const result = await run("save_record", { module, record: recordForm }, recordForm.id ? "记录已更新" : "记录已新增");
    if (result) setDialog(null);
  };

  const revealPassword = async (id: string) => {
    if (data.passwordsVisible) {
      setHiddenPasswordIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
      return;
    }
    if (revealId === id) {
      setRevealId(null);
      setRevealedPassword("");
      return;
    }
    try {
      const result = await invoke<{ password: string }>("reveal_password", { id });
      setRevealId(id);
      setRevealedPassword(result.password);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法显示密码");
    }
  };

  const copy = (kind: "account" | "code" | "username" | "password", id = selected[0]) => {
    if (id) void run(`copy_${kind}`, { id }, kind === "account" ? "账号已复制" : kind === "code" ? "验证码已复制" : kind === "username" ? "用户名已复制" : "密码已复制");
  };

  const openGroups = () => setDialog("groups");
  const isOtp = module === "otp";
  const columns = isOtp
    ? [["service", "服务"], ["account", "账号"], ["code", "验证码"], ["remaining", "剩余"], ["type", "类型"], ["created", "创建时间"]]
    : [["name", "名称/服务"], ["username", "用户名"], ["password", "密码"], ["url", "网址"], ["created", "创建时间"]];

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ height: "100%", display: "flex", flexDirection: "column", background: "radial-gradient(circle at 10% -10%, #dceeff 0, transparent 34%), #eef5fa" }}>
        <AppBar position="static" elevation={0} color="transparent" sx={{ color: "text.primary", borderBottom: "1px solid rgba(148,163,184,.22)", background: "rgba(255,255,255,.74)", backdropFilter: "blur(18px)" }}>
          <Box sx={{ minHeight: 72, px: 2.5, display: "flex", alignItems: "center", gap: 1.25 }}>
            <AppIcon size={40} />
            <Box sx={{ minWidth: 150 }}><Typography variant="h6" sx={{ fontWeight: 800 }}>验证器桌面版</Typography><Typography variant="caption" color="text.secondary">{data.security}</Typography></Box>
            <Box sx={{ flex: 1 }} />
            <Tooltip title={module === "servers" ? "请使用服务器栏的新增按钮" : "新增"}><span><Button variant="contained" startIcon={<AddRounded />} onClick={createRecord} disabled={data.locked || data.busy || module === "servers"}>新增</Button></span></Tooltip>
            <Tooltip title="导入备份或 otpauth URI"><IconButton onClick={() => void run("import")} disabled={data.locked || data.busy}><UploadRounded /></IconButton></Tooltip>
            <Tooltip title="导出"><IconButton onClick={(event) => setExportAnchor(event.currentTarget)} disabled={data.locked || data.busy}><DownloadRounded /></IconButton></Tooltip>
            <Tooltip title={module === "servers" ? "服务器模块不提供轻量模式" : "轻量模式"}><span><IconButton aria-label="轻量模式" onClick={() => void switchToCompact()} disabled={!moduleReady || data.locked || data.busy || module === "servers"}><PhonelinkLockRounded /></IconButton></span></Tooltip>
            <Tooltip title="窗口置顶"><IconButton color={data.onTop ? "primary" : "default"} onClick={() => void run("toggle_topmost")}><PushPinRounded /></IconButton></Tooltip>
            <Tooltip title={data.locked ? "解锁保险库" : "锁定保险库"}><IconButton color={data.locked ? "error" : "default"} onClick={() => setDialog(data.locked ? "unlock" : "confirm")}><>{data.locked ? <LockOutlined /> : <LockOpenRounded />}</></IconButton></Tooltip>
            <IconButton onClick={(event) => setMoreAnchor(event.currentTarget)}><MoreHorizRounded /></IconButton>
            <ToggleButtonGroup exclusive value={module} onChange={(_event, value: ModuleName | null) => value && void changeModule(value)} size="small" sx={{ ml: 1, bgcolor: "#f1f5f9", borderRadius: 2, p: .25, "& .MuiToggleButton-root": { border: 0, px: 2.2, borderRadius: 1.5 } }}>
              <ToggleButton value="otp" sx={{ "&.Mui-selected": { bgcolor: "#d9f5e4 !important", color: "#08784a" } }}>验证码</ToggleButton>
              <ToggleButton value="passwords" sx={{ "&.Mui-selected": { bgcolor: "#dff3ff !important", color: "#087bb9" } }}>密码本</ToggleButton>
              <ToggleButton value="servers" sx={{ "&.Mui-selected": { bgcolor: "#dff8f5 !important", color: "#087a78" } }}>服务器</ToggleButton>
            </ToggleButtonGroup>
          </Box>
        </AppBar>

        {module === "servers" ? <Suspense fallback={<Box sx={{ flex: 1, display: "grid", placeItems: "center" }}><CircularProgress size={28} /></Box>}><ServerWorkspace snapshot={data} refresh={refresh} /></Suspense> : <Box sx={{ flex: 1, minHeight: 0, display: "flex", p: 1.5, gap: 1.5, position: "relative" }}>
          <Drawer variant="permanent" sx={{ width: navigationWidth, flexShrink: 0, position: narrowNavigation && navigationOpen ? "absolute" : "relative", left: 0, top: 0, bottom: 0, zIndex: narrowNavigation && navigationOpen ? 20 : "auto", "& .MuiDrawer-paper": { width: navigationWidth, position: narrowNavigation && navigationOpen ? "absolute" : "relative", height: "100%", border: "1px solid rgba(148,163,184,.22)", borderRadius: 2.5, bgcolor: "rgba(255,255,255,.60)", backdropFilter: "blur(18px)", overflow: "hidden", transition: "width 160ms ease" } }}>
            <Box sx={{ p: navigationOpen ? 1.2 : .5, display: "flex", gap: .45, alignItems: "center" }}>{navigationOpen && <TextField size="small" value={query} onChange={(event) => setQuery(event.target.value)} fullWidth placeholder="搜索分组或账号" slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchRounded fontSize="small" /></InputAdornment> } }} />}{narrowNavigation && <Tooltip title={navigationOpen ? "收起导航" : "展开导航"}><IconButton size="small" onClick={() => setSideNavExpanded((open) => !open)}>{navigationOpen ? <ChevronLeftRounded /> : <ChevronRightRounded />}</IconButton></Tooltip>}</Box>
            <List dense sx={{ px: .8, py: 0, overflowY: "auto", flex: 1 }}>
              {data.navigation.map((item) => <ListItemButton key={item.id} selected={scope === item.id} onClick={() => { setScope(item.id); if (narrowNavigation) setSideNavExpanded(false); }} sx={{ borderRadius: 1.5, mb: .3, justifyContent: navigationOpen ? "initial" : "center", px: navigationOpen ? 1 : .5 }}>
                <ListItemIcon sx={{ minWidth: navigationOpen ? 31 : 0, color: item.id === "favorites" ? "#e69b00" : "primary.main" }}><Tooltip title={item.officialUrl ? `${item.label} · ${item.officialUrl}` : item.label}>{navIcon(item)}</Tooltip></ListItemIcon>
                {navigationOpen && <><ListItemText primary={<Typography noWrap sx={{ fontSize: 13, fontWeight: scope === item.id ? 800 : 500 }}>{item.label}</Typography>} /><Chip label={item.count} size="small" sx={{ height: 21, minWidth: 25, bgcolor: "rgba(226,232,240,.74)", fontWeight: 700 }} /></>}
              </ListItemButton>)}
            </List>
            <Box sx={{ m: navigationOpen ? 1 : .5, px: navigationOpen ? 1.2 : .75, py: 1, borderRadius: 2, border: "1px solid rgba(61,128,226,.18)", bgcolor: "rgba(238,246,255,.72)" }}><Stack direction="row" spacing={.8} sx={{ alignItems: "center", justifyContent: navigationOpen ? "initial" : "center" }}><ShieldRounded color="primary" fontSize="small" />{navigationOpen && <Typography variant="caption" sx={{ fontWeight: 700 }}>{data.locked ? "保险库已锁定" : "本地数据已加密"}</Typography>}</Stack></Box>
          </Drawer>

          <Box sx={{ minWidth: 0, flex: 1, display: "flex", flexDirection: "column", gap: 1.4 }}>
            <Box sx={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 1.2 }}>
              {data.stats.map((stat) => {
                const [background, accent] = statTone(stat.tone);
                return <Paper key={stat.label} variant="outlined" sx={{ px: 1.6, py: 1.25, minWidth: 0, borderColor: `${accent}38`, bgcolor: background, display: "flex", gap: 1, alignItems: "center" }}><Box sx={{ width: 35, height: 35, borderRadius: "50%", bgcolor: "rgba(255,255,255,.76)", color: accent, display: "grid", placeItems: "center" }}><KeyRounded fontSize="small" /></Box><Box sx={{ minWidth: 0 }}><Typography sx={{ fontWeight: 800, fontSize: 21, lineHeight: 1.1 }}>{stat.value}</Typography><Typography noWrap sx={{ fontSize: 12, fontWeight: 700 }}>{stat.label}</Typography><Typography variant="caption" color="text.secondary" noWrap>{stat.detail}</Typography></Box></Paper>;
              })}
            </Box>

            <Paper variant="outlined" sx={{ minHeight: 0, flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", borderColor: "rgba(148,163,184,.22)", bgcolor: "rgba(255,255,255,.76)", backdropFilter: "blur(20px)" }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.8, py: 1.1, borderBottom: "1px solid rgba(148,163,184,.17)" }}>
                <Typography sx={{ fontWeight: 800 }}>{isOtp ? "账号列表" : "密码列表"}</Typography><Typography variant="caption" color="text.secondary">{data.summary}</Typography><Box sx={{ flex: 1 }} />
                <TextField size="small" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={isOtp ? "搜索账号" : "搜索密码记录"} sx={{ width: 245 }} slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchRounded fontSize="small" /></InputAdornment> } }} />
                <Tooltip title="显示或隐藏置顶记录"><Button size="small" variant={showPinned ? "contained" : "outlined"} startIcon={<PushPinRounded />} onClick={() => { const next = !showPinned; setShowPinned(next); void run("set_show_pinned", { module, value: next }); }}>置顶可见</Button></Tooltip>
                <Button size="small" startIcon={<FolderOutlined />} onClick={openGroups}>分组</Button>
              </Box>
              <TableContainer ref={tableContainerRef} onScroll={handleTableScroll} sx={{ flex: 1, overflowY: "auto" }}><Table stickyHeader size="small" aria-label={isOtp ? "验证码账号列表" : "密码记录列表"} sx={{ tableLayout: "fixed" }}>
                <TableHead><TableRow>
                  <TableCell padding="checkbox"><Checkbox size="small" checked={data.rows.length > 0 && selected.length === data.rows.length} indeterminate={selected.length > 0 && selected.length < data.rows.length} onChange={selectAll} /></TableCell>
                  <TableCell sx={{ width: 38 }} />
                  {columns.map(([field, label]) => <TableCell key={field} onClick={() => field !== "code" && field !== "remaining" && field !== "password" && changeSort(field)} sx={{ cursor: ["code", "remaining", "password"].includes(field) ? "default" : "pointer", whiteSpace: "nowrap" }}>{label}{sort.field === field && (sort.direction === "ascending" ? <ArrowUpwardRounded sx={{ fontSize: 14, verticalAlign: "middle", ml: .3 }} /> : <ArrowDownwardRounded sx={{ fontSize: 14, verticalAlign: "middle", ml: .3 }} />)}</TableCell>)}
                  <TableCell align="right">操作</TableCell>
                </TableRow></TableHead>
              <TableBody>{virtualRange.start > 0 && <TableRow aria-hidden="true"><TableCell colSpan={columns.length + 3} sx={{ p: 0, border: 0, height: virtualRange.start * TABLE_ROW_HEIGHT, lineHeight: 0 }} /></TableRow>}{renderedRows.map((row) => <TableRow hover key={row.id} selected={selected.includes(row.id)} onClick={() => toggleSelected(row.id, false)} onDoubleClick={() => copy(isOtp ? "code" : "password", row.id)} sx={{ height: TABLE_ROW_HEIGHT, cursor: "default", "& td": { boxSizing: "border-box", height: TABLE_ROW_HEIGHT, whiteSpace: "nowrap", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis" } }}>
                  <TableCell padding="checkbox" onClick={(event) => event.stopPropagation()}><Checkbox size="small" checked={selected.includes(row.id)} onChange={() => toggleSelected(row.id)} /></TableCell>
                  <TableCell sx={{ py: .3 }} onClick={(event) => event.stopPropagation()}><Stack spacing={-.45}><Tooltip title={row.favorite ? "取消收藏" : "收藏"}><IconButton size="small" color={row.favorite ? "warning" : "default"} onClick={() => void run("set_favorite", { module, ids: [row.id], value: !row.favorite })}>{row.favorite ? <StarRounded fontSize="small" /> : <StarBorderRounded fontSize="small" />}</IconButton></Tooltip><Tooltip title={row.pinned ? "取消置顶" : "置顶"}><IconButton size="small" color={row.pinned ? "primary" : "default"} onClick={() => void run("set_pinned", { module, ids: [row.id], value: !row.pinned })}><PushPinRounded sx={{ fontSize: 16 }} /></IconButton></Tooltip></Stack></TableCell>
                  <TableCell>{row.title}</TableCell>
                  {isOtp ? <>
                    <TableCell onClick={(event) => { event.stopPropagation(); copy("account", row.id); }} sx={{ cursor: "pointer", color: "text.primary", "&:hover": { color: "primary.main", textDecoration: "underline" } }}><Tooltip title="点击复制账号"><Box component="span">{row.account}</Box></Tooltip></TableCell>
                    <TableCell onClick={(event) => { event.stopPropagation(); copy("code", row.id); }} sx={{ color: row.invalid ? "error.main" : "primary.main", fontSize: 19, fontWeight: 800, cursor: "pointer" }}>
                      <Stack direction="row" spacing={.2} sx={{ alignItems: "center" }}>
                        <Box component="span" sx={{ minWidth: 0, flex: 1, letterSpacing: 1, overflow: "hidden", textOverflow: "ellipsis" }}>{row.invalid || data.otpCodesVisible !== otpVisibilityOverrides.includes(row.id) ? row.code : "••••••"}</Box>
                        <Tooltip title={data.otpCodesVisible !== otpVisibilityOverrides.includes(row.id) ? "隐藏验证码" : "显示验证码"}><IconButton size="small" aria-label={data.otpCodesVisible !== otpVisibilityOverrides.includes(row.id) ? "隐藏验证码" : "显示验证码"} onClick={(event) => { event.stopPropagation(); setOtpVisibilityOverrides((current) => current.includes(row.id) ? current.filter((item) => item !== row.id) : [...current, row.id]); }}>{data.otpCodesVisible !== otpVisibilityOverrides.includes(row.id) ? <VisibilityOffOutlined fontSize="small" /> : <VisibilityOutlined fontSize="small" />}</IconButton></Tooltip>
                      </Stack>
                    </TableCell><TableCell><Chip label={formatRemaining(row)} size="small" color={row.remaining !== null && (row.remaining ?? 99) <= 10 ? "warning" : "default"} /></TableCell><TableCell>{row.type}</TableCell>
                  </> : <>
                    <TableCell>{row.username}</TableCell>
                    <TableCell onClick={(event) => { event.stopPropagation(); void revealPassword(row.id); }} sx={{ cursor: "pointer", color: (data.passwordsVisible ? !hiddenPasswordIds.includes(row.id) : revealId === row.id) ? "text.primary" : "text.secondary" }}>
                      <Stack direction="row" spacing={.2} sx={{ alignItems: "center" }}>
                        <Box component="span" sx={{ minWidth: 0, flex: 1, overflow: "hidden", textOverflow: "ellipsis", letterSpacing: (data.passwordsVisible ? !hiddenPasswordIds.includes(row.id) : revealId === row.id) ? 0 : 1.4 }}>{data.passwordsVisible ? (hiddenPasswordIds.includes(row.id) ? row.password : visiblePasswords[row.id] ?? row.password) : (revealId === row.id ? revealedPassword : row.password)}</Box>
                        <Tooltip title={(data.passwordsVisible ? !hiddenPasswordIds.includes(row.id) : revealId === row.id) ? "隐藏密码" : "显示密码"}><IconButton size="small" aria-label={(data.passwordsVisible ? !hiddenPasswordIds.includes(row.id) : revealId === row.id) ? "隐藏密码" : "显示密码"} onClick={(event) => { event.stopPropagation(); void revealPassword(row.id); }}>{(data.passwordsVisible ? !hiddenPasswordIds.includes(row.id) : revealId === row.id) ? <VisibilityOffOutlined fontSize="small" /> : <VisibilityOutlined fontSize="small" />}</IconButton></Tooltip>
                      </Stack>
                    </TableCell><TableCell>{row.url || "-"}</TableCell>
                  </>}
                  <TableCell>{row.createdAt}</TableCell>
                  <TableCell align="right" onClick={(event) => event.stopPropagation()}><Tooltip title="编辑"><IconButton size="small" onClick={() => void editRecord(row.id)}><EditOutlined fontSize="small" /></IconButton></Tooltip>{!isOtp && row.url && <Tooltip title="打开网站"><IconButton size="small" onClick={() => void run("open_website", { id: row.id })}><LaunchRounded fontSize="small" /></IconButton></Tooltip>}<IconButton size="small" onClick={() => toggleSelected(row.id, false)}><MoreVertRounded fontSize="small" /></IconButton></TableCell>
                </TableRow>)}{virtualRange.end < displayRows.length && <TableRow aria-hidden="true"><TableCell colSpan={columns.length + 3} sx={{ p: 0, border: 0, height: (displayRows.length - virtualRange.end) * TABLE_ROW_HEIGHT, lineHeight: 0 }} /></TableRow>}</TableBody>
              </Table></TableContainer>
              <Divider /><Box sx={{ minHeight: 54, px: 1.5, display: "flex", gap: .75, alignItems: "center" }}><Box sx={{ mr: "auto", minWidth: 0 }}>{selected.length > 0 && <Typography variant="caption" color="text.secondary">已选择 {selected.length} 项</Typography>}</Box>
                {isOtp ? <Button size="small" startIcon={<ContentCopyRounded />} disabled={!oneSelected} onClick={() => copy("code")}>复制验证码</Button> : <><Button size="small" startIcon={<ContentCopyRounded />} disabled={!oneSelected} onClick={() => copy("username")}>复制用户名</Button><Button size="small" variant="contained" startIcon={<ContentCopyRounded />} disabled={!oneSelected} onClick={() => copy("password")}>复制密码</Button><Button size="small" startIcon={(data.passwordsVisible ? !hiddenPasswordIds.includes(selected[0]) : revealId === selected[0]) ? <VisibilityOffOutlined /> : <VisibilityOutlined />} disabled={!oneSelected} onClick={() => activeRow && void revealPassword(activeRow.id)}>{(data.passwordsVisible ? !hiddenPasswordIds.includes(selected[0]) : revealId === selected[0]) ? "隐藏" : "显示"}</Button></>}
                <Button size="small" startIcon={<FolderOutlined />} disabled={!selected.length} onClick={openGroups}>分组</Button><Button size="small" startIcon={<StarRounded />} disabled={!selected.length} onClick={() => void run("set_favorite", { module, ids: selected, value: true }, "已收藏所选记录")}>收藏</Button><Button size="small" startIcon={<PushPinRounded />} disabled={!selected.length} onClick={() => void run("set_pinned", { module, ids: selected, value: true }, "已置顶所选记录")}>置顶</Button><Button size="small" color="error" startIcon={<DeleteOutlineRounded />} disabled={!selected.length} onClick={() => { setConfirmAction("delete"); setDialog("confirm"); }}>删除</Button>
              </Box>
            </Paper>
          </Box>
        </Box>}

        <Menu anchorEl={moreAnchor} open={Boolean(moreAnchor)} onClose={() => setMoreAnchor(null)}><MenuItem onClick={() => { setMoreAnchor(null); setDialog("settings"); }}><SettingsOutlined fontSize="small" /><Box sx={{ ml: 1 }}>设置</Box></MenuItem><MenuItem onClick={() => { setMoreAnchor(null); setDialog("help"); }}><HelpOutlineRounded fontSize="small" /><Box sx={{ ml: 1 }}>本机 API 说明</Box></MenuItem></Menu>
        <Menu anchorEl={exportAnchor} open={Boolean(exportAnchor)} onClose={() => setExportAnchor(null)}><MenuItem onClick={() => { setExportAnchor(null); void run("export_encrypted"); }}>加密备份（推荐）</MenuItem><MenuItem onClick={() => { setExportAnchor(null); void run("export_plain"); }}>明文 JSON</MenuItem><MenuItem onClick={() => { setExportAnchor(null); void run("export_google"); }}>Google Authenticator 二维码</MenuItem></Menu>

        <RecordDialog open={dialog === "record"} module={module} form={recordForm} groups={data.groups} onClose={() => setDialog(null)} onChange={setRecordForm} onSave={() => void saveRecord()} onScan={() => void run("scan", {}, "请在屏幕上选择二维码区域").then(() => setDialog(null))} onGenerate={async () => { try { const result = await invoke<{ password: string }>("generate_password"); setRecordForm((current) => current ? { ...current, password: result.password } : current); } catch (caught) { setError(caught instanceof Error ? caught.message : "无法生成密码"); } }} />
        <GroupDialog open={dialog === "groups"} module={module} groups={data.groups} selected={selected} onClose={() => setDialog(null)} onRun={run} />
        <SettingsDialog open={dialog === "settings"} snapshot={data} onClose={() => setDialog(null)} onRun={run} />
        <UnlockDialog open={dialog === "unlock"} onClose={() => setDialog(null)} onUnlock={async (password) => { const result = await run("unlock", { password }, "保险库已解锁"); if (result) setDialog(null); }} />
        <InfoDialog open={dialog === "help"} title="本机 API" onClose={() => setDialog(null)}><Typography variant="body2">服务地址：{data.apiEndpoint || "未启动"}</Typography><Typography variant="body2" sx={{ mt: 1 }}>接口仅监听本机，保险库锁定时不会返回账号或密钥。访问令牌不会显示在网页中，可在设置中复制。</Typography></InfoDialog>
        <ConfirmDialog open={dialog === "confirm"} locked={data.locked} action={confirmAction} count={selected.length} onClose={() => { setDialog(null); setConfirmAction(null); }} onConfirm={() => { if (data.locked) { setDialog("unlock"); return; } if (confirmAction === "delete") void run("delete", { module, ids: selected }, "记录已删除").then(() => { setSelected([]); setDialog(null); }); else void run("lock", {}, "保险库已锁定").then(() => setDialog(null)); }} />
        <Snackbar open={Boolean(toast)} autoHideDuration={3200} onClose={() => setToast("")} message={toast} /><Snackbar open={Boolean(error || moduleError)} autoHideDuration={6000} onClose={() => setError("")}><Alert severity="error" onClose={() => setError("")}>{error || moduleError}</Alert></Snackbar>
      </Box>
    </ThemeProvider>
  );
}

function CompactApp() {
  const pageActive = usePageActivity();
  const { module, ready: moduleReady, select: selectModule, error: moduleError } = useWorkspaceModule(pageActive, true);
  const [query, setQuery] = useState("");
  const [data, setData] = useState<Snapshot>(EMPTY_SNAPSHOT);
  const [dynamicRows, setDynamicRows] = useState<Record<string, DynamicRecordRow>>({});
  const [shownCodeIds, setShownCodeIds] = useState<string[]>([]);
  const [passwordVisibilityOverrides, setPasswordVisibilityOverrides] = useState<string[]>([]);
  const [visiblePasswords, setVisiblePasswords] = useState<Record<string, string>>({});
  const [clipboard, setClipboard] = useState("");
  const [editingClipboard, setEditingClipboard] = useState(false);
  const [recordForm, setRecordForm] = useState<RecordForm | null>(null);
  const [addAnchor, setAddAnchor] = useState<HTMLElement | null>(null);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const clipboardClickTimer = useRef<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(160);
  const refreshGeneration = useRef(0);
  const isOtp = module === "otp";

  const refresh = useCallback(async () => {
    const request = ++refreshGeneration.current;
    try {
      const next = await snapshot({
        module,
        query,
        scope: "all",
        sort: { field: "created", direction: "descending" },
        showPinned: true,
        compact: true,
      });
      if (request !== refreshGeneration.current) return;
      setData(next);
      setDynamicRows({});
      if (next.locked) {
        setShownCodeIds([]);
        setVisiblePasswords({});
        setPasswordVisibilityOverrides([]);
        setRecordForm(null);
      }
      if (!editingClipboard) setClipboard(next.compactClipboard ?? "");
      setError("");
    } catch (caught) {
      if (request === refreshGeneration.current) setError(caught instanceof Error ? caught.message : "无法连接本地界面服务");
    }
  }, [module, editingClipboard, query]);

  useEffect(() => {
    if (!moduleReady) return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => { ++refreshGeneration.current; window.clearInterval(timer); };
  }, [moduleReady, refresh]);

  useEffect(() => {
    setShownCodeIds([]);
    setPasswordVisibilityOverrides([]);
    setVisiblePasswords({});
    setRecordForm(null);
    setAddAnchor(null);
    setScrollTop(0);
    if (listRef.current) listRef.current.scrollTop = 0;
  }, [module]);

  useEffect(() => {
    if (!pageActive) { setVisiblePasswords({}); setRecordForm(null); }
  }, [pageActive]);

  useEffect(() => {
    const container = listRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => setViewportHeight(container.clientHeight));
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const refreshDynamic = useCallback(async () => {
    try {
      const next = await dynamicSnapshot({
        module,
        compact: true,
        query,
        rowIds: data.rows.map((row) => row.id),
      });
      if (next.structureChanged) {
        void refresh();
        return;
      }
      setDynamicRows(Object.fromEntries(next.rows.map((row) => [row.id, row])));
      setData((current) => (
        current.locked === next.locked && current.busy === next.busy && current.onTop === next.onTop && current.status === next.status
          ? current
          : { ...current, locked: next.locked, busy: next.busy, onTop: next.onTop, status: next.status }
      ));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法连接本地界面服务");
    }
  }, [module, data.rows, query, refresh]);

  useEffect(() => {
    if (!moduleReady || !isOtp || data.module !== module) return;
    void refreshDynamic();
    const timer = window.setInterval(() => void refreshDynamic(), 1_000);
    return () => window.clearInterval(timer);
  }, [moduleReady, isOtp, data.module, module, refreshDynamic]);

  useEffect(() => () => {
    if (clipboardClickTimer.current !== null) window.clearTimeout(clipboardClickTimer.current);
  }, []);

  const run = async (action: string, payload: Record<string, unknown> = {}, success?: string) => {
    try {
      const result = await invoke<{ message?: string }>(action, payload);
      if (success || result.message) setToast(success ?? result.message ?? "操作完成");
      if (!action.startsWith("copy_")) await refresh();
      return result;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "操作失败");
      return undefined;
    }
  };

  const switchToFull = async () => {
    try {
      await invoke("return_full", { module });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法返回完整界面");
    }
  };

  const scan = async () => {
    const result = await run("scan", { compact: true }, "正在扫描屏幕中的二维码");
    if (result) setRecordForm(null);
  };

  const saveRecord = async () => {
    if (!recordForm) return;
    const result = await run("save_record", { module, record: recordForm }, isOtp ? "账号已新增" : "密码记录已新增");
    if (result) setRecordForm(null);
  };

  const copy = (kind: "account" | "code" | "username" | "password", id: string) => {
    const messages = { account: "账号已复制", code: "验证码已复制", username: "用户名已复制", password: "密码已复制" };
    void run(`copy_${kind}`, { id }, messages[kind]);
  };

  const changeModule = async (next: ModuleName) => {
    if (next === module) return;
    if (await selectModule(next)) setQuery("");
  };

  const generatePassword = async () => {
    try {
      const result = await invoke<{ password: string }>("generate_password");
      setRecordForm((current) => current ? { ...current, password: result.password } : null);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "无法生成密码"); }
  };

  const copyClipboard = () => {
    if (editingClipboard) return;
    if (clipboardClickTimer.current !== null) window.clearTimeout(clipboardClickTimer.current);
    clipboardClickTimer.current = window.setTimeout(() => {
      clipboardClickTimer.current = null;
      void run("copy_compact_clipboard", { value: clipboard }, "已复制常驻剪贴板内容");
    }, 210);
  };

  const editClipboard = () => {
    if (clipboardClickTimer.current !== null) {
      window.clearTimeout(clipboardClickTimer.current);
      clipboardClickTimer.current = null;
    }
    setEditingClipboard(true);
  };

  const saveClipboard = async () => {
    if (!editingClipboard) return;
    const result = await run("set_compact_clipboard", { value: clipboard }, "常驻剪贴板已保存");
    if (result) setEditingClipboard(false);
  };

  const displayRows = useMemo(
    () => data.module === module && !data.locked ? data.rows.map((row) => ({ ...row, ...(isOtp ? dynamicRows[row.id] : {}) })) : [],
    [data.rows, data.module, data.locked, module, isOtp, dynamicRows],
  );
  const rowStride = 78;
  const virtualRange = virtualRowRange(displayRows.length, scrollTop, viewportHeight, rowStride, 2);
  const renderedRows = useMemo(() => displayRows.slice(virtualRange.start, virtualRange.end), [displayRows, virtualRange.start, virtualRange.end]);
  const visiblePasswordIds = useMemo(() => renderedRows.filter((row) => data.passwordsVisible !== passwordVisibilityOverrides.includes(row.id)).map((row) => row.id), [renderedRows, data.passwordsVisible, passwordVisibilityOverrides]);
  useEffect(() => {
    if (!moduleReady || isOtp || data.locked || !visiblePasswordIds.length) { setVisiblePasswords({}); return; }
    let cancelled = false;
    setVisiblePasswords((current) => Object.fromEntries(Object.entries(current).filter(([id]) => visiblePasswordIds.includes(id))));
    const timer = window.setTimeout(() => {
      void invoke<{ passwords: Record<string, string> }>("visible_passwords", { ids: visiblePasswordIds })
        .then((result) => { if (!cancelled) setVisiblePasswords(result.passwords); })
        .catch((caught) => { if (!cancelled) setError(caught instanceof Error ? caught.message : "无法读取密码"); });
    }, 40);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [moduleReady, isOtp, data.locked, visiblePasswordIds, data.rows]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ height: "100%", p: .75, display: "flex", flexDirection: "column", gap: .65, overflow: "hidden", bgcolor: "#eef5fa", background: "radial-gradient(circle at 15% -20%, #d8eeff 0, transparent 38%), #eef5fa" }}>
        <Paper variant="outlined" sx={{ p: .65, flexShrink: 0, borderColor: "rgba(148,163,184,.22)", bgcolor: "rgba(255,255,255,.76)", backdropFilter: "blur(18px)" }}>
          <Stack direction="row" spacing={.65} sx={{ alignItems: "center" }}>
            <AppIcon size={27} />
            <Typography sx={{ fontWeight: 800, fontSize: 15, flex: 1 }}>验证器</Typography>
            <ToggleButtonGroup exclusive value={module} size="small" aria-label="轻量窗口模块" onChange={(_event, value: ModuleName | null) => value && void changeModule(value)} sx={{ flexShrink: 0, p: .25, bgcolor: "#edf2f7", borderRadius: 2, "& .MuiToggleButton-root": { border: 0, borderRadius: 1.5, px: .8, py: .45, minHeight: 28, fontSize: 11.5, whiteSpace: "nowrap" } }}>
              <ToggleButton value="otp" sx={{ "&.Mui-selected, &.Mui-selected:hover": { bgcolor: "#d6f4e3", color: "#137848" } }}>验证码</ToggleButton>
              <ToggleButton value="passwords" sx={{ "&.Mui-selected, &.Mui-selected:hover": { bgcolor: "#dcefff", color: "#0873af" } }}>密码本</ToggleButton>
            </ToggleButtonGroup>
            <Tooltip title="切换窗口置顶"><IconButton size="small" color={data.onTop ? "primary" : "default"} onClick={() => void run("toggle_topmost")}><PushPinRounded fontSize="small" /></IconButton></Tooltip>
            <Button size="small" variant="outlined" onClick={() => void switchToFull()}>完整界面</Button>
          </Stack>
        </Paper>
        <TextField size="small" value={query} onChange={(event) => { setQuery(event.target.value); setScrollTop(0); if (listRef.current) listRef.current.scrollTop = 0; }} placeholder={isOtp ? "搜索账号" : "搜索密码本"} fullWidth sx={{ "& .MuiInputBase-root": { height: 32 }, "& .MuiInputBase-input": { py: .45, fontSize: 13.5 } }} slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchRounded sx={{ fontSize: 19 }} /></InputAdornment> } }} />
        <Stack direction="row" spacing={.75} sx={{ flexShrink: 0 }}>
          <Button fullWidth variant="contained" startIcon={isOtp ? <QrCodeScannerRounded /> : <AddRounded />} disabled={!moduleReady || data.module !== module || data.locked || data.busy} onClick={() => isOtp ? void scan() : setRecordForm(emptyForm(module, data.groups))} sx={{ minHeight: 34, fontSize: 13 }}> {isOtp ? "扫码新增" : "新增密码"}</Button>
          {isOtp && <IconButton aria-label="新增方式" disabled={data.locked || data.busy} onClick={(event) => setAddAnchor(event.currentTarget)}><ExpandMoreRounded /></IconButton>}
        </Stack>
        <Menu anchorEl={addAnchor} open={Boolean(addAnchor)} onClose={() => setAddAnchor(null)}><MenuItem onClick={() => { setAddAnchor(null); void scan(); }}><QrCodeScannerRounded fontSize="small" /><Box sx={{ ml: 1 }}>扫码添加</Box></MenuItem><MenuItem onClick={() => { setAddAnchor(null); setRecordForm(emptyForm("otp", data.groups)); }}><AddRounded fontSize="small" /><Box sx={{ ml: 1 }}>手动添加</Box></MenuItem></Menu>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", minWidth: 0, flexShrink: 0 }}>
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 800, whiteSpace: "nowrap" }}>最近添加</Typography>
          {editingClipboard ? <TextField autoFocus size="small" value={clipboard} onChange={(event) => setClipboard(event.target.value)} onBlur={() => void saveClipboard()} onKeyDown={(event) => { if (event.key === "Enter") void saveClipboard(); if (event.key === "Escape") { setClipboard(data.compactClipboard ?? ""); setEditingClipboard(false); } }} sx={{ flex: 1, "& .MuiInputBase-root": { height: 27, bgcolor: "rgba(255,255,255,.78)" } }} /> : <Typography onClick={copyClipboard} onDoubleClick={editClipboard} title="单击复制，双击编辑" noWrap sx={{ flex: 1, minWidth: 0, cursor: "pointer", color: "text.primary", fontSize: 13, borderBottom: "1px solid rgba(148,163,184,.26)", py: .25, "&:hover": { color: "primary.main" } }}>{clipboard || "常驻剪贴板"}</Typography>}
        </Stack>
        <Box ref={listRef} onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)} sx={{ minHeight: 0, flex: 1, overflowY: "auto", pr: .2 }}>
          <Box sx={{ height: virtualRange.start * rowStride }} />
          {renderedRows.map((row) => <Paper key={row.id} variant="outlined" sx={{ p: .65, height: 72, mb: "6px", overflow: "hidden", borderColor: row.highlighted ? "#21a26b" : "rgba(148,163,184,.22)", boxShadow: row.highlighted ? "0 0 0 2px rgba(33,162,107,.16)" : "none", transition: "border-color .18s ease, box-shadow .18s ease", bgcolor: "rgba(255,255,255,.78)" }}>
            <Stack direction="row" spacing={.75} sx={{ alignItems: "center", height: 19 }}><Typography variant="body2" sx={{ fontWeight: 800, minWidth: 0, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 13 }}>{row.title}</Typography>{row.pinned && <PushPinRounded color="primary" sx={{ fontSize: 14 }} />}{isOtp && <Chip label={formatRemaining(row)} size="small" sx={{ height: 19, fontSize: 11 }} />}</Stack>
            <Typography onClick={() => copy(isOtp ? "account" : "username", row.id)} title={isOtp ? "点击复制账号" : "点击复制用户名"} noWrap sx={{ mt: .1, cursor: "pointer", color: "text.secondary", fontSize: 11.5, lineHeight: 1.25, "&:hover": { color: "primary.main", textDecoration: "underline" } }}>{isOtp ? row.account : row.username}</Typography>
            <Stack direction="row" spacing={.4} sx={{ mt: .15, alignItems: "center" }}>
              {isOtp ? <>
                <Typography onClick={() => copy("code", row.id)} title="点击复制验证码" sx={{ cursor: "pointer", color: row.invalid ? "error.main" : "primary.main", fontSize: 20, fontWeight: 800, letterSpacing: 0, lineHeight: 1 }}>{row.invalid || data.otpCodesVisible || shownCodeIds.includes(row.id) ? row.code : "••••••"}</Typography>
                {!data.otpCodesVisible && <Tooltip title={shownCodeIds.includes(row.id) ? "隐藏验证码" : "显示验证码"}><IconButton size="small" aria-label={shownCodeIds.includes(row.id) ? "隐藏验证码" : "显示验证码"} onClick={() => setShownCodeIds((current) => current.includes(row.id) ? current.filter((id) => id !== row.id) : [...current, row.id])}>{shownCodeIds.includes(row.id) ? <VisibilityOffOutlined sx={{ fontSize: 16 }} /> : <VisibilityOutlined sx={{ fontSize: 16 }} />}</IconButton></Tooltip>}
              </> : <>
                <Typography onClick={() => copy("password", row.id)} title="点击复制密码" noWrap sx={{ flex: 1, minWidth: 0, cursor: "pointer", color: "text.primary", fontSize: 16, fontWeight: 600, lineHeight: 1.2 }}>{visiblePasswords[row.id] ?? "••••••••••••"}</Typography>
                <Tooltip title={visiblePasswordIds.includes(row.id) ? "隐藏密码" : "显示密码"}><IconButton size="small" aria-label={visiblePasswordIds.includes(row.id) ? "隐藏密码" : "显示密码"} onClick={() => setPasswordVisibilityOverrides((current) => current.includes(row.id) ? current.filter((id) => id !== row.id) : [...current, row.id])}>{visiblePasswordIds.includes(row.id) ? <VisibilityOffOutlined sx={{ fontSize: 16 }} /> : <VisibilityOutlined sx={{ fontSize: 16 }} />}</IconButton></Tooltip>
              </>}
            </Stack>
          </Paper>)}
          <Box sx={{ height: (displayRows.length - virtualRange.end) * rowStride }} />
          {moduleReady && data.module === module && !displayRows.length && <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", pt: 3 }}>{data.locked ? "保险库已锁定" : query ? "没有符合搜索条件的记录" : isOtp ? "暂无账号" : "暂无密码记录"}</Typography>}
        </Box>
        <RecordDialog open={recordForm !== null} module={module} form={recordForm} groups={data.groups} onClose={() => setRecordForm(null)} onChange={setRecordForm} onSave={() => void saveRecord()} onScan={() => void scan()} onGenerate={() => void generatePassword()} />
        <Snackbar open={Boolean(toast)} autoHideDuration={2200} onClose={() => setToast("")} anchorOrigin={{ vertical: "bottom", horizontal: "center" }} message={toast} sx={{ bottom: "12px !important", "& .MuiSnackbarContent-root": { minWidth: 0, width: "fit-content", maxWidth: "calc(100vw - 52px)", px: 1.25, py: .55, borderRadius: 2, fontSize: 12.5, boxShadow: "0 8px 20px rgba(15,23,42,.22)" } }} />
        <Snackbar open={Boolean(error || moduleError)} autoHideDuration={6000} onClose={() => setError("")}><Alert severity="error" onClose={() => setError("")}>{error || moduleError}</Alert></Snackbar>
      </Box>
    </ThemeProvider>
  );
}

function RecordDialog({ open, module, form, groups, onClose, onChange, onSave, onScan, onGenerate }: { open: boolean; module: ModuleName; form: RecordForm | null; groups: Group[]; onClose: () => void; onChange: (value: RecordForm) => void; onSave: () => void; onScan: () => void; onGenerate: () => void }) {
  if (!form) return null;
  function set<K extends keyof RecordForm>(key: K, value: RecordForm[K]) {
    onChange({ ...form, [key]: value } as RecordForm);
  }
  const passwordModule = module === "passwords";
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{form.id ? "编辑" : "新增"}{passwordModule ? "密码记录" : "验证码账号"}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={1.35}>
          {passwordModule ? (
            <>
              <TextField label="名称/服务（选填）" value={form.name} onChange={(event) => set("name", event.target.value)} autoFocus />
              <TextField required label="用户名" value={form.username} onChange={(event) => set("username", event.target.value)} />
              <TextField required label="密码" type="password" value={form.password} onChange={(event) => set("password", event.target.value)} slotProps={{ input: { endAdornment: <InputAdornment position="end"><Button size="small" onClick={onGenerate}>生成</Button></InputAdornment> } }} />
              <TextField label="网址（选填）" value={form.url} onChange={(event) => set("url", event.target.value)} />
              <TextField label="备注（选填）" value={form.notes} multiline minRows={4} onChange={(event) => set("notes", event.target.value)} />
            </>
          ) : (
            <>
              <TextField label="服务商（选填）" value={form.issuer} onChange={(event) => set("issuer", event.target.value)} autoFocus />
              <TextField required label="账号" value={form.account} onChange={(event) => set("account", event.target.value)} />
              <TextField required label="密钥" value={form.secret} onChange={(event) => set("secret", event.target.value)} slotProps={{ input: { endAdornment: <InputAdornment position="end"><Tooltip title="扫码识别"><IconButton onClick={onScan}><QrCodeScannerRounded /></IconButton></Tooltip></InputAdornment> } }} />
              <FormControl fullWidth><Select value={form.otpType} onChange={(event) => set("otpType", event.target.value)}><MenuItem value="totp">基于时间（TOTP）</MenuItem><MenuItem value="hotp">基于计数器（HOTP）</MenuItem><MenuItem value="steam">Steam 令牌</MenuItem><MenuItem value="battle">Battle.net</MenuItem></Select></FormControl>
              <Stack direction="row" spacing={1}><TextField label="周期" value={form.period} onChange={(event) => set("period", event.target.value)} fullWidth disabled={form.otpType === "hotp"} /><TextField label="位数" value={form.digits} onChange={(event) => set("digits", event.target.value)} fullWidth /><TextField label="计数器" value={form.counter} onChange={(event) => set("counter", event.target.value)} fullWidth disabled={form.otpType !== "hotp"} /></Stack>
            </>
          )}
          <Divider />
          <Typography variant="subtitle2">分组</Typography>
          <Stack direction="row" spacing={.4} sx={{ flexWrap: "wrap" }}>{groups.map((group) => <Chip key={group.id} label={group.name} variant={form.groupIds.includes(group.id) ? "filled" : "outlined"} color={form.groupIds.includes(group.id) ? "primary" : "default"} onClick={() => set("groupIds", form.groupIds.includes(group.id) ? form.groupIds.filter((id) => id !== group.id) : [...form.groupIds, group.id])} />)}</Stack>
          <Stack direction="row" spacing={1}><Button variant={form.favorite ? "contained" : "outlined"} size="small" startIcon={<StarRounded />} onClick={() => set("favorite", !form.favorite)}>收藏</Button><Button variant={form.pinned ? "contained" : "outlined"} size="small" startIcon={<PushPinRounded />} onClick={() => set("pinned", !form.pinned)}>置顶</Button></Stack>
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>取消</Button><Button variant="contained" onClick={onSave}>保存</Button></DialogActions>
    </Dialog>
  );
}

function GroupDialog({ open, module, groups, selected, onClose, onRun }: { open: boolean; module: ModuleName; groups: Group[]; selected: string[]; onClose: () => void; onRun: (action: string, payload?: Record<string, unknown>, success?: string) => Promise<unknown> }) {
  const [name, setName] = useState("");
  const [assigned, setAssigned] = useState<string[]>([]);
  useEffect(() => setAssigned(groups.filter((group) => group.system).map((group) => group.id)), [groups]);
  return <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs"><DialogTitle>分组管理</DialogTitle><DialogContent dividers><Stack spacing={1.2}><Stack direction="row" spacing={1}><TextField label="新建分组" size="small" value={name} onChange={(event) => setName(event.target.value)} fullWidth /><Button variant="contained" onClick={() => { if (name.trim()) void onRun("create_group", { module, name }, "分组已创建").then(() => setName("")); }}>新建</Button></Stack>{groups.map((group) => <Stack key={group.id} direction="row" sx={{ alignItems: "center" }}><Checkbox checked={assigned.includes(group.id)} disabled={!selected.length} onChange={() => setAssigned((current) => current.includes(group.id) ? current.filter((id) => id !== group.id) : [...current, group.id])} /><Typography sx={{ flex: 1 }}>{group.name}<Typography component="span" variant="caption" color="text.secondary"> · {group.count}</Typography></Typography>{!group.system && <Button color="error" size="small" onClick={() => void onRun("delete_group", { module, id: group.id }, "分组已删除")}>删除</Button>}</Stack>)}{!selected.length && <Typography variant="caption" color="text.secondary">选择一条或多条记录后，可批量调整其分组。</Typography>}</Stack></DialogContent><DialogActions><Button onClick={onClose}>关闭</Button><Button variant="contained" disabled={!selected.length} onClick={() => void onRun("assign_groups", { module, ids: selected, groupIds: assigned }, "分组已更新").then(() => onClose())}>应用到所选记录</Button></DialogActions></Dialog>;
}

function SettingsDialog({ open, snapshot, onClose, onRun }: { open: boolean; snapshot: Snapshot; onClose: () => void; onRun: (action: string, payload?: Record<string, unknown>, success?: string) => Promise<unknown> }) {
  const [minutes, setMinutes] = useState(String(snapshot.autolockMinutes));
  const [otpCodesVisible, setOtpCodesVisible] = useState(snapshot.otpCodesVisible);
  const [passwordsVisible, setPasswordsVisible] = useState(snapshot.passwordsVisible);
  useEffect(() => {
    if (!open) return;
    setMinutes(String(snapshot.autolockMinutes));
    setOtpCodesVisible(snapshot.otpCodesVisible);
    setPasswordsVisible(snapshot.passwordsVisible);
  }, [open, snapshot.autolockMinutes, snapshot.otpCodesVisible, snapshot.passwordsVisible]);
  return <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
    <DialogTitle>设置</DialogTitle>
    <DialogContent dividers><Stack spacing={1.5}>
      <TextField label="自动锁定（分钟，0 为关闭）" type="number" value={minutes} onChange={(event) => setMinutes(event.target.value)} slotProps={{ htmlInput: { min: 0, max: 1440 } }} />
      <Divider />
      <Typography variant="subtitle2">默认显示</Typography>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}><Typography variant="body2">验证码</Typography><Switch slotProps={{ input: { "aria-label": "默认显示验证码" } }} checked={otpCodesVisible} onChange={(event) => setOtpCodesVisible(event.target.checked)} /></Stack>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}><Typography variant="body2">密码本密码</Typography><Switch slotProps={{ input: { "aria-label": "默认显示密码本密码" } }} checked={passwordsVisible} onChange={(event) => setPasswordsVisible(event.target.checked)} /></Stack>
      <Divider />
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}><Box><Typography variant="body2">窗口始终置顶</Typography><Typography variant="caption" color="text.secondary">完整窗口与轻量窗口共享</Typography></Box><Switch checked={snapshot.onTop} onChange={() => void onRun("toggle_topmost")} /></Stack>
      <Divider />
      <Typography variant="body2">本机 API：{snapshot.apiEndpoint || "未启动"}</Typography>
      <Button size="small" startIcon={<ContentCopyRounded />} onClick={() => void onRun("copy_api_token", {}, "API 令牌已复制")}>复制 API 令牌</Button>
    </Stack></DialogContent>
    <DialogActions><Button onClick={onClose}>取消</Button><Button variant="contained" onClick={() => void onRun("save_settings", { autolockMinutes: minutes, otpCodesVisible, passwordsVisible }, "设置已保存").then((result) => { if (result) onClose(); })}>保存</Button></DialogActions>
  </Dialog>;
}

function UnlockDialog({ open, onClose, onUnlock }: { open: boolean; onClose: () => void; onUnlock: (password: string) => void }) {
  const [password, setPassword] = useState("");
  useEffect(() => { if (!open) setPassword(""); }, [open]);
  return <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs"><DialogTitle>解锁保险库</DialogTitle><DialogContent><TextField autoFocus fullWidth margin="dense" type="password" label="主密码" value={password} onChange={(event) => setPassword(event.target.value)} onKeyDown={(event) => event.key === "Enter" && onUnlock(password)} /></DialogContent><DialogActions><Button onClick={onClose}>取消</Button><Button variant="contained" disabled={!password} onClick={() => onUnlock(password)}>解锁</Button></DialogActions></Dialog>;
}

function InfoDialog({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) { return <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs"><DialogTitle>{title}</DialogTitle><DialogContent dividers>{children}</DialogContent><DialogActions><Button onClick={onClose}>关闭</Button></DialogActions></Dialog>; }

function ConfirmDialog({ open, locked, action, count, onClose, onConfirm }: { open: boolean; locked: boolean; action: "delete" | null; count: number; onClose: () => void; onConfirm: () => void }) { const isDelete = action === "delete"; return <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth><DialogTitle>{locked ? "解锁保险库" : isDelete ? "删除记录" : "锁定保险库"}</DialogTitle><DialogContent><Typography>{locked ? "请输入主密码后解锁本地安全数据。" : isDelete ? `确定删除所选 ${count} 条记录吗？此操作无法撤销。` : "锁定后，验证码、密码本和本机 API 将无法访问。"}</Typography></DialogContent><DialogActions><Button onClick={onClose}>取消</Button><Button color={isDelete ? "error" : "primary"} variant="contained" onClick={onConfirm}>{locked ? "继续" : isDelete ? "删除" : "锁定"}</Button></DialogActions></Dialog>; }
