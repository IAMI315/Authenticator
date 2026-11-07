import {
  AddRounded,
  CloseRounded,
  ComputerRounded,
  DeleteOutlineRounded,
  EditOutlined,
  KeyRounded,
  LockResetRounded,
  MoreVertRounded,
  PlayArrowRounded,
  PowerSettingsNewRounded,
  PublicRounded,
  TerminalRounded,
  UploadFileRounded,
} from "@mui/icons-material";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  List,
  ListItemButton,
  ListItemText,
  Menu,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Stack,
  Switch,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { useCallback, useEffect, useRef, useState } from "react";
import { invoke, terminalInvoke } from "./bridge";
import type { ServerProfile, ServerTerminalTab, Snapshot } from "./types";

interface ServerForm {
  id?: string;
  name: string;
  host: string;
  port: string;
  username: string;
  authKind: "password" | "private_key";
  password: string;
  privateKeyPassphrase: string;
  privateKeyRef: string;
  privateKeyName: string;
  replaceCredentials: boolean;
  notes: string;
}

interface TerminalTab extends ServerTerminalTab {
}

interface TerminalEvent {
  type?: string;
  data?: string;
  status?: string;
  message?: string;
  algorithm?: string;
}

const emptyServerForm = (): ServerForm => ({
  name: "",
  host: "",
  port: "22",
  username: "",
  authKind: "password",
  password: "",
  privateKeyPassphrase: "",
  privateKeyRef: "",
  privateKeyName: "",
  replaceCredentials: true,
  notes: "",
});

function TerminalPane({ tab, active, onStatus, onAwaitHostKey }: {
  tab: TerminalTab;
  active: boolean;
  onStatus: (sessionId: string, status: string, message: string) => void;
  onAwaitHostKey: (sessionId: string, fingerprint: string, algorithm: string) => void;
}) {
  const mount = useRef<HTMLDivElement | null>(null);
  const terminalFinished = useRef(false);

  useEffect(() => {
    const target = mount.current;
    if (!target) return;
    const terminal = new Terminal({
      convertEol: true,
      cursorBlink: true,
      fontFamily: 'Consolas, "Cascadia Mono", monospace',
      fontSize: 13,
      theme: { background: "#102033", foreground: "#E6F1FF", cursor: "#90D7FF", selectionBackground: "#3B629080" },
      scrollback: 5000,
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.open(target);
    terminal.writeln("[正在连接服务器…]");
    terminalFinished.current = false;
    let disposed = false;
    let polling = false;
    let pollAbort: AbortController | undefined;
    let resizeTimer: number | undefined;
    let inputFrame: number | undefined;
    let inputSending = false;
    let queuedInput = "";
    const finish = (status: "closed" | "error", message: string) => {
      if (terminalFinished.current) return;
      terminalFinished.current = true;
      terminal.writeln(`\r\n[${message}]`);
      onStatus(tab.id, status, message);
    };
    const consume = (message: TerminalEvent) => {
      if (message.type === "output" && message.data) terminal.write(message.data);
      if (message.type !== "status") return;
      const status = message.status ?? "";
      const detail = message.message ?? "";
      onStatus(tab.id, status, detail);
      if (status === "awaiting_host_key") onAwaitHostKey(tab.id, detail, message.algorithm ?? "未知算法");
      if (status === "error" || status === "host_key_changed") {
        terminalFinished.current = true;
        const explanation = status === "host_key_changed"
          ? "服务器主机指纹已变化，请在详情中重置信任记录后再连接。"
          : detail || "连接失败";
        terminal.writeln(`\r\n[${explanation}]`);
      }
      if (status === "closed") {
        terminalFinished.current = true;
        terminal.writeln("\r\n[连接已关闭]");
      }
    };
    const consumeBatch = (events: TerminalEvent[]) => {
      // One terminal.write per batch avoids repeatedly reflowing xterm when a
      // command produces many small Paramiko packets.
      let output = "";
      const flushOutput = () => {
        if (output) terminal.write(output);
        output = "";
      };
      for (const event of events) {
        if (event.type === "output" && event.data) {
          output += event.data;
        } else {
          flushOutput();
          consume(event);
        }
      }
      flushOutput();
    };
    const poll = async () => {
      if (disposed || terminalFinished.current || polling) return;
      polling = true;
      const controller = new AbortController();
      pollAbort = controller;
      try {
        const result = await terminalInvoke<{ events: TerminalEvent[] }>(
          "terminal_events",
          { sessionId: tab.id, waitMs: 20_000 },
          controller.signal,
        );
        consumeBatch(result.events);
      } catch (caught) {
        if (disposed || (caught instanceof DOMException && caught.name === "AbortError")) return;
        const detail = caught instanceof Error ? caught.message : "终端连接中断";
        finish("error", detail);
      } finally {
        if (pollAbort === controller) pollAbort = undefined;
        polling = false;
        if (!disposed && !terminalFinished.current) queueMicrotask(() => void poll());
      }
    };
    const sendResize = () => {
      try {
        fit.fit();
        if (resizeTimer !== undefined) window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(() => {
          void terminalInvoke("terminal_resize", { sessionId: tab.id, cols: terminal.cols, rows: terminal.rows }).catch((caught) => {
            const detail = caught instanceof Error ? caught.message : "终端尺寸同步失败";
            finish("error", detail);
          });
        }, 40);
      } catch {
        // A hidden tab can report no layout; the next visible resize fixes it.
      }
    };
    const observer = new ResizeObserver(sendResize);
    observer.observe(target);
    sendResize();
    void poll();
    const flushInput = () => {
      inputFrame = undefined;
      if (disposed || terminalFinished.current || inputSending || !queuedInput) return;
      const data = queuedInput;
      queuedInput = "";
      inputSending = true;
      void terminalInvoke("terminal_input", { sessionId: tab.id, data }).catch((caught) => {
        const detail = caught instanceof Error ? caught.message : "终端输入失败";
        finish("error", detail);
      }).finally(() => {
        inputSending = false;
        if (!disposed && !terminalFinished.current && queuedInput && inputFrame === undefined) {
          inputFrame = window.requestAnimationFrame(flushInput);
        }
      });
    };
    const input = terminal.onData((data) => {
      if (!terminalFinished.current) {
        queuedInput += data;
        if (inputFrame === undefined && !inputSending) inputFrame = window.requestAnimationFrame(flushInput);
      }
    });
    terminal.focus();
    return () => {
      disposed = true;
      pollAbort?.abort();
      if (resizeTimer !== undefined) window.clearTimeout(resizeTimer);
      if (inputFrame !== undefined) window.cancelAnimationFrame(inputFrame);
      input.dispose();
      observer.disconnect();
      terminal.dispose();
    };
  }, [onAwaitHostKey, onStatus, tab.id]);

  useEffect(() => {
    if (active) window.setTimeout(() => window.dispatchEvent(new Event("resize")), 0);
  }, [active]);

  return <Box ref={mount} sx={{ display: active ? "block" : "none", height: "100%", minHeight: 0, p: 1.1, "& .xterm": { height: "100%" }, "& .xterm-viewport": { borderRadius: 1.5 } }} />;
}

export function ServerWorkspace({ snapshot, refresh }: {
  snapshot: Snapshot;
  refresh: () => Promise<void>;
}) {
  const profiles = snapshot.servers ?? [];
  const [selectedId, setSelectedId] = useState("");
  const [form, setForm] = useState<ServerForm | null>(null);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [menuProfile, setMenuProfile] = useState<ServerProfile | null>(null);
  const [tabs, setTabs] = useState<TerminalTab[]>([]);
  const [activeTab, setActiveTab] = useState("");
  const tabsRef = useRef<TerminalTab[]>([]);
  const activeTabRef = useRef("");
  const dismissedSessionIds = useRef(new Set<string>());
  const [hostKey, setHostKey] = useState<{ sessionId: string; fingerprint: string; algorithm: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<ServerProfile | null>(null);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const selected = profiles.find((profile) => profile.id === selectedId) ?? profiles[0];

  useEffect(() => {
    tabsRef.current = tabs;
  }, [tabs]);

  useEffect(() => {
    activeTabRef.current = activeTab;
  }, [activeTab]);

  useEffect(() => {
    const restored = (snapshot.terminalTabs ?? []).filter((tab) => !dismissedSessionIds.current.has(tab.id));
    if (!tabs.length && restored.length) {
      const restoredTabs = restored.map((tab) => ({ ...tab }));
      tabsRef.current = restoredTabs;
      activeTabRef.current = restoredTabs[0].id;
      setTabs(restoredTabs);
      setActiveTab(restoredTabs[0].id);
    }
  }, [snapshot.terminalTabs, tabs.length]);

  useEffect(() => {
    if (!selectedId && profiles[0]) setSelectedId(profiles[0].id);
    if (selectedId && !profiles.some((profile) => profile.id === selectedId)) setSelectedId(profiles[0]?.id ?? "");
  }, [profiles, selectedId]);

  useEffect(() => {
    if (snapshot.locked) {
      tabsRef.current = [];
      activeTabRef.current = "";
      setTabs([]);
      setActiveTab("");
      setHostKey(null);
    }
  }, [snapshot.locked]);

  const run = useCallback(async <T,>(
    action: string,
    payload: Record<string, unknown> = {},
    refreshAfter = true,
  ): Promise<T | undefined> => {
    try {
      const result = await invoke<T & { message?: string }>(action, payload);
      if (result && typeof result === "object" && "message" in result && result.message) setToast(String(result.message));
      if (refreshAfter) await refresh();
      return result;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "服务器操作失败");
      return undefined;
    }
  }, [refresh]);

  const openNew = () => setForm(emptyServerForm());
  const openEdit = async (profile: ServerProfile) => {
    const result = await run<ServerProfile>("server_details", { id: profile.id });
    if (!result) return;
    setForm({
      id: result.id, name: result.name, host: result.host, port: String(result.port), username: result.username,
      authKind: result.authKind, password: "", privateKeyPassphrase: "", privateKeyRef: "", privateKeyName: "",
      replaceCredentials: false, notes: result.notes,
    });
  };
  const chooseKey = async () => {
    const result = await run<{ keyRef: string; filename: string }>("server_choose_private_key");
    if (result?.keyRef) setForm((current) => current ? { ...current, privateKeyRef: result.keyRef, privateKeyName: result.filename, replaceCredentials: true } : current);
  };
  const save = async () => {
    if (!form) return;
    const result = await run<{ id: string }>("save_server", { server: { ...form, port: Number(form.port) } });
    if (result) {
      setSelectedId(result.id);
      setForm(null);
    }
  };
  const connect = async (profile = selected) => {
    if (!profile) return;
    const result = await run<{ sessionId: string; name: string; profileId: string }>("connect_server", { id: profile.id, cols: 100, rows: 28 }, false);
    if (!result) return;
    const tab: TerminalTab = { id: result.sessionId, name: result.name, profileId: result.profileId, status: "connecting" };
    setTabs((current) => {
      const next = [...current, tab];
      tabsRef.current = next;
      return next;
    });
    activeTabRef.current = tab.id;
    setActiveTab(tab.id);
  };
  const closeTab = useCallback((sessionId: string) => {
    if (dismissedSessionIds.current.has(sessionId)) return;
    dismissedSessionIds.current.add(sessionId);
    const currentTabs = tabsRef.current;
    const closingIndex = currentTabs.findIndex((tab) => tab.id === sessionId);
    const remaining = currentTabs.filter((tab) => tab.id !== sessionId);
    const currentActive = activeTabRef.current;
    const nextActive = currentActive === sessionId
      ? (remaining[closingIndex]?.id ?? remaining[closingIndex - 1]?.id ?? remaining[0]?.id ?? "")
      : currentActive;
    tabsRef.current = remaining;
    activeTabRef.current = nextActive;
    setTabs(remaining);
    setActiveTab(nextActive);
    setHostKey((current) => current?.sessionId === sessionId ? null : current);
    // Closing the rendered terminal must never wait for the Tk bridge queue.
    void terminalInvoke("terminal_disconnect", { sessionId }).catch(() => undefined);
  }, []);
  const disconnectProfile = async (profile: ServerProfile) => {
    const result = await run("disconnect_server_profile", { id: profile.id }, false);
    if (result) setTabs((current) => current.filter((tab) => tab.profileId !== profile.id));
  };
  const updateStatus = useCallback((sessionId: string, status: string, _message: string) => {
    setTabs((current) => current.map((tab) => tab.id === sessionId ? { ...tab, status } : tab));
  }, []);
  const awaitHostKey = useCallback((sessionId: string, fingerprint: string, algorithm: string) => {
    setHostKey({ sessionId, fingerprint, algorithm });
  }, []);
  const deleteProfile = async (profile: ServerProfile) => {
    const result = await run("delete_server", { id: profile.id });
    if (result) {
      setTabs((current) => current.filter((tab) => tab.profileId !== profile.id));
      setConfirmDelete(null);
    }
  };

  return <Box sx={{ flex: 1, minHeight: 0, display: "flex", gap: 1.5, p: 1.5 }}>
    <Paper variant="outlined" sx={{ width: 250, minWidth: 190, display: "flex", flexDirection: "column", overflow: "hidden", bgcolor: "rgba(255,255,255,.62)", backdropFilter: "blur(18px)", borderColor: "rgba(148,163,184,.22)" }}>
      <Box sx={{ p: 1.1, display: "flex", alignItems: "center", gap: .75, borderBottom: "1px solid rgba(148,163,184,.18)" }}>
        <Typography sx={{ fontWeight: 800, flex: 1 }}>服务器</Typography><Chip label={profiles.length} size="small" sx={{ height: 21 }} />
        <Tooltip title="新增服务器"><IconButton size="small" color="primary" onClick={openNew} disabled={snapshot.locked || snapshot.busy}><AddRounded /></IconButton></Tooltip>
      </Box>
      <List dense sx={{ px: .7, py: .7, overflow: "auto", flex: 1 }}>
        {profiles.map((profile) => <ListItemButton key={profile.id} selected={selected?.id === profile.id} onClick={() => setSelectedId(profile.id)} sx={{ borderRadius: 1.5, py: .75, px: .9, mb: .35, alignItems: "center" }}>
          <ComputerRounded fontSize="small" color="primary" /><ListItemText sx={{ ml: 1, minWidth: 0 }} primary={<Typography noWrap sx={{ fontSize: 13, fontWeight: 750 }}>{profile.name}</Typography>} secondary={<Typography noWrap variant="caption">{profile.username}@{profile.host}</Typography>} />
          <IconButton size="small" onClick={(event) => { event.stopPropagation(); setMenuAnchor(event.currentTarget); setMenuProfile(profile); }}><MoreVertRounded fontSize="small" /></IconButton>
        </ListItemButton>)}
        {!profiles.length && <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", px: 2, py: 4 }}>{snapshot.locked ? "保险库已锁定" : "尚未添加服务器"}</Typography>}
      </List>
      <Box sx={{ p: 1, borderTop: "1px solid rgba(148,163,184,.18)", color: "text.secondary" }}><Typography variant="caption">凭据仅保存在加密保险库中</Typography></Box>
    </Paper>

    <Paper variant="outlined" sx={{ minWidth: 0, flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", bgcolor: "rgba(255,255,255,.78)", backdropFilter: "blur(20px)", borderColor: "rgba(148,163,184,.22)" }}>
      {!selected ? <Box sx={{ flex: 1, display: "grid", placeItems: "center", color: "text.secondary" }}><Stack spacing={1} sx={{ alignItems: "center" }}><ComputerRounded sx={{ fontSize: 42, color: "primary.light" }} /><Typography>从左侧新增或选择一台服务器</Typography></Stack></Box> : <>
        <Box sx={{ px: 2, py: 1.3, display: "flex", alignItems: "center", gap: 1, borderBottom: "1px solid rgba(148,163,184,.18)" }}>
          <Box sx={{ width: 34, height: 34, display: "grid", placeItems: "center", color: "#158B89", bgcolor: "#E7F8F5", borderRadius: 1.7 }}><TerminalRounded fontSize="small" /></Box><Box sx={{ minWidth: 0, flex: 1 }}><Typography sx={{ fontWeight: 800 }} noWrap>{selected.name}</Typography><Typography variant="caption" color="text.secondary">{selected.username}@{selected.host}:{selected.port}</Typography></Box>
          <Button size="small" variant="contained" startIcon={<PlayArrowRounded />} disabled={snapshot.locked || snapshot.busy} onClick={() => void connect()}>连接</Button><Tooltip title="编辑"><IconButton size="small" onClick={() => void openEdit(selected)}><EditOutlined fontSize="small" /></IconButton></Tooltip>
        </Box>
        {tabs.length ? <>
          <Tabs value={activeTab} onChange={(_event, value) => setActiveTab(value)} variant="scrollable" scrollButtons="auto" sx={{ minHeight: 38, px: 1, borderBottom: "1px solid rgba(148,163,184,.18)", "& .MuiTab-root": { minHeight: 38, minWidth: 110, textTransform: "none" } }}>
            {tabs.map((tab) => <Tab key={tab.id} value={tab.id} label={<Stack direction="row" spacing={.4} sx={{ alignItems: "center" }}><Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: tab.status === "connected" ? "#17A673" : tab.status === "error" ? "#EA580C" : "#78A6C8" }} /><Typography noWrap sx={{ maxWidth: 96, fontSize: 12 }}>{tab.name}</Typography><CloseRounded role="button" aria-label={`关闭 ${tab.name} 终端`} tabIndex={0} onMouseDown={(event) => { event.preventDefault(); event.stopPropagation(); closeTab(tab.id); }} onClick={(event) => { event.preventDefault(); event.stopPropagation(); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); closeTab(tab.id); } }} sx={{ fontSize: 15, ml: .25, cursor: "pointer", borderRadius: .5, "&:hover": { color: "error.main", bgcolor: "rgba(239,68,68,.1)" } }} /></Stack>} />)}
          </Tabs>
          <Box sx={{ flex: 1, minHeight: 0, bgcolor: "#102033" }}>{tabs.map((tab) => <TerminalPane key={tab.id} tab={tab} active={activeTab === tab.id} onStatus={updateStatus} onAwaitHostKey={awaitHostKey} />)}</Box>
        </> : <Box sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 2.2 }}><Stack spacing={2}><Box sx={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 1.2 }}>{[["地址", selected.host], ["SSH 端口", String(selected.port)], ["用户名", selected.username], ["认证方式", selected.authKind === "password" ? "密码" : "私钥"]].map(([label, value]) => <Paper key={label} variant="outlined" sx={{ p: 1.1, bgcolor: "rgba(248,252,255,.76)" }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography noWrap sx={{ fontWeight: 700 }}>{value}</Typography></Paper>)}</Box><Divider /><Box><Typography variant="subtitle2" sx={{ mb: .5 }}>安全状态</Typography><Stack direction="row" spacing={.8} sx={{ flexWrap: "wrap" }}><Chip size="small" icon={<KeyRounded />} label={selected.credentialsConfigured ? "认证资料已配置" : "需要配置凭据"} color={selected.credentialsConfigured ? "success" : "warning"} /><Chip size="small" icon={<PublicRounded />} label={selected.trustedFingerprint ? `已信任 ${selected.trustedAlgorithm}` : "首次连接需确认指纹"} color={selected.trustedFingerprint ? "info" : "default"} /></Stack>{selected.trustedFingerprint && <Stack direction="row" spacing={.75} sx={{ mt: .9, alignItems: "center" }}><Typography variant="caption" sx={{ fontFamily: "monospace", wordBreak: "break-all", flex: 1 }}>{selected.trustedFingerprint}</Typography><Button size="small" startIcon={<LockResetRounded />} onClick={() => void run("reset_server_host_key", { id: selected.id })}>重置信任</Button></Stack>}</Box><Box><Typography variant="subtitle2" sx={{ mb: .5 }}>备注</Typography><Typography variant="body2" color={selected.notes ? "text.primary" : "text.secondary"} sx={{ whiteSpace: "pre-wrap" }}>{selected.notes || "暂无备注"}</Typography></Box></Stack></Box>}
      </>}
    </Paper>

    <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={() => setMenuAnchor(null)}>{menuProfile && <><MenuItem onClick={() => { setMenuAnchor(null); void connect(menuProfile); }}><PlayArrowRounded fontSize="small" /><Box sx={{ ml: 1 }}>连接</Box></MenuItem><MenuItem onClick={() => { setMenuAnchor(null); void openEdit(menuProfile); }}><EditOutlined fontSize="small" /><Box sx={{ ml: 1 }}>编辑</Box></MenuItem><MenuItem onClick={() => { setMenuAnchor(null); void disconnectProfile(menuProfile); }}><PowerSettingsNewRounded fontSize="small" /><Box sx={{ ml: 1 }}>断开</Box></MenuItem><MenuItem sx={{ color: "error.main" }} onClick={() => { setMenuAnchor(null); setConfirmDelete(menuProfile); }}><DeleteOutlineRounded fontSize="small" /><Box sx={{ ml: 1 }}>删除</Box></MenuItem></>}</Menu>

    <Dialog open={Boolean(form)} onClose={() => setForm(null)} fullWidth maxWidth="sm">
      <DialogTitle>{form?.id ? "编辑服务器" : "新增服务器"}</DialogTitle>
      <DialogContent dividers>
        {form && <Stack spacing={1.25} sx={{ pt: .5 }}>
          <TextField autoFocus required label="名称" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
          <Stack direction="row" spacing={1}>
            <TextField required label="IP 或域名" value={form.host} onChange={(event) => setForm({ ...form, host: event.target.value })} fullWidth />
            <TextField required label="SSH 端口" type="number" value={form.port} onChange={(event) => setForm({ ...form, port: event.target.value })} sx={{ width: 130 }} slotProps={{ htmlInput: { min: 1, max: 65535 } }} />
          </Stack>
          <TextField required label="用户名" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} />
          <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between" }}>
            <Typography variant="body2">{form.id ? "更新认证资料" : "配置认证资料"}</Typography>
            <Switch checked={form.replaceCredentials} onChange={(_event, checked) => setForm({ ...form, replaceCredentials: checked })} />
          </Stack>
          {form.replaceCredentials && <>
            <FormControl fullWidth size="small">
              <InputLabel>认证方式</InputLabel>
              <Select label="认证方式" value={form.authKind} onChange={(event) => setForm({ ...form, authKind: event.target.value as ServerForm["authKind"], privateKeyRef: "", privateKeyName: "" })}>
                <MenuItem value="password">密码</MenuItem><MenuItem value="private_key">导入私钥</MenuItem>
              </Select>
            </FormControl>
            {form.authKind === "password" ? <TextField required label="SSH 密码" type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} autoComplete="new-password" /> : <>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <Button variant="outlined" startIcon={<UploadFileRounded />} onClick={() => void chooseKey()}>选择私钥文件</Button>
                <Typography variant="caption" color="text.secondary" noWrap>{form.privateKeyName || "尚未选择私钥"}</Typography>
              </Stack>
              <TextField label="私钥口令（如有）" type="password" value={form.privateKeyPassphrase} onChange={(event) => setForm({ ...form, privateKeyPassphrase: event.target.value })} autoComplete="new-password" />
            </>}
          </>}
          <TextField label="备注" value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} multiline minRows={3} />
        </Stack>}
      </DialogContent>
      <DialogActions><Button onClick={() => setForm(null)}>取消</Button><Button variant="contained" onClick={() => void save()}>保存</Button></DialogActions>
    </Dialog>

    <Dialog open={Boolean(hostKey)} onClose={() => { if (hostKey) void terminalInvoke("terminal_disconnect", { sessionId: hostKey.sessionId }).catch(() => undefined); setHostKey(null); }} fullWidth maxWidth="xs"><DialogTitle>确认服务器指纹</DialogTitle><DialogContent><Typography variant="body2">这是首次连接。请仅在通过其他可靠渠道确认服务器指纹后继续。</Typography><Stack spacing={.5} sx={{ mt: 1.5 }}><Typography variant="caption" color="text.secondary">算法：{hostKey?.algorithm}</Typography><Paper variant="outlined" sx={{ p: 1, bgcolor: "rgba(248,252,255,.76)", fontFamily: "monospace", fontSize: 12, wordBreak: "break-all" }}>{hostKey?.fingerprint}</Paper></Stack></DialogContent><DialogActions><Button onClick={() => { if (hostKey) void terminalInvoke("terminal_disconnect", { sessionId: hostKey.sessionId }).catch(() => undefined); setHostKey(null); }}>拒绝</Button><Button variant="contained" onClick={() => { if (hostKey) void run("confirm_server_host_key", { sessionId: hostKey.sessionId }); setHostKey(null); }}>信任并连接</Button></DialogActions></Dialog>

    <Dialog open={Boolean(confirmDelete)} onClose={() => setConfirmDelete(null)} fullWidth maxWidth="xs"><DialogTitle>删除服务器</DialogTitle><DialogContent><Typography>确定删除“{confirmDelete?.name}”吗？保存的连接凭据和信任记录会一起删除。</Typography></DialogContent><DialogActions><Button onClick={() => setConfirmDelete(null)}>取消</Button><Button color="error" variant="contained" onClick={() => confirmDelete && void deleteProfile(confirmDelete)}>删除</Button></DialogActions></Dialog>
    <Snackbar open={Boolean(toast)} autoHideDuration={3200} onClose={() => setToast("")} message={toast} /><Snackbar open={Boolean(error)} autoHideDuration={6000} onClose={() => setError("")}><Alert severity="error" onClose={() => setError("")}>{error}</Alert></Snackbar>
  </Box>;
}
