import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp';
import { toast } from 'sonner';

const VerifyEmailCode = () => {
    const [code, setCode] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const submit = async () => {
        if (code.length !== 6) {
            toast.error('Введите 6-значный код из письма');
            return;
        }
        const token = localStorage.getItem('access_token');
        if (!token) {
            toast.error('Сессия истекла — войдите снова');
            navigate('/auth');
            return;
        }
        setLoading(true);
        try {
            const res = await fetch('/api/verify-email-code', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ code }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                const msg =
                    typeof data.detail === 'string'
                        ? data.detail
                        : Array.isArray(data.detail)
                          ? data.detail.map((e: { msg?: string } | string) =>
                              typeof e === 'string' ? e : (e.msg || JSON.stringify(e)),
                            ).join('; ')
                          : 'Неверный код';
                throw new Error(msg);
            }
            toast.success('Email подтверждён');
            navigate('/app');
        } catch (err: unknown) {
            toast.error(err instanceof Error ? err.message : 'Ошибка');
        } finally {
            setLoading(false);
        }
    };

    const resend = async () => {
        const token = localStorage.getItem('access_token');
        if (!token) {
            navigate('/auth');
            return;
        }
        setLoading(true);
        try {
            const res = await fetch('/api/resend-verification-code', {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                const msg =
                    typeof data.detail === 'string'
                        ? data.detail
                        : 'Не удалось отправить письмо';
                throw new Error(msg);
            }
            toast.success('Код отправлен повторно');
        } catch (err: unknown) {
            toast.error(err instanceof Error ? err.message : 'Ошибка');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center p-4 bg-background">
            <Card className="w-full max-w-md">
                <CardHeader className="text-center">
                    <CardTitle className="text-2xl font-bold">Подтверждение email</CardTitle>
                    <CardDescription>
                        Мы отправили 6-значный код на вашу почту. Введите его ниже.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    <div className="flex justify-center">
                        <InputOTP maxLength={6} value={code} onChange={setCode}>
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
                    <Button className="w-full" disabled={loading} onClick={() => void submit()}>
                        {loading ? 'Проверка...' : 'Подтвердить'}
                    </Button>
                    <Button
                        type="button"
                        variant="outline"
                        className="w-full"
                        disabled={loading}
                        onClick={() => void resend()}
                    >
                        Отправить код ещё раз
                    </Button>
                </CardContent>
                <CardFooter className="flex flex-col gap-2">
                    <Link to="/auth" className="text-sm text-muted-foreground hover:text-primary text-center">
                        На страницу входа
                    </Link>
                </CardFooter>
            </Card>
        </div>
    );
};

export default VerifyEmailCode;
