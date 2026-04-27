import { useState, useEffect, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { TelegramConnectDialog } from '@/components/TelegramConnectDialog';
import { toast } from 'sonner';
import {
  ArrowLeft,
  User,
  Mail,
  Sparkles,
  Send,
  Shield,
  Loader2,
} from 'lucide-react';

interface MeData {
  username: string;
  id: number;
  is_admin: boolean;
  is_pro: boolean;
  email: string | null;
  email_verified: boolean;
  telegram_id: number | null;
  company_description: string | null;
  can_save_description_free: boolean;
  description_last_saved: string | null;
}

const Profile = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [savingDesc, setSavingDesc] = useState(false);
  const [me, setMe] = useState<MeData | null>(null);
  const [description, setDescription] = useState('');
  const [tgOpen, setTgOpen] = useState(false);
  const [tgForceRegenerate, setTgForceRegenerate] = useState(false);

  const authHeaders = () => {
    const token = localStorage.getItem('access_token');
    return { Authorization: `Bearer ${token}` } as Record<string, string>;
  };

  const load = useCallback(async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      navigate('/auth');
      return;
    }
    try {
      const res = await fetch('/users/me', { headers: authHeaders() });
      if (res.status === 401) {
        navigate('/auth');
        return;
      }
      if (!res.ok) {
        toast.error('Не удалось загрузить профиль');
        return;
      }
      const data: MeData = await res.json();
      setMe(data);
      setDescription(data.company_description || '');
    } catch {
      toast.error('Ошибка сети');
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    load();
  }, [load]);

  const saveDescription = async () => {
    if (!me) return;
    setSavingDesc(true);
    try {
      const res = await fetch('/api/users/me/description', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ description }),
      });
      if (res.ok) {
        toast.success('Описание компании сохранено');
        await load();
        return;
      }
      const err = await res.json().catch(() => ({}));
      if (res.status === 402 && err.detail?.code === 'SAVE_LIMIT') {
        toast.error(
          'Повторное изменение: раз в месяц бесплатно или оплатите разблокировку (299 ₽) в поиске тендеров.'
        );
        return;
      }
      toast.error('Не удалось сохранить');
    } catch {
      toast.error('Ошибка соединения');
    } finally {
      setSavingDesc(false);
    }
  };

  if (loading || !me) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-50 w-full border-b bg-card/95 backdrop-blur">
        <div className="container flex h-16 items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link to="/app">
              <Button variant="ghost" size="sm" className="gap-2">
                <ArrowLeft className="h-4 w-4" />
                К тендерам
              </Button>
            </Link>
            <div className="flex items-center gap-2">
              <User className="h-5 w-5 text-primary" />
              <span className="font-semibold">Профиль</span>
            </div>
          </div>
          {me.is_admin && (
            <Link to="/admin">
              <Button variant="outline" size="sm" className="gap-2">
                <Shield className="h-4 w-4" />
                Админ-панель
              </Button>
            </Link>
          )}
        </div>
      </header>

      <main className="container py-8 max-w-2xl space-y-6">
        <Card>
          <CardHeader>
            <div className="flex items-start gap-4">
              <div className="h-16 w-16 rounded-2xl bg-primary/10 flex items-center justify-center text-2xl font-bold text-primary shrink-0">
                {me.username.slice(0, 2).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <CardTitle className="text-xl truncate">{me.username}</CardTitle>
                <CardDescription className="mt-1">ID: {me.id}</CardDescription>
                <div className="flex flex-wrap gap-2 mt-3">
                  {me.is_pro ? (
                    <Badge className="bg-gradient-to-r from-amber-500 to-orange-600 gap-1">
                      <Sparkles className="h-3 w-3" />
                      Tendrix Pro
                    </Badge>
                  ) : (
                    <Badge variant="secondary">Базовый тариф</Badge>
                  )}
                  {me.is_admin && <Badge variant="default">Администратор</Badge>}
                </div>
              </div>
            </div>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Mail className="h-5 w-5" />
              Контакты
            </CardTitle>
            <CardDescription>Email и статус подтверждения</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label className="text-muted-foreground text-xs">Email</Label>
              <p className="font-medium mt-0.5 break-all">{me.email || '—'}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {me.email_verified ? (
                <Badge variant="outline" className="text-emerald-600 border-emerald-600/50">
                  Email подтверждён
                </Badge>
              ) : (
                <>
                  <Badge variant="outline" className="text-amber-600 border-amber-600/50">
                    Не подтверждён
                  </Badge>
                  <Button variant="link" className="h-auto p-0" asChild>
                    <Link to="/verify-email-code">Подтвердить email</Link>
                  </Button>
                </>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Send className="h-5 w-5 text-[#0088cc]" />
              Telegram
            </CardTitle>
            <CardDescription>Уведомления о тендерах в боте</CardDescription>
          </CardHeader>
          <CardContent>
            {me.telegram_id ? (
              <div className="space-y-3">
                <p className="text-sm text-emerald-600 dark:text-emerald-400">
                  Аккаунт подключён (Telegram ID: {me.telegram_id})
                </p>
                <Button
                  type="button"
                  variant="outline"
                  className="gap-2"
                  onClick={() => {
                    setTgForceRegenerate(true);
                    setTgOpen(true);
                  }}
                >
                  <Send className="h-4 w-4" />
                  Обновить код привязки
                </Button>
              </div>
            ) : (
              <Button
                type="button"
                variant="outline"
                className="gap-2"
                onClick={() => {
                  setTgForceRegenerate(false);
                  setTgOpen(true);
                }}
              >
                <Send className="h-4 w-4" />
                Связать с Telegram
              </Button>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Описание компании</CardTitle>
            <CardDescription>
              Используется для персонализации поиска и ИИ-анализа.{' '}
              {me.description_last_saved && (
                <span className="block mt-1 text-xs">
                  Последнее сохранение:{' '}
                  {new Date(me.description_last_saved).toLocaleString('ru-RU')}
                </span>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Кратко опишите профиль компании, отрасль, интересующие закупки..."
              rows={6}
              className="resize-y min-h-[120px]"
            />
            <div className="flex flex-wrap gap-2 items-center">
              <Button type="button" onClick={() => void saveDescription()} disabled={savingDesc}>
                {savingDesc ? 'Сохранение…' : 'Сохранить описание'}
              </Button>
              {!me.can_save_description_free && (
                <span className="text-xs text-muted-foreground">
                  Бесплатное сохранение в этом месяце уже использовано — повторное изменение через поиск
                  тендеров (оплата 299 ₽) или дождитесь следующего месяца.
                </span>
              )}
            </div>
          </CardContent>
        </Card>

        <Separator />

        <div className="flex justify-center pb-8">
          <Button variant="ghost" className="text-muted-foreground" asChild>
            <Link to="/app">Вернуться в личный кабинет</Link>
          </Button>
        </div>
      </main>

      <TelegramConnectDialog
        open={tgOpen}
        onOpenChange={(o) => {
          setTgOpen(o);
          if (!o) setTgForceRegenerate(false);
        }}
        forceRegenerate={tgForceRegenerate}
      />
    </div>
  );
};

export default Profile;
