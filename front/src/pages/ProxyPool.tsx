import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Loader2,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Label,
  PageHeader,
  Textarea,
  Toast,
} from "@/components/ui";

type ProxyItem = {
  id: string;
  url: string;
  display_url: string;
  protocol: string;
  latency_ms: number | null;
  status: string;
  last_checked: number | null;
  fail_count: number;
  exit_ip?: string;
};

export function ProxyPoolPage() {
  const [items, setItems] = useState<ProxyItem[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [toast, setToast] = useState<{ message: string; tone?: "default" | "success" | "error" }>({
    message: "",
  });

  const notify = (message: string, tone: "default" | "success" | "error" = "default") => {
    setToast({ message, tone });
    window.setTimeout(() => setToast({ message: "" }), 2400);
  };

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.proxies.list();
      setItems((data.items as ProxyItem[]) || []);
    } catch (error: any) {
      notify(error.message || "加载代理池失败", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const selectedIds = Object.entries(selected)
    .filter(([, value]) => value)
    .map(([id]) => id);

  const toggleAll = (checked: boolean) => {
    if (!checked) {
      setSelected({});
      return;
    }
    const next: Record<string, boolean> = {};
    for (const item of items) next[item.id] = true;
    setSelected(next);
  };

  const handleAdd = async () => {
    if (!input.trim()) return;
    setBusy("add");
    try {
      const data = await api.proxies.add({ lines: input });
      const result = (data as any).result || data;
      setItems(((data as any).items as ProxyItem[]) || items);
      setInput("");
      notify(
        `新增 ${result.added ?? 0}，跳过 ${result.skipped ?? 0}，无效 ${result.invalid ?? 0}`,
        "success"
      );
      await load();
    } catch (error: any) {
      notify(error.message || "添加失败", "error");
    } finally {
      setBusy("");
    }
  };

  const handleProbe = async (ids?: string[]) => {
    setBusy("probe");
    try {
      const data = await api.proxies.probe({ ids, delay_ms: 200 });
      const result = (data as any).result || data;
      setItems(((data as any).items as ProxyItem[]) || items);
      notify(
        `探测完成：可用 ${result.ok ?? 0}，失败 ${result.failed ?? 0}`,
        "success"
      );
      await load();
    } catch (error: any) {
      notify(error.message || "探测失败", "error");
    } finally {
      setBusy("");
    }
  };

  const handleDelete = async (ids: string[]) => {
    if (!ids.length) return;
    if (!window.confirm(`确认删除 ${ids.length} 条代理？`)) return;
    setBusy("delete");
    try {
      const data = await api.proxies.delete(ids);
      setItems(((data as any).items as ProxyItem[]) || []);
      setSelected({});
      notify(`已删除 ${data.deleted ?? ids.length} 条`, "success");
      await load();
    } catch (error: any) {
      notify(error.message || "删除失败", "error");
    } finally {
      setBusy("");
    }
  };

  const handleDeleteFailed = async () => {
    if (!window.confirm("确认删除所有失效代理？")) return;
    setBusy("delete-failed");
    try {
      const data = await api.proxies.deleteFailed({ min_fail_count: 1 });
      setItems(((data as any).items as ProxyItem[]) || []);
      setSelected({});
      notify(`已删除 ${data.deleted ?? 0} 条失效代理`, "success");
      await load();
    } catch (error: any) {
      notify(error.message || "删除失败", "error");
    } finally {
      setBusy("");
    }
  };

  const statusBadge = (item: ProxyItem) => {
    if (item.status === "ok") {
      return (
        <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100">
          可用{item.latency_ms != null ? ` · ${item.latency_ms}ms` : ""}
        </Badge>
      );
    }
    if (item.status === "failed") {
      return <Badge className="bg-rose-100 text-rose-700 hover:bg-rose-100">失效</Badge>;
    }
    return <Badge variant="secondary">未知</Badge>;
  };

  return (
    <div className="space-y-5 sm:space-y-6">
      <PageHeader
        title="代理池"
        description="每行一条代理地址；支持 http / socks5 与用户名密码；可批量探测延迟并删除失效项。"
        actions={
          <>
            <Link to="/settings">
              <Button variant="outline">
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                返回设置
              </Button>
            </Link>
            <Button variant="outline" onClick={() => void load()} disabled={loading || !!busy}>
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
              刷新
            </Button>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader className="flex-row items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sky-50 text-sky-600">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <CardTitle>添加代理</CardTitle>
              <CardDescription>每行一个 URL，支持 # 注释行。</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="proxy-lines">代理列表</Label>
              <Textarea
                id="proxy-lines"
                className="min-h-40 font-mono text-xs"
                placeholder={"http://user:pass@host:8080\nsocks5://user:pass@host:1080\n# 注释行会被忽略"}
                value={input}
                onChange={(event) => setInput(event.target.value)}
              />
            </div>
            <Button className="w-full" onClick={() => void handleAdd()} disabled={!!busy || !input.trim()}>
              {busy === "add" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              添加代理
            </Button>
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                onClick={() => void handleProbe()}
                disabled={!!busy || items.length === 0}
              >
                {busy === "probe" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                探测全部
              </Button>
              <Button
                variant="outline"
                onClick={() => void handleDeleteFailed()}
                disabled={!!busy || items.length === 0}
              >
                <Trash2 className="h-4 w-4" />
                删除失效
              </Button>
            </div>
            <p className="text-xs leading-5 text-muted-foreground">
              注册时优先从代理池选取；池为空时回退到「网络代理」单条配置。
            </p>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
            <div>
              <CardTitle>代理列表</CardTitle>
              <CardDescription>
                共 {items.length} 条
                {selectedIds.length ? `，已选 ${selectedIds.length}` : ""}
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!selectedIds.length || !!busy}
                onClick={() => void handleProbe(selectedIds)}
              >
                探测选中
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!selectedIds.length || !!busy}
                onClick={() => void handleDelete(selectedIds)}
              >
                删除选中
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? (
              <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                加载中…
              </div>
            ) : items.length === 0 ? (
              <div className="p-6">
                <EmptyState title="暂无代理" description="在左侧粘贴多行代理地址后点击添加。" />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
                    <tr>
                      <th className="w-10 px-4 py-3">
                        <input
                          type="checkbox"
                          checked={items.length > 0 && items.every((item) => selected[item.id])}
                          onChange={(event) => toggleAll(event.target.checked)}
                          aria-label="全选"
                        />
                      </th>
                      <th className="px-3 py-3 font-medium">代理</th>
                      <th className="px-3 py-3 font-medium">协议</th>
                      <th className="px-3 py-3 font-medium">状态</th>
                      <th className="px-3 py-3 font-medium">出口</th>
                      <th className="px-3 py-3 font-medium">失败</th>
                      <th className="px-3 py-3 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => (
                      <tr key={item.id} className="border-b last:border-0">
                        <td className="px-4 py-3 align-middle">
                          <input
                            type="checkbox"
                            checked={!!selected[item.id]}
                            onChange={(event) =>
                              setSelected((previous) => {
                                const next = { ...previous };
                                if (event.target.checked) next[item.id] = true;
                                else delete next[item.id];
                                return next;
                              })
                            }
                            aria-label={`选择 ${item.display_url}`}
                          />
                        </td>
                        <td className="max-w-[280px] truncate px-3 py-3 font-mono text-xs" title={item.url}>
                          {item.display_url || item.url}
                        </td>
                        <td className="px-3 py-3 uppercase text-xs text-muted-foreground">
                          {item.protocol || "-"}
                        </td>
                        <td className="px-3 py-3">{statusBadge(item)}</td>
                        <td className="px-3 py-3 font-mono text-xs text-muted-foreground">
                          {item.exit_ip || "-"}
                        </td>
                        <td className="px-3 py-3 text-xs">{item.fail_count || 0}</td>
                        <td className="px-3 py-3">
                          <div className="flex gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={!!busy}
                              onClick={() => void handleProbe([item.id])}
                            >
                              探测
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive"
                              disabled={!!busy}
                              onClick={() => void handleDelete([item.id])}
                            >
                              <X className="h-4 w-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {toast.message ? <Toast message={toast.message} tone={toast.tone} /> : null}
    </div>
  );
}
