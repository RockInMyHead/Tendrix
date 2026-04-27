import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const VerifyEmail = () => {
    const [searchParams] = useSearchParams();
    const token = searchParams.get('token');
    const navigate = useNavigate();
    const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
    const [message, setMessage] = useState('');

    useEffect(() => {
        if (!token) {
            setStatus('error');
            setMessage('Токен верификации не указан');
            return;
        }
        fetch(`/api/verify-email?token=${encodeURIComponent(token)}`)
            .then(async (res) => {
                const data = await res.json().catch(() => ({}));
                if (res.ok) {
                    setStatus('success');
                    setMessage(data.message || 'Email подтверждён');
                } else {
                    setStatus('error');
                    setMessage(data.detail || 'Недействительный или устаревший токен');
                }
            })
            .catch(() => {
                setStatus('error');
                setMessage('Ошибка сети');
            });
    }, [token]);

    return (
        <div className="min-h-screen flex items-center justify-center p-4 bg-background">
            <Card className="w-full max-w-md">
                <CardHeader className="text-center">
                    <CardTitle className="text-2xl font-bold">Tendrix</CardTitle>
                    <CardDescription>
                        {status === 'loading' && 'Подтверждение email...'}
                        {status === 'success' && 'Email подтверждён'}
                        {status === 'error' && 'Ошибка верификации'}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {status === 'loading' && (
                        <div className="flex justify-center py-4">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                        </div>
                    )}
                    {status === 'success' && (
                        <p className="text-center text-muted-foreground">
                            {message}. Теперь вы можете войти в систему.
                        </p>
                    )}
                    {status === 'error' && (
                        <p className="text-center text-destructive">
                            {message}
                        </p>
                    )}
                </CardContent>
                <CardFooter className="flex flex-col gap-2">
                    {status === 'success' && (
                        <Button className="w-full" onClick={() => navigate('/auth')}>
                            Войти
                        </Button>
                    )}
                    {status === 'error' && (
                        <Button variant="outline" className="w-full" onClick={() => navigate('/auth')}>
                            На страницу входа
                        </Button>
                    )}
                    <Link to="/" className="text-sm text-muted-foreground hover:text-primary text-center">
                        На главную
                    </Link>
                </CardFooter>
            </Card>
        </div>
    );
};

export default VerifyEmail;
