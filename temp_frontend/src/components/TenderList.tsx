import { useEffect, useRef, useCallback } from 'react';
import { Tender } from '@/types/tender';
import { TenderCard } from './TenderCard';
import { EmptyState } from './EmptyState';

interface TenderListProps {
  tenders: Tender[];
  onToggleFavorite: (id: string) => void;
  onMarkViewed: (id: string) => void;
  onOpenDetail: (tender: Tender) => void;
  showFavorites: boolean;
  onClearFilters: () => void;
  onLoadMore?: () => void;
  hasMore?: boolean;
  isLoadingMore?: boolean;
  isPro?: boolean;
  isLoading?: boolean;
  isAiSearch?: boolean;
}

export const TenderList = ({
  tenders,
  onToggleFavorite,
  onMarkViewed,
  onOpenDetail,
  showFavorites,
  onClearFilters,
  onLoadMore,
  hasMore = false,
  isLoadingMore = false,
  isPro = false,
  isLoading = false,
  isAiSearch = false,
}: TenderListProps) => {
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!onLoadMore || !hasMore || isLoadingMore) return;
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) onLoadMore();
      },
      { rootMargin: '200px', threshold: 0.1 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [onLoadMore, hasMore, isLoadingMore]);

  if (isLoading && tenders.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 px-4 text-center animate-fade-in">
        <div className="h-12 w-12 rounded-full border-2 border-primary border-t-transparent animate-spin mb-6" />
        <p className="text-foreground font-medium mb-2">Синхронизация данных...</p>
        {isAiSearch ? (
          <p className="text-sm text-muted-foreground max-w-md leading-relaxed">
            Подбираем релевантные тендеры по описанию компании. Поиск и фильтры выше остаются доступны — дождитесь окончания анализа.
          </p>
        ) : (
          <p className="text-sm text-muted-foreground max-w-md">Загрузка списка тендеров...</p>
        )}
      </div>
    );
  }

  if (tenders.length === 0) {
    return (
      <EmptyState
        type={showFavorites ? 'no-favorites' : 'no-results'}
        onClearFilters={!showFavorites ? onClearFilters : undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
        {tenders.map((tender, index) => (
          <div
            key={tender.id}
            className="animate-slide-up"
            style={{ animationDelay: `${Math.min(index, 20) * 50}ms` }}
          >
            <TenderCard
              tender={tender}
              onToggleFavorite={onToggleFavorite}
              onMarkViewed={onMarkViewed}
              onOpenDetail={onOpenDetail}
              isPro={isPro}
            />
          </div>
        ))}
      </div>
      {hasMore && (
        <div ref={sentinelRef} className="flex justify-center py-8">
          {isLoadingMore && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <span className="h-4 w-4 rounded-full border-2 border-primary border-t-transparent animate-spin" />
              Загрузка...
            </div>
          )}
        </div>
      )}
    </div>
  );
};
