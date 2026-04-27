import { useState } from 'react';
import { X, Heart, ExternalLink, Calendar, MapPin, Building2, Tag, Clock, FileText, Sparkles, AlertCircle, ChevronRight, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tender } from '@/types/tender';
import { format, differenceInCalendarDays, startOfDay } from 'date-fns';
import { ru } from 'date-fns/locale';

const safeDate = (s: string | null | undefined): Date => {
  if (!s) return new Date();
  const d = new Date(s);
  return isNaN(d.getTime()) ? new Date() : d;
};

interface TenderDetailProps {
  tender: Tender;
  onClose: () => void;
  onToggleFavorite: (id: string) => void;
  isPro?: boolean;
}


export const TenderDetail = ({ tender, onClose, onToggleFavorite, isPro = false }: TenderDetailProps) => {
  const [pitfalls, setPitfalls] = useState<string | null>(null);
  const [loadingPitfalls, setLoadingPitfalls] = useState(false);
  const deadlineDate = safeDate(tender.deadline);
  const today = startOfDay(new Date());
  const deadlineDay = startOfDay(deadlineDate);
  const daysUntilDeadline = differenceInCalendarDays(deadlineDay, today);

  const fetchPitfalls = async () => {
    setLoadingPitfalls(true);
    try {
      const token = localStorage.getItem('access_token');
      const params = new URLSearchParams();
      params.set('refresh', 'true');
      if (tender.sourceUrl?.trim()) {
        params.set('link', tender.sourceUrl.trim());
      }
      const q = params.toString();
      const response = await fetch(
        `/api/tenders/${tender.id}/pitfalls${q ? `?${q}` : ''}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );
      const data = await response.json();
      if (data.pitfalls) {
        setPitfalls(data.pitfalls);
      }
    } catch (error) {
      console.error('Error fetching pitfalls:', error);
    } finally {
      setLoadingPitfalls(false);
    }
  };

  const isUrgent = daysUntilDeadline > 0 && daysUntilDeadline <= 3;

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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/20 backdrop-blur-sm animate-fade-in">
      <div
        className="absolute inset-0"
        onClick={onClose}
      />

      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-auto bg-card rounded-xl shadow-lg border border-border animate-scale-in">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between p-4 border-b border-border bg-card">
          <div className="flex items-center gap-2">
            <Badge variant="outline">{tender.source}</Badge>
            {isUrgent && (
              <Badge variant="destructive">Срочно</Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onToggleFavorite(tender.id)}
            >
              <Heart
                className={`h-5 w-5 ${tender.isFavorite ? 'fill-accent text-accent' : ''
                  }`}
              />
            </Button>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-5 w-5" />
            </Button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          <div>
            <h2 className="text-xl font-semibold text-foreground mb-2">
              {tender.title}
            </h2>
            <div className="flex items-center gap-2 text-muted-foreground">
              <Building2 className="h-4 w-4" />
              <span>{tender.customer}</span>
            </div>
          </div>

          {/* Key Info Grid */}
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 rounded-lg bg-secondary/50">
              <div className="text-sm text-muted-foreground mb-1">Начальная цена</div>
              <div className="text-2xl font-bold text-foreground">
                {formatBudget(tender.budget)}
              </div>
            </div>

            <div className={`p-4 rounded-lg ${isUrgent ? 'bg-destructive/10' : 'bg-secondary/50'}`}>
              <div className="text-sm text-muted-foreground mb-1">Срок подачи</div>
              <div className={`text-2xl font-bold ${isUrgent ? 'text-destructive' : 'text-foreground'}`}>
                {format(deadlineDate, 'd MMMM yyyy', { locale: ru })}
              </div>
              <div className="text-sm text-muted-foreground">
                {daysUntilDeadline > 0 ? `Осталось ${daysUntilDeadline} дн.` : daysUntilDeadline === 0 ? 'Завершается сегодня' : 'Срок истёк'}
              </div>
            </div>
          </div>

          {/* Details */}
          <div className="space-y-3">
            <div className="flex items-center gap-3 text-sm">
              <MapPin className="h-4 w-4 text-muted-foreground" />
              <span className="text-muted-foreground">Регион:</span>
              <span className="font-medium">{tender.region}</span>
            </div>

            <div className="flex items-center gap-3 text-sm">
              <Tag className="h-4 w-4 text-muted-foreground" />
              <span className="text-muted-foreground">Категория:</span>
              <span className="font-medium">{tender.category}</span>
            </div>

            <div className="flex items-center gap-3 text-sm">
              <FileText className="h-4 w-4 text-muted-foreground" />
              <span className="text-muted-foreground">Тип закупки:</span>
              <span className="font-medium">{tender.procurementType}</span>
            </div>

            {/* Дата публикации: API возвращает только срок подачи. Реальная дата публикации недоступна для большинства источников. */}
          </div>

          {/* AI Analysis — только для Pro */}
          {isPro && tender.relevance != null && (
            <div className="p-4 rounded-xl bg-gradient-to-r from-amber-500/10 via-orange-500/10 to-amber-500/10 border border-amber-500/20 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-amber-600 font-bold text-sm uppercase tracking-wider">
                  <Sparkles className="h-4 w-4 fill-current" />
                  AI Анализ соответствия
                </div>
                <Badge className="bg-amber-500 text-white border-0">
                  {tender.relevance}%
                </Badge>
              </div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-700/90 mb-1">
                Обоснование
              </div>
              <p className="text-foreground text-sm leading-relaxed">
                {tender.relevanceReason?.trim()
                  ? tender.relevanceReason
                  : 'Закупка отобрана по вашему описанию компании; пояснение от модели временно недоступно.'}
              </p>
            </div>
          )}
          {/* Risk Analysis Section */}
          <div className="space-y-4">
            {!pitfalls && !loadingPitfalls ? (
              <Button
                variant="outline"
                className="w-full py-8 border-dashed border-2 hover:border-primary/50 hover:bg-primary/5 transition-all group"
                onClick={fetchPitfalls}
              >
                <div className="flex flex-col items-center gap-2">
                  <div className="flex items-center gap-2 text-primary font-semibold">
                    <AlertCircle className="h-5 w-5" />
                    Найти подводные камни
                  </div>
                  <div className="text-xs text-muted-foreground group-hover:text-muted-foreground/80 flex items-center gap-1">
                    Глубокий AI-анализ всех вкладок тендера <ChevronRight className="h-3 w-3" />
                  </div>
                </div>
              </Button>
            ) : (
              <div className={`p-5 rounded-xl border transition-all duration-500 ${loadingPitfalls ? 'bg-secondary/30 border-border animate-pulse' : 'bg-red-500/5 border-red-500/20'
                }`}>
                <div className={`flex items-center gap-2 text-sm font-bold uppercase tracking-wider mb-3 ${loadingPitfalls ? 'text-muted-foreground' : 'text-red-600'
                  }`}>
                  {loadingPitfalls ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Анализируем 6 разделов тендера...
                    </>
                  ) : (
                    <>
                      <AlertCircle className="h-4 w-4" />
                      Подводные камни и риски
                    </>
                  )}
                </div>

                {loadingPitfalls ? (
                  <div className="space-y-2">
                    <div className="h-4 bg-muted rounded w-3/4"></div>
                    <div className="h-4 bg-muted rounded w-1/2"></div>
                  </div>
                ) : (
                  <div className="text-sm text-foreground leading-relaxed whitespace-pre-line prose prose-sm max-w-none prose-p:my-1">
                    {pitfalls}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Description */}
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-2">Описание тендера</h3>
            <p className="text-foreground leading-relaxed whitespace-pre-line">
              {tender.title}
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 p-4 border-t border-border bg-card">
          <Button
            className="w-full gap-2"
            size="lg"
            onClick={() => window.open(tender.sourceUrl, '_blank')}
          >
            <ExternalLink className="h-4 w-4" />
            Открыть на {tender.source}
          </Button>
        </div>
      </div>
    </div>
  );
};
