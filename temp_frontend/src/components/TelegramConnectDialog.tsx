import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Loader2, Copy, Check } from "lucide-react";
import { useState, useEffect } from "react";
import { QRCodeSVG } from "qrcode.react";

interface TelegramConnectDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export const TelegramConnectDialog = ({ open, onOpenChange }: TelegramConnectDialogProps) => {
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState<{ code: string; link: string } | null>(null);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        if (open && !data) {
            fetchCode();
        }
    }, [open]);

    const fetchCode = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await fetch('/api/users/me/telegram-link', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const json = await res.json();
                setData(json);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const copyCode = () => {
        if (data?.code) {
            navigator.clipboard.writeText(data.code);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>Связь с Telegram</DialogTitle>
                    <DialogDescription>
                        Отсканируйте код или отправьте цифры боту для получения уведомлений.
                    </DialogDescription>
                </DialogHeader>

                <div className="flex flex-col items-center justify-center p-4 space-y-6">
                    {loading ? (
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    ) : data ? (
                        <>
                            <div className="bg-white p-4 rounded-xl shadow-sm border">
                                <QRCodeSVG value={data.link} size={200} />
                            </div>

                            <div className="flex flex-col items-center w-full gap-2">
                                <span className="text-sm text-muted-foreground uppercase tracking-wider font-semibold">Ваш код подключения</span>
                                <div className="flex items-center gap-2 w-full max-w-[240px]">
                                    <div className="flex-1 h-10 bg-muted/50 rounded-lg flex items-center justify-center font-mono text-xl font-bold tracking-widest border">
                                        {data.code}
                                    </div>
                                    <Button size="icon" variant="outline" onClick={copyCode}>
                                        {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                                    </Button>
                                </div>
                            </div>

                            <Button className="w-full" onClick={() => window.open(data.link, '_blank')}>
                                Открыть бота
                            </Button>
                        </>
                    ) : (
                        <div className="text-red-500">Не удалось загрузить код. Попробуйте обновить страницу.</div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
};
