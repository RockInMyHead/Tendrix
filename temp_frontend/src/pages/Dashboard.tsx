import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '@/components/Header';
import { TelegramConnectDialog } from '@/components/TelegramConnectDialog';
import { SearchFilters } from '@/components/SearchFilters';
import { TenderList } from '@/components/TenderList';
import { TenderDetail } from '@/components/TenderDetail';
import { useTenders } from '@/hooks/useTenders';
import { Tender } from '@/types/tender';

const Dashboard = () => {
  const navigate = useNavigate();
  const [profileReady, setProfileReady] = useState(false);
  const {
    filteredTenders,
    filters,
    setFilters,
    sortField,
    sortOrder,
    handleSortChange,
    showFavorites,
    setShowFavorites,
    toggleFavorite,
    markViewed,
    clearFilters,
    loadMore,
    hasMore,
    isLoadingMore,
    favoritesCount,
    totalCount,
    isLoading,
  } = useTenders({ searchEnabled: profileReady });

  const [selectedTender, setSelectedTender] = useState<Tender | null>(null);
  const [isPro, setIsPro] = useState(false);
  const [canSaveDescriptionFree, setCanSaveDescriptionFree] = useState(true);
  const [hasTelegramConnected, setHasTelegramConnected] = useState(false);
  const [showTgDialog, setShowTgDialog] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  const fetchUserMe = async () => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        setProfileReady(true);
        return;
      }
      const res = await fetch('/users/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        if (data.email_verified === false && !data.is_admin) {
          navigate('/verify-email-code', { replace: true });
          return;
        }
        setIsPro(data.is_pro);
        setIsAdmin(!!data.is_admin);
        setCanSaveDescriptionFree(data.can_save_description_free !== false);
        setHasTelegramConnected(!!data.telegram_id);
        if (data.company_description?.trim()) {
          setFilters((prev) => {
            if (prev.companyDescription?.trim()) return prev;
            return { ...prev, companyDescription: data.company_description };
          });
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setProfileReady(true);
    }
  };

  useEffect(() => {
    fetchUserMe();
  }, []);

  const handleSaveDescription = async (desc: string, paid299 = false) => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) return;
      const url = `/api/users/me/description${paid299 ? '?paid_299=true' : ''}`;
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ description: desc })
      });
      if (res.ok) {
        setCanSaveDescriptionFree(false);
        import('sonner').then(({ toast }) => toast.success('Описание компании сохранено в профиле'));
      } else {
        const err = await res.json().catch(() => ({}));
        if (res.status === 402 && err.detail?.code === 'SAVE_LIMIT') {
          return { limitReached: true, price: err.detail?.paid_unlock_price ?? 299 };
        }
        throw new Error('Ошибка при сохранении');
      }
    } catch (e) {
      import('sonner').then(({ toast }) => toast.error('Не удалось сохранить описание'));
      throw e;
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Header
        favoritesCount={favoritesCount}
        onShowFavorites={() => setShowFavorites(!showFavorites)}
        showFavorites={showFavorites}
        isAdmin={isAdmin}
        onProActivated={() => setIsPro(true)}
      />
      <TelegramConnectDialog open={showTgDialog} onOpenChange={setShowTgDialog} />

      <main className="container py-6 space-y-6">
        <SearchFilters
          filters={filters}
          onFiltersChange={setFilters}
          sortField={sortField}
          sortOrder={sortOrder}
          onSortChange={handleSortChange}
          totalCount={totalCount}
          filteredCount={filteredTenders.length}
          isPro={isPro}
          canSaveDescriptionFree={canSaveDescriptionFree}
          onSaveDescription={handleSaveDescription}
          isLoading={isLoading}
          hasTelegramConnected={hasTelegramConnected}
          onSubscribeClick={() => setShowTgDialog(true)}
        />

        <TenderList
          tenders={filteredTenders}
          onToggleFavorite={toggleFavorite}
          onMarkViewed={markViewed}
          onOpenDetail={setSelectedTender}
          showFavorites={showFavorites}
          onClearFilters={clearFilters}
          onLoadMore={loadMore}
          hasMore={hasMore}
          isLoadingMore={isLoadingMore}
          isPro={isPro}
          isLoading={isLoading}
          isAiSearch={!!filters.smartSearchMode && isLoading && filteredTenders.length === 0}
        />
      </main>

      {selectedTender && (
        <TenderDetail
          tender={selectedTender}
          onClose={() => setSelectedTender(null)}
          onToggleFavorite={(id) => {
            toggleFavorite(id);
            setSelectedTender(prev => prev ? { ...prev, isFavorite: !prev.isFavorite } : null);
          }}
          isPro={isPro}
        />
      )}
    </div>
  );
};

export default Dashboard;
