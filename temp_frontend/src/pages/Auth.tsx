import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Checkbox } from '@/components/ui/checkbox';
import { toast } from 'sonner';

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
    const navigate = useNavigate();

    const handleAuth = async (isLogin: boolean) => {
        if (!isLogin) {
            if (!email?.trim()) {
                toast.error('Укажите email для регистрации');
                return;
            }
            if (password !== passwordRepeat) {
                toast.error('Пароли не совпадают');
                return;
            }
            if (!offer || !privacy || !personalData) {
                toast.error('Необходимо принять обязательные условия');
                return;
            }
        }
        setIsLoading(true);
        try {
            let url, body, headers;

            if (isLogin) {
                url = '/token';
                const formData = new URLSearchParams();
                formData.append('username', username);
                formData.append('password', password);
                body = formData;
                headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
            } else {
                url = '/register';
                body = JSON.stringify({ username, password, email: email.trim() });
                headers = { 'Content-Type': 'application/json' };
            }

            const response = await fetch(url, {
                method: 'POST',
                headers: headers,
                body: body
            });

            const data = await response.json();

            if (!response.ok) {
                const errMsg = Array.isArray(data.detail)
                    ? data.detail.map((e: { msg?: string } | string) => typeof e === 'string' ? e : (e.msg || JSON.stringify(e))).join('; ')
                    : (typeof data.detail === 'string' ? data.detail : (data.detail?.msg || 'Ошибка авторизации'));
                throw new Error(errMsg);
            }

            localStorage.setItem('access_token', data.access_token);
            if (isLogin) {
                toast.success('Вход выполнен');
                navigate('/app');
            } else {
                toast.success(data.email_sent
                    ? 'Регистрация успешна. На почту отправлен код подтверждения'
                    : 'Регистрация успешна. Не удалось отправить письмо — запросите код повторно на странице подтверждения');
                navigate('/verify-email-code');
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
                    <Tabs defaultValue="login" className="w-full">
                        <TabsList className="grid w-full grid-cols-2">
                            <TabsTrigger value="login">Вход</TabsTrigger>
                            <TabsTrigger value="register">Регистрация</TabsTrigger>
                        </TabsList>
                        <TabsContent value="login">
                            <form onSubmit={(e) => { e.preventDefault(); handleAuth(true); }} className="space-y-4 pt-4">
                                <div className="space-y-2">
                                    <Label htmlFor="login-username">Логин</Label>
                                    <Input
                                        id="login-username"
                                        placeholder="admin"
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
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        required
                                    />
                                </div>
                                <Button type="submit" className="w-full" disabled={isLoading}>
                                    {isLoading ? "Загрузка..." : "Войти"}
                                </Button>
                            </form>
                        </TabsContent>
                        <TabsContent value="register">
                            <form onSubmit={(e) => { e.preventDefault(); handleAuth(false); }} className="space-y-4 pt-4">
                                <div className="space-y-2">
                                    <Label htmlFor="reg-username">Логин</Label>
                                    <Input
                                        id="reg-username"
                                        placeholder="Новый пользователь"
                                        value={username}
                                        onChange={(e) => setUsername(e.target.value)}
                                        required
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="reg-email">Почта <span className="text-destructive">*</span></Label>
                                    <Input
                                        id="reg-email"
                                        type="email"
                                        placeholder="example@mail.ru"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        required
                                    />
                                    <p className="text-xs text-muted-foreground">На почту придёт ссылка для подтверждения</p>
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="reg-password">Пароль</Label>
                                    <Input
                                        id="reg-password"
                                        type="password"
                                        placeholder="••••••••"
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
                                        value={passwordRepeat}
                                        onChange={(e) => setPasswordRepeat(e.target.value)}
                                        required
                                    />
                                </div>

                                <div className="space-y-3 pt-2">
                                    <div className="flex items-start gap-2">
                                        <Checkbox
                                            id="offer"
                                            checked={offer}
                                            onCheckedChange={(c) => setOffer(!!c)}
                                        />
                                        <Label htmlFor="offer" className="text-sm cursor-pointer leading-tight">
                                            Принимаю условия оферты
                                        </Label>
                                    </div>
                                    <div className="flex items-start gap-2">
                                        <Checkbox
                                            id="privacy"
                                            checked={privacy}
                                            onCheckedChange={(c) => setPrivacy(!!c)}
                                        />
                                        <Label htmlFor="privacy" className="text-sm cursor-pointer leading-tight">
                                            Согласен и принимаю политику конфиденциальности
                                        </Label>
                                    </div>
                                    <div className="flex items-start gap-2">
                                        <Checkbox
                                            id="personalData"
                                            checked={personalData}
                                            onCheckedChange={(c) => setPersonalData(!!c)}
                                        />
                                        <Label htmlFor="personalData" className="text-sm cursor-pointer leading-tight">
                                            Даю согласие на обработку персональных данных
                                        </Label>
                                    </div>
                                    <div className="flex items-start gap-2">
                                        <Checkbox
                                            id="marketing"
                                            checked={marketing}
                                            onCheckedChange={(c) => setMarketing(!!c)}
                                        />
                                        <Label htmlFor="marketing" className="text-sm cursor-pointer leading-tight text-muted-foreground">
                                            Согласен получать рекламные предложения
                                        </Label>
                                    </div>
                                </div>

                                <Button type="submit" className="w-full" disabled={isLoading}>
                                    {isLoading ? "Загрузка..." : "Зарегистрироваться"}
                                </Button>
                            </form>
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
