import { useState, useEffect, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';
import {
  Trash2,
  Shield,
  ArrowLeft,
  LayoutDashboard,
  Users,
  Ticket,
  RefreshCw,
} from 'lucide-react';

interface UserRow {
  id: number;
  username: string;
  email: string;
  email_verified: boolean;
  is_admin: boolean;
  is_active: boolean;
  /** Суммарно списанные токены OpenAI (вход+выход по ответам API) */
  openai_tokens_total?: number;
}

interface PromoRow {
  id: number;
  code: string;
  is_active: boolean;
  description: string;
}

interface Stats {
  users: number;
  admins: number;
  tenders: number;
  promocodes: number;
  email_verified: number;
  /** Сумма по всем пользователям; может отсутствовать у старых бэкендов */
  openai_tokens_total?: number;
}

const authHeaders = () => {
  const token = localStorage.getItem('access_token');
  return { Authorization: `Bearer ${token}` } as Record<string, string>;
};

const Admin = () => {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [promos, setPromos] = useState<PromoRow[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingPromos, setLoadingPromos] = useState(false);
  const [deleteUserId, setDeleteUserId] = useState<number | null>(null);
  const [deletePromoId, setDeletePromoId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [newPromoCode, setNewPromoCode] = useState('');
  const [newPromoDesc, setNewPromoDesc] = useState('');
  const [creatingPromo, setCreatingPromo] = useState(false);
  const [togglingPromoId, setTogglingPromoId] = useState<number | null>(null);
  const navigate = useNavigate();

  const redirectIfUnauthorized = (res: Response) => {
    if (res.status === 401) {
      navigate('/auth');
      return true;
    }
    if (res.status === 403) {
      toast.error('Доступ запрещён. Нужны права администратора.');
      navigate('/app');
      return true;
    }
    return false;
  };

  const loadMe = useCallback(async () => {
    try {
      const res = await fetch('/api/users/me', { headers: authHeaders() });
      if (redirectIfUnauthorized(res)) return;
      if (res.ok) {
        const data = await res.json();
        setCurrentUserId(data.id ?? null);
      }
    } catch {
      /* ignore */
    }
  }, [navigate]);

  const loadStats = useCallback(async () => {
    try {
      const res = await fetch('/admin/stats', { headers: authHeaders() });
      if (redirectIfUnauthorized(res)) return;
      if (res.ok) setStats(await res.json());
    } catch {
      toast.error('Не удалось загрузить статистику');
    }
  }, [navigate]);

  const loadUsers = useCallback(async () => {
    try {
      const res = await fetch('/admin/users', { headers: authHeaders() });
      if (redirectIfUnauthorized(res)) return;
      const data = await res.json();
      setUsers(data);
    } catch {
      toast.error('Ошибка загрузки пользователей');
    }
  }, [navigate]);

  const loadPromos = useCallback(async () => {
    setLoadingPromos(true);
    try {
      const res = await fetch('/admin/promocodes', { headers: authHeaders() });
      if (redirectIfUnauthorized(res)) return;
      const data = await res.json();
      setPromos(data);
    } catch {
      toast.error('Ошибка загрузки промокодов');
    } finally {
      setLoadingPromos(false);
    }
  }, [navigate]);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadMe(), loadStats(), loadUsers(), loadPromos()]);
    setLoading(false);
  }, [loadMe, loadStats, loadUsers, loadPromos]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  const handleDeleteUser = async () => {
    if (!deleteUserId) return;
    setDeleting(true);
    try {
      const res = await fetch(`/admin/users/${deleteUserId}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setUsers((prev) => prev.filter((u) => u.id !== deleteUserId));
        toast.success('Пользователь удалён');
        setDeleteUserId(null);
        loadStats();
      } else {
        toast.error(typeof data.detail === 'string' ? data.detail : 'Ошибка удаления');
      }
    } catch {
      toast.error('Ошибка соединения');
    } finally {
      setDeleting(false);
    }
  };

  const handleCreatePromo = async (e: React.FormEvent) => {
    e.preventDefault();
    const code = newPromoCode.trim().toUpperCase();
    if (!code) {
      toast.error('Введите код промокода');
      return;
    }
    setCreatingPromo(true);
    try {
      const res = await fetch('/admin/promocodes', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, description: newPromoDesc.trim() || null }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        toast.success('Промокод создан');
        setNewPromoCode('');
        setNewPromoDesc('');
        loadPromos();
        loadStats();
      } else {
        toast.error(typeof data.detail === 'string' ? data.detail : 'Не удалось создать');
      }
    } catch {
      toast.error('Ошибка соединения');
    } finally {
      setCreatingPromo(false);
    }
  };

  const handleTogglePromo = async (p: PromoRow, next: boolean) => {
    setTogglingPromoId(p.id);
    try {
      const res = await fetch(`/admin/promocodes/${p.id}`, {
        method: 'PATCH',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: next }),
      });
      if (res.ok) {
        setPromos((prev) =>
          prev.map((x) => (x.id === p.id ? { ...x, is_active: next } : x))
        );
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(typeof data.detail === 'string' ? data.detail : 'Ошибка');
      }
    } catch {
      toast.error('Ошибка соединения');
    } finally {
      setTogglingPromoId(null);
    }
  };

  const handleDeletePromo = async () => {
    if (!deletePromoId) return;
    setDeleting(true);
    try {
      const res = await fetch(`/admin/promocodes/${deletePromoId}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (res.ok) {
        setPromos((prev) => prev.filter((p) => p.id !== deletePromoId));
        toast.success('Промокод удалён');
        setDeletePromoId(null);
        loadStats();
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(typeof data.detail === 'string' ? data.detail : 'Ошибка');
      }
    } catch {
      toast.error('Ошибка соединения');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-50 w-full border-b bg-card/95 backdrop-blur">
        <div className="container flex h-16 items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <Link to="/app">
              <Button variant="ghost" size="sm" className="gap-2 shrink-0">
                <ArrowLeft className="h-4 w-4" />
                <span className="hidden sm:inline">В кабинет</span>
              </Button>
            </Link>
            <div className="flex items-center gap-2 min-w-0">
              <Shield className="h-5 w-5 text-primary shrink-0" />
              <span className="font-semibold truncate">Панель администратора</span>
            </div>
          </div>
          <Button variant="outline" size="sm" className="gap-2 shrink-0" onClick={() => refreshAll()} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Обновить
          </Button>
        </div>
      </header>

      <main className="container py-8 max-w-5xl">
        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList className="grid w-full grid-cols-3 h-auto p-1 sm:inline-flex sm:w-auto">
            <TabsTrigger value="overview" className="gap-2 py-2.5">
              <LayoutDashboard className="h-4 w-4" />
              Обзор
            </TabsTrigger>
            <TabsTrigger value="users" className="gap-2 py-2.5">
              <Users className="h-4 w-4" />
              Пользователи
            </TabsTrigger>
            <TabsTrigger value="promos" className="gap-2 py-2.5">
              <Ticket className="h-4 w-4" />
              Промокоды
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4 mt-6">
            {loading && !stats ? (
              <div className="py-16 text-center text-muted-foreground">Загрузка...</div>
            ) : stats ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Пользователей</CardDescription>
                    <CardTitle className="text-3xl tabular-nums">{stats.users}</CardTitle>
                  </CardHeader>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Администраторов</CardDescription>
                    <CardTitle className="text-3xl tabular-nums">{stats.admins}</CardTitle>
                  </CardHeader>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Подтверждённых email</CardDescription>
                    <CardTitle className="text-3xl tabular-nums">{stats.email_verified}</CardTitle>
                  </CardHeader>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Тендеров в базе</CardDescription>
                    <CardTitle className="text-3xl tabular-nums">{stats.tenders}</CardTitle>
                  </CardHeader>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Промокодов</CardDescription>
                    <CardTitle className="text-3xl tabular-nums">{stats.promocodes}</CardTitle>
                  </CardHeader>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Токены OpenAI (все пользователи)</CardDescription>
                    <CardTitle className="text-3xl tabular-nums">
                      {(stats.openai_tokens_total ?? 0).toLocaleString('ru-RU')}
                    </CardTitle>
                  </CardHeader>
                </Card>
              </div>
            ) : null}
            <Card className="border-dashed">
              <CardContent className="pt-6 text-sm text-muted-foreground">
                Учётная запись по умолчанию: <code className="rounded bg-muted px-1.5 py-0.5">admin</code> /{' '}
                <code className="rounded bg-muted px-1.5 py-0.5">admin123</code> — смените пароль в продакшене.
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="users" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>Пользователи</CardTitle>
                <CardDescription>
                  Удаление недоступно для вашей учётной записи. Последнего администратора удалить нельзя.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="py-12 text-center text-muted-foreground">Загрузка...</div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-14">ID</TableHead>
                        <TableHead>Логин</TableHead>
                        <TableHead>Email</TableHead>
                        <TableHead>Роль</TableHead>
                        <TableHead>Подтверждён</TableHead>
                        <TableHead className="text-right whitespace-nowrap">Токены OpenAI</TableHead>
                        <TableHead className="w-[60px]" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {users.map((u) => (
                        <TableRow key={u.id}>
                          <TableCell className="font-mono text-sm">{u.id}</TableCell>
                          <TableCell className="font-medium">{u.username}</TableCell>
                          <TableCell className="text-muted-foreground max-w-[200px] truncate" title={u.email}>
                            {u.email || '—'}
                          </TableCell>
                          <TableCell>
                            {u.is_admin ? (
                              <Badge className="bg-emerald-600">Admin</Badge>
                            ) : (
                              <Badge variant="secondary">User</Badge>
                            )}
                          </TableCell>
                          <TableCell>
                            {u.email_verified ? (
                              <Badge variant="outline" className="text-emerald-600 border-emerald-600/50">
                                ✓
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-amber-600 border-amber-600/50">
                                Нет
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell className="text-right tabular-nums text-muted-foreground">
                            {(u.openai_tokens_total ?? 0).toLocaleString('ru-RU')}
                          </TableCell>
                          <TableCell>
                            {currentUserId !== u.id && (
                              <Button
                                variant="ghost"
                                size="icon"
                                className="text-destructive hover:text-destructive hover:bg-destructive/10"
                                onClick={() => setDeleteUserId(u.id)}
                                title="Удалить"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
                {!loading && users.length === 0 && (
                  <div className="py-12 text-center text-muted-foreground">Пользователей нет</div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="promos" className="mt-6 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Новый промокод</CardTitle>
                <CardDescription>Код будет приведён к верхнему регистру при создании.</CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleCreatePromo} className="flex flex-col gap-4 sm:flex-row sm:items-end">
                  <div className="space-y-2 flex-1">
                    <Label htmlFor="promo-code">Код</Label>
                    <Input
                      id="promo-code"
                      placeholder="PRO2026"
                      value={newPromoCode}
                      onChange={(e) => setNewPromoCode(e.target.value)}
                      maxLength={32}
                    />
                  </div>
                  <div className="space-y-2 flex-[2]">
                    <Label htmlFor="promo-desc">Описание (необязательно)</Label>
                    <Input
                      id="promo-desc"
                      placeholder="Например: скидка на Pro"
                      value={newPromoDesc}
                      onChange={(e) => setNewPromoDesc(e.target.value)}
                    />
                  </div>
                  <Button type="submit" disabled={creatingPromo}>
                    {creatingPromo ? 'Создание…' : 'Создать'}
                  </Button>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Список промокодов</CardTitle>
                <CardDescription>Отключённые коды не принимаются при активации Pro.</CardDescription>
              </CardHeader>
              <CardContent>
                {loadingPromos ? (
                  <div className="py-12 text-center text-muted-foreground">Загрузка...</div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Код</TableHead>
                        <TableHead>Описание</TableHead>
                        <TableHead className="w-[120px]">Активен</TableHead>
                        <TableHead className="w-[60px]" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {promos.map((p) => (
                        <TableRow key={p.id}>
                          <TableCell className="font-mono font-medium">{p.code}</TableCell>
                          <TableCell className="text-muted-foreground max-w-[280px] truncate" title={p.description}>
                            {p.description || '—'}
                          </TableCell>
                          <TableCell>
                            <Switch
                              checked={p.is_active}
                              disabled={togglingPromoId === p.id}
                              onCheckedChange={(checked) => handleTogglePromo(p, checked)}
                            />
                          </TableCell>
                          <TableCell>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="text-destructive hover:text-destructive hover:bg-destructive/10"
                              onClick={() => setDeletePromoId(p.id)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
                {!loadingPromos && promos.length === 0 && (
                  <div className="py-12 text-center text-muted-foreground">Промокодов пока нет</div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>

      <AlertDialog open={deleteUserId !== null} onOpenChange={(open) => !open && setDeleteUserId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить пользователя?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteUserId &&
                (() => {
                  const u = users.find((x) => x.id === deleteUserId);
                  return u
                    ? `Будет удалён пользователь «${u.username}» (${u.email || 'без email'}). Действие необратимо.`
                    : '';
                })()}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteUser}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? 'Удаление…' : 'Удалить'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deletePromoId !== null} onOpenChange={(open) => !open && setDeletePromoId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить промокод?</AlertDialogTitle>
            <AlertDialogDescription>
              {deletePromoId &&
                (() => {
                  const p = promos.find((x) => x.id === deletePromoId);
                  return p ? `Код «${p.code}» будет удалён.` : '';
                })()}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeletePromo}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? 'Удаление…' : 'Удалить'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default Admin;
