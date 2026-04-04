import { Bell, Heart, Settings, Search, Send, LogOut, Sparkles, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { TelegramConnectDialog } from './TelegramConnectDialog';
import { ProModal } from './ProModal';
import { toast } from 'sonner';

interface HeaderProps {
  favoritesCount: number;
  onShowFavorites: () => void;
  showFavorites: boolean;
  showTgDialog?: boolean;
  onShowTgDialogChange?: (open: boolean) => void;
  isAdmin?: boolean;
}

export const Header = ({ favoritesCount, onShowFavorites, showFavorites, showTgDialog: externalTg, onShowTgDialogChange, isAdmin }: HeaderProps) => {
  const [internalTg, setInternalTg] = useState(false);
  const showTgDialog = externalTg ?? internalTg;
  const setShowTgDialog = onShowTgDialogChange ?? setInternalTg;
  const [showProModal, setShowProModal] = useState(false);
  const [isPro, setIsPro] = useState(false);
  const [loadingPro, setLoadingPro] = useState(false);

  useEffect(() => {
    checkProStatus();
  }, []);

  const checkProStatus = async () => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) return;
      const res = await fetch('/users/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setIsPro(data.is_pro);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleActivatePro = async () => {
    setLoadingPro(true);
    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch('/api/users/me/pro', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        setIsPro(true);
        setShowProModal(false);
        toast.success("Tendrix Pro активирован! AI-анализ теперь доступен.");
      } else {
        toast.error("Ошибка активации Pro");
      }
    } catch (e) {
      console.error(e);
      toast.error("Ошибка соединения");
    } finally {
      setLoadingPro(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    window.location.href = '/auth';
  };

  return (
    <>
      <header className="sticky top-0 z-50 w-full border-b border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80">
        <div className="container flex h-16 items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-2 shrink-0 hover:opacity-80 transition-opacity">
              <div className="h-9 w-9 rounded-xl bg-primary flex items-center justify-center shadow-lg shadow-primary/20">
                <span className="text-primary-foreground font-bold text-xl">T</span>
              </div>
              <span className="text-xl font-bold text-foreground hidden sm:inline-block">Tendrix.io</span>
            </Link>

            {isPro ? (
              <Button
                variant="ghost"
                size="sm"
                type="button"
                className="h-auto py-1 px-2 sm:px-3 gap-1.5 rounded-full bg-gradient-to-r from-amber-400 to-orange-500 text-white border-0 hover:opacity-90 hover:bg-transparent shadow-md"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setShowProModal(true);
                }}
              >
                <Sparkles className="h-3.5 w-3.5 fill-white" />
                <span className="hidden sm:inline">PRO Active</span>
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                className="flex items-center gap-2 border-amber-500/50 text-amber-600 hover:text-amber-700 hover:bg-amber-500/10 hover:border-amber-500 transition-all shadow-sm hover:shadow-amber-500/20 px-2 sm:px-3"
                onClick={() => setShowProModal(true)}
              >
                <Sparkles className="h-4 w-4" />
                <span className="font-bold hidden sm:inline">Tendrix Pro</span>
              </Button>
            )}

            <Button
              variant="ghost"
              size="sm"
              className="flex items-center gap-2 bg-gradient-to-r from-[#0088cc]/10 to-[#229ED9]/10 hover:from-[#0088cc]/20 hover:to-[#229ED9]/20 text-[#0088cc] border border-[#0088cc]/20 rounded-full px-2 sm:px-4"
              onClick={() => setShowTgDialog(true)}
            >
              <Send className="h-4 w-4" />
              <span className="font-medium text-xs uppercase tracking-wider hidden sm:inline">Telegram бот</span>
            </Button>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant={showFavorites ? "default" : "ghost"}
              size="sm"
              onClick={onShowFavorites}
              className="relative gap-2"
            >
              <Heart className={`h-4 w-4 ${showFavorites ? 'fill-current' : ''}`} />
              <span className="hidden md:inline">Избранное</span>
              {favoritesCount > 0 && (
                <Badge
                  variant="secondary"
                  className="h-5 min-w-5 px-1.5 text-[10px] bg-accent text-accent-foreground"
                >
                  {favoritesCount}
                </Badge>
              )}
            </Button>

            {isAdmin && (
              <Link to="/admin">
                <Button variant="ghost" size="sm" className="gap-2 text-muted-foreground hover:text-foreground">
                  <Shield className="h-4 w-4" />
                  <span className="hidden sm:inline">Админ</span>
                </Button>
              </Link>
            )}
            <Button variant="ghost" size="icon" className="relative hidden sm:flex">
              <Bell className="h-4 w-4" />
              <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-accent border-2 border-card" />
            </Button>

            <Button variant="ghost" size="icon" className="hidden sm:flex" onClick={handleLogout}>
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </header>
      <TelegramConnectDialog open={showTgDialog} onOpenChange={setShowTgDialog} />
      <ProModal
        open={showProModal}
        onOpenChange={setShowProModal}
        isPro={isPro}
        onBuy={handleActivatePro}
        loading={loadingPro}
      />
    </>
  );
};
