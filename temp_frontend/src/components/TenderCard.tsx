import { Heart, ExternalLink, MapPin, Building2, Tag, Clock, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Tender } from '@/types/tender';
import { format, differenceInCalendarDays, startOfDay } from 'date-fns';
import { ru } from 'date-fns/locale';

const safeDate = (s: string | null | undefined): Date => {
  if (!s) return new Date();
  const d = new Date(s);
  return isNaN(d.getTime()) ? new Date() : d;
};

interface TenderCardProps {
  tender: Tender;
  onToggleFavorite: (id: string) => void;
  onMarkViewed: (id: string) => void;
  onOpenDetail: (tender: Tender) => void;
  isPro?: boolean;
}

export const TenderCard = ({ tender, onToggleFavorite, onMarkViewed, onOpenDetail, isPro = false }: TenderCardProps) => {
  const deadlineDate = safeDate(tender.deadline);
  const today = startOfDay(new Date());
  const deadlineDay = startOfDay(deadlineDate);
  const daysUntilDeadline = differenceInCalendarDays(deadlineDay, today);
  const isUrgent = daysUntilDeadline > 0 && daysUntilDeadline <= 3;
  const isExpiringSoon = daysUntilDeadline > 3 && daysUntilDeadline <= 7;

  const formatBudget = (budget: number | null) => {
    if (budget === null || budget <= 0) {
      return 'Цена не указана';
    }
    if (budget >= 1_000_000_000) {
      const v = budget / 1_000_000_000;
      return `${v.toFixed(1)} млрд ₽`.replace('.0 ', ' ');
    }
    if (budget >= 1_000_000) {
      const v = budget / 1_000_000;
      return `${v.toFixed(1)} млн ₽`.replace('.0 ', ' ');
    }
    if (budget >= 1_000) {
      return `${Math.round(budget / 1000)} тыс ₽`;
    }
    return `${budget} ₽`;
  };

  const handleClick = () => {
    if (!tender.isViewed) {
      onMarkViewed(tender.id);
    }
    onOpenDetail(tender);
  };

  return (
    <Card
      className={`relative overflow-hidden transition-all duration-300 hover:shadow-xl hover:-translate-y-1 group border-border/50 bg-card/50 backdrop-blur-sm ${tender.isViewed ? 'opacity-80' : ''
        }`}
      onClick={handleClick}
    >
      <div className="p-5 flex flex-col gap-4">
        {/* Top Bar: Budget & Source */}
        <div className="flex items-center justify-between">
          <div className="text-xl font-bold bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-transparent">
            {formatBudget(tender.budget)}
          </div>
          <Badge variant="outline" className="bg-background/50 border-primary/20 text-primary text-[10px] font-bold uppercase tracking-widest">
            {tender.source}
          </Badge>
        </div>

        {/* Title */}
        <div className="space-y-2">
          <div className="flex items-start justify-between gap-4">
            <h3 className="font-semibold text-foreground line-clamp-2 leading-tight group-hover:text-primary transition-colors text-base flex-1">
              {tender.title}
            </h3>
            {isPro && tender.relevance != null && (
              <Badge
                variant="secondary"
                className={`shrink-0 flex items-center gap-1 border-0 ${tender.relevance >= 80 ? 'bg-emerald-500/10 text-emerald-600' :
                  tender.relevance >= 65 ? 'bg-amber-500/10 text-amber-600' :
                    'bg-orange-500/10 text-orange-600'
                  }`}
              >
                <Sparkles className="h-3 w-3 fill-current" />
                {tender.relevance}%
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Building2 className="h-3 w-3 shrink-0" />
            <span className="truncate">{tender.customer}</span>
          </div>
          {isPro && tender.relevance != null && (
            <div className="mt-2 rounded-md border border-primary/15 bg-primary/5 px-2.5 py-2 space-y-1">
              <div className="text-[10px] font-semibold uppercase tracking-wide text-primary/90">
                Обоснование
              </div>
              <p className="text-xs text-foreground/90 leading-snug line-clamp-3">
                {tender.relevanceReason?.trim()
                  ? tender.relevanceReason
                  : 'Закупка отобрана по вашему описанию компании; пояснение от модели временно недоступно.'}
              </p>
            </div>
          )}
        </div>

        {/* Badges & Meta */}
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="bg-secondary/50 text-secondary-foreground text-[10px] py-0 px-2">
            <MapPin className="h-3 w-3 mr-1" />
            {tender.region}
          </Badge>
          <Badge variant="secondary" className="bg-secondary/50 text-secondary-foreground text-[10px] py-0 px-2">
            <Tag className="h-3 w-3 mr-1" />
            {tender.category}
          </Badge>
        </div>

        {/* Bottom Section: Deadline & Action */}
        <div className="flex items-center justify-between pt-4 mt-auto border-t border-border/40">
          <div className="flex flex-col">
            <div className={`flex items-center gap-1.5 text-xs font-bold ${isUrgent ? 'text-destructive' : isExpiringSoon ? 'text-orange-500' : 'text-emerald-600'
              }`}>
              <Clock className="h-3.5 w-3.5" />
              {format(deadlineDate, 'd MMMM', { locale: ru })}
            </div>
            <span className="text-[10px] text-muted-foreground mt-0.5">
              {daysUntilDeadline > 0
                ? `Осталось ${daysUntilDeadline} дн.`
                : daysUntilDeadline === 0
                  ? 'Завершается сегодня'
                  : 'Срок истёк'}
            </span>
          </div>

          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className={`h-8 w-8 rounded-full ${tender.isFavorite ? 'text-accent fill-accent hover:text-accent/80' : 'text-muted-foreground hover:text-accent'}`}
              onClick={(e) => {
                e.stopPropagation();
                onToggleFavorite(tender.id);
              }}
            >
              <Heart className="h-4 w-4" />
            </Button>
            <div className="h-8 w-8 rounded-full flex items-center justify-center bg-primary/5 text-primary group-hover:bg-primary group-hover:text-white transition-all">
              <ExternalLink className="h-3.5 w-3.5" />
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
};
