import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Checkbox } from '@/components/ui/checkbox';
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp';
import { toast } from 'sonner';

const REG_TOKEN_KEY = 'tendrix_reg_completion_token';
const REG_EMAIL_KEY = 'tendrix_reg_email';

const Auth = () => {
    const [isLoading, setIsLoading] = useState(false);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [passwordRepeat, setPasswordRepeat] = useState('');
    const [email, setEmail] = useState('');
    const [offer, setOffer] = useState(false);
    const [privacy, setPrivacy] = useState(false);
    const [personalData, setPersonalData] = useState(false);
    const [marketing, setMarketing] = useState(false);
    const [regStep, setRegStep] = useState<1 | 2 | 3>(1);
    const [verifyCode, setVerifyCode] = useState('');
    const [completionToken, setCompletionToken] = useState('');
    const navigate = useNavigate();

    useEffect(() => {
        const t = sessionStorage.getItem(REG_TOKEN_KEY);
        const e = sessionStorage.getItem(REG_EMAIL_KEY);
        if (t && e) {
            setCompletionToken(t);
            setEmail(e);
            setRegStep(3);
        }
    }, []);

    const clearRegSession = () => {
        sessionStorage.removeItem(REG_TOKEN_KEY);
        sessionStorage.removeItem(REG_EMAIL_KEY);
        setCompletionToken('');
        setVerifyCode('');
        setRegStep(1);
    };

    const handleLogin = async () => {
        setIsLoading(true);
        try {
            const formData = new URLSearchParams();
            formData.append('username', username);
            formData.append('password', password);
            const response = await fetch('/token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData,
            });
            const data = await response.json();
            if (!response.ok) {
                const errMsg = Array.isArray(data.detail)
                    ? data.detail.map((x: { msg?: string } | string) => typeof x === 'string' ? x : (x.msg || JSON.stringify(x))).join('; ')
                    : (typeof data.detail === 'string' ? data.detail : (data.detail?.msg || 'Ошибка авторизации'));
                throw new Error(errMsg);
            }
            localStorage.setItem('access_token', data.access_token);
            toast.success('Вход выполнен');
            navigate('/app');
        } catch (err: unknown) {
            toast.error(err instanceof Error ? err.message : 'Ошибка');
        } finally {
            setIsLoading(false);
        }
    };

    const handleRequestCode = async () => {
        const em = email?.trim();
        if (!em) {
            toast.error('Укажите email');
            return;
        }
        setIsLoading(true);
        try {
            const res = await fetch('/api/register/request-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: em }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                const msg = typeof data.detail === 'string' ? data.detail : 'Не удалось отправить код';
                throw new Error(msg);
            }
            if (data.email_sent) {
                toast.success('Код отправлен на почту');
                setRegStep(2);
            } else {
                toast.error('Письмо не отправлено — проверьте настройки почты на сервере');
            }
        } catch (err: unknown) {
            toast.error(err instanceof Error ? err.message : 'Ошибка');
        } finally {
            setIsLoading(false);
        }
    };

    const handleVerifyCode = async () => {
        if (verifyCode.length !== 6) {
            toast.error('Введите 6-значный код');
            return;
        }
        setIsLoading(true);
        try {
            const res = await fetch('/api/register/verify-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email.trim(), code: verifyCode }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                const msg = typeof data.detail === 'string' ? data.detail : 'Неверный код';
                throw new Error(msg);
            }
            const token = data.completion_token as string;
            setCompletionToken(token);
            sessionStorage.setItem(REG_TOKEN_KEY, token);
            sessionStorage.setItem(REG_EMAIL_KEY, email.trim());
            toast.success('Email подтверждён — задайте логин и пароль');
            setRegStep(3);
        } catch (err: unknown) {
            toast.error(err instanceof Error ? err.message : 'Ошибка');
        } finally {
            setIsLoading(false);
        }
    };

    const handleRegisterComplete = async (e: React.FormEvent) => {
        e.preventDefault();
        if (password !== passwordRepeat) {
            toast.error('Пароли не совпадают');
            return;
        }
        if (!offer || !privacy || !personalData) {
            toast.error('Необходимо принять обязательные условия');
            return;
        }
        if (!completionToken) {
            toast.error('Сессия регистрации истекла — начните заново');
            clearRegSession();
            return;
        }
        setIsLoading(true);
        try {
            const response = await fetch('/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: username.trim(),
                    password,
                    completion_token: completionToken,
                }),
            });
            const data = await response.json();
            if (!response.ok) {
                const errMsg = Array.isArray(data.detail)
                    ? data.detail.map((x: { msg?: string } | string) => typeof x === 'string' ? x : (x.msg || JSON.stringify(x))).join('; ')
                    : (typeof data.detail === 'string' ? data.detail : (data.detail?.msg || 'Ошибка регистрации'));
                throw new Error(errMsg);
            }
            localStorage.setItem('access_token', data.access_token);
            clearRegSession();
            toast.success('Регистрация завершена');
            navigate('/app');
        } catch (err: unknown) {
            toast.error(err instanceof Error ? err.message : 'Ошибка');
        } finally {
            setIsLoading(false);
        }
    };

    const resendCode = async () => {
        const em = email?.trim();
        if (!em) return;
        setIsLoading(true);
        try {
            const res = await fetch('/api/register/request-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: em }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(typeof data.detail === 'string' ? data.detail : 'Ошибка');
            }
            if (data.email_sent) {
                toast.success('Код отправлен повторно');
            } else {
                toast.error('Не удалось отправить письмо');
            }
        } catch (err: unknown) {
            toast.error(err instanceof Error ? err.message : 'Ошибка');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center p-4 bg-background">
            <Card className="w-full max-w-md">
                <CardHeader className="text-center">
                    <CardTitle className="text-2xl font-bold">Tendrix</CardTitle>
                    <CardDescription>
                        Войдите в систему для доступа к тендерам
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Tabs
                        defaultValue="login"
                        className="w-full"
                        onValueChange={(v) => {
                            if (v === 'register') {
                                if (!sessionStorage.getItem(REG_TOKEN_KEY)) {
                                    setRegStep(1);
                                    setVerifyCode('');
                                }
                            }
                        }}
                    >
                        <TabsList className="grid w-full grid-cols-2">
                            <TabsTrigger value="login">Вход</TabsTrigger>
                            <TabsTrigger value="register">Регистрация</TabsTrigger>
                        </TabsList>
                        <TabsContent value="login">
                            <form onSubmit={(e) => { e.preventDefault(); void handleLogin(); }} className="space-y-4 pt-4">
                                <div className="space-y-2">
                                    <Label htmlFor="login-username">Логин</Label>
                                    <Input
                                        id="login-username"
                                        placeholder="admin"
                                        autoComplete="username"
                                        value={username}
                                        onChange={(e) => setUsername(e.target.value)}
                                        required
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="login-password">Пароль</Label>
                                    <Input
                                        id="login-password"
                                        type="password"
                                        placeholder="••••••••"
                                        autoComplete="current-password"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        required
                                    />
                                </div>
                                <Button type="submit" className="w-full" disabled={isLoading}>
                                    {isLoading ? 'Загрузка...' : 'Войти'}
                                </Button>
                            </form>
                        </TabsContent>
                        <TabsContent value="register">
                            {regStep === 1 && (
                                <div className="space-y-4 pt-4">
                                    <p className="text-sm text-muted-foreground">
                                        Сначала подтвердите email: мы отправим код на почту, затем вы зададите логин и пароль.
                                    </p>
                                    <div className="space-y-2">
                                        <Label htmlFor="reg-email">Почта <span className="text-destructive">*</span></Label>
                                        <Input
                                            id="reg-email"
                                            type="email"
                                            placeholder="example@mail.ru"
                                            autoComplete="email"
                                            value={email}
                                            onChange={(e) => setEmail(e.target.value)}
                                            required
                                        />
                                    </div>
                                    <Button type="button" className="w-full" disabled={isLoading} onClick={() => void handleRequestCode()}>
                                        {isLoading ? 'Отправка...' : 'Получить код на почту'}
                                    </Button>
                                </div>
                            )}

                            {regStep === 2 && (
                                <div className="space-y-4 pt-4">
                                    <p className="text-sm text-muted-foreground text-center">
                                        Код отправлен на <span className="font-medium text-foreground">{email}</span>
                                    </p>
                                    <div className="flex justify-center">
                                        <InputOTP maxLength={6} value={verifyCode} onChange={setVerifyCode}>
                                            <InputOTPGroup>
                                                <InputOTPSlot index={0} />
                                                <InputOTPSlot index={1} />
                                                <InputOTPSlot index={2} />
                                                <InputOTPSlot index={3} />
                                                <InputOTPSlot index={4} />
                                                <InputOTPSlot index={5} />
                                            </InputOTPGroup>
                                        </InputOTP>
                                    </div>
                                    <Button type="button" className="w-full" disabled={isLoading} onClick={() => void handleVerifyCode()}>
                                        {isLoading ? 'Проверка...' : 'Подтвердить код'}
                                    </Button>
                                    <Button type="button" variant="outline" className="w-full" disabled={isLoading} onClick={() => void resendCode()}>
                                        Отправить код ещё раз
                                    </Button>
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        className="w-full text-muted-foreground"
                                        onClick={() => { setRegStep(1); setVerifyCode(''); }}
                                    >
                                        Изменить email
                                    </Button>
                                </div>
                            )}

                            {regStep === 3 && (
                                <form onSubmit={handleRegisterComplete} className="space-y-4 pt-4">
                                    <p className="text-sm text-emerald-600 dark:text-emerald-400 text-center">
                                        Email подтверждён. Завершите регистрацию.
                                    </p>
                                    <div className="space-y-2">
                                        <Label htmlFor="reg-username">Логин</Label>
                                        <Input
                                            id="reg-username"
                                            placeholder="Новый пользователь"
                                            autoComplete="username"
                                            value={username}
                                            onChange={(e) => setUsername(e.target.value)}
                                            required
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="reg-password">Пароль</Label>
                                        <Input
                                            id="reg-password"
                                            type="password"
                                            placeholder="••••••••"
                                            autoComplete="new-password"
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                            required
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="reg-password-repeat">Повторите пароль</Label>
                                        <Input
                                            id="reg-password-repeat"
                                            type="password"
                                            placeholder="••••••••"
                                            autoComplete="new-password"
                                            value={passwordRepeat}
                                            onChange={(e) => setPasswordRepeat(e.target.value)}
                                            required
                                        />
                                    </div>

                                    <div className="space-y-3 pt-2">
                                        <div className="flex items-start gap-2">
                                            <Checkbox id="offer" checked={offer} onCheckedChange={(c) => setOffer(!!c)} />
                                            <Label htmlFor="offer" className="text-sm cursor-pointer leading-tight">
                                                Принимаю{" "}
                                                <a
                                                    href="/legal/offer-user-agreement.pdf"
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="underline underline-offset-4 hover:text-primary"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    условия оферты / пользовательского соглашения
                                                </a>
                                            </Label>
                                        </div>
                                        <div className="flex items-start gap-2">
                                            <Checkbox id="privacy" checked={privacy} onCheckedChange={(c) => setPrivacy(!!c)} />
                                            <Label htmlFor="privacy" className="text-sm cursor-pointer leading-tight">
                                                Согласен и принимаю{" "}
                                                <a
                                                    href="/legal/privacy-policy.pdf"
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="underline underline-offset-4 hover:text-primary"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    политику конфиденциальности
                                                </a>
                                            </Label>
                                        </div>
                                        <div className="flex items-start gap-2">
                                            <Checkbox id="personalData" checked={personalData} onCheckedChange={(c) => setPersonalData(!!c)} />
                                            <Label htmlFor="personalData" className="text-sm cursor-pointer leading-tight">
                                                Даю согласие на{" "}
                                                <a
                                                    href="/legal/privacy-policy.pdf"
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="underline underline-offset-4 hover:text-primary"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    обработку персональных данных
                                                </a>
                                            </Label>
                                        </div>
                                        <div className="flex items-start gap-2">
                                            <Checkbox id="marketing" checked={marketing} onCheckedChange={(c) => setMarketing(!!c)} />
                                            <Label htmlFor="marketing" className="text-sm cursor-pointer leading-tight text-muted-foreground">
                                                Согласен получать рекламные предложения
                                            </Label>
                                        </div>
                                    </div>

                                    <Button type="submit" className="w-full" disabled={isLoading}>
                                        {isLoading ? 'Загрузка...' : 'Зарегистрироваться'}
                                    </Button>
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        className="w-full text-muted-foreground text-sm"
                                        onClick={() => {
                                            clearRegSession();
                                            setEmail('');
                                        }}
                                    >
                                        Начать регистрацию заново
                                    </Button>
                                </form>
                            )}
                        </TabsContent>
                    </Tabs>
                </CardContent>
                <CardFooter className="flex justify-center">
                    <Link to="/" className="text-sm text-muted-foreground hover:text-primary transition-colors">
                        На главную
                    </Link>
                </CardFooter>
            </Card>
        </div>
    );
};

export default Auth;
