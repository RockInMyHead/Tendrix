import { Search, X, SlidersHorizontal, Clock, Sparkles, Bell } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { TenderFilters, SortField, SortOrder } from '@/types/tender';
import { categories, regions, procurementTypes } from '@/data/filterOptions';
import { useState } from 'react';

interface SearchFiltersProps {
  filters: TenderFilters;
  onFiltersChange: (filters: TenderFilters) => void;
  sortField: SortField;
  sortOrder: SortOrder;
  onSortChange: (field: SortField, order: SortOrder) => void;
  totalCount: number;
  filteredCount: number;
  isPro?: boolean;
  canSaveDescriptionFree?: boolean;
  onSaveDescription?: (desc: string, paid299?: boolean) => Promise<{ limitReached?: boolean; price?: number } | void>;
  isLoading?: boolean;
  hasTelegramConnected?: boolean;
  onSubscribeClick?: () => void;
}

export const SearchFilters = ({
  filters,
  onFiltersChange,
  sortField,
  sortOrder,
  onSortChange,
  totalCount,
  filteredCount,
  isPro = false,
  canSaveDescriptionFree = true,
  onSaveDescription,
  isLoading = false,
  hasTelegramConnected = false,
  onSubscribeClick,
}: SearchFiltersProps) => {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [showPayOption, setShowPayOption] = useState(false);

  const updateFilter = <K extends keyof TenderFilters>(key: K, value: TenderFilters[K]) => {
    const resetPageKeys: (keyof TenderFilters)[] = [
      'search',
      'region',
      'source',
      'budgetFrom',
      'budgetTo',
      'law44',
      'law223',
      'category',
      'procurementType',
      'companyDescription',
    ];
    const resetPage = resetPageKeys.includes(key);
    const resetAi = key !== 'smartSearchMode' && key !== 'companyDescription';
    onFiltersChange({
      ...filters,
      [key]: value,
      ...(resetPage ? { page: 1 } : {}),
      ...(resetAi ? { smartSearchMode: false } : {}),
    });
  };

  const clearFilters = () => {
    onFiltersChange({
      search: '',
      region: '',
      source: 'all',
      budgetFrom: null,
      budgetTo: null,
      category: '',
      procurementType: '',
      hoursAgo: null,
      hideMicroLots: false,
      excludeCategories: [],
      excludeCustomers: [],
      companyDescription: filters.companyDescription,
      law44: true,
      law223: true,
      smartSearchMode: false,
      page: 1,
      recordsPerPage: 50,
    });
  };

  const handleAiSearch = () => {
    if (!filters.companyDescription?.trim()) return;
    onFiltersChange({ ...filters, smartSearchMode: true, page: 1 });
  };

  const hasActiveFilters =
    filters.search ||
    filters.region ||
    (filters.source && filters.source !== 'all') ||
    filters.category ||
    filters.procurementType ||
    filters.budgetFrom !== null ||
    filters.budgetTo !== null ||
    filters.hoursAgo !== null ||
    !filters.law44 ||
    filters.law223 ||
    filters.hideMicroLots;

  const handleSave = async (paid299 = false) => {
    if (!onSaveDescription) return;
    setSaveStatus('saving');
    setShowPayOption(false);
    try {
      const result = await onSaveDescription(filters.companyDescription, paid299);
      if (result?.limitReached) {
        setShowPayOption(true);
        setSaveStatus('idle');
      } else {
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus('idle'), 2000);
      }
    } catch (e) {
      setSaveStatus('idle');
    }
  };

  return (
    <div className="space-y-4">
      {/* AI Section */}
      {isPro && (
        <div className="p-4 rounded-xl bg-gradient-to-r from-amber-500/10 via-orange-500/10 to-amber-500/10 border border-amber-500/20 shadow-sm space-y-3 transition-all">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-amber-600">
              <Sparkles className="h-4 w-4" />
              <h3 className="text-sm font-bold uppercase tracking-wider">AI-Анализ & Умный поиск</h3>
            </div>
          </div>
          <Textarea
            placeholder="Опишите чем занимается ваша компания, что вы ищете? Наш ИИ сам подберет ключевые слова и оценит каждый тендер."
            value={filters.companyDescription}
            onChange={(e) => updateFilter('companyDescription', e.target.value)}
            className="bg-background/50 border-amber-500/20 focus-visible:ring-amber-500/30"
            rows={2}
          />
          <p className="text-xs text-muted-foreground">
            Повторное изменение: 1 раз в месяц бесплатно или за 299 ₽
          </p>
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              size="sm"
              className="bg-amber-500 hover:bg-amber-600 text-white h-8 text-xs font-bold transition-all active:scale-95 disabled:opacity-70"
              onClick={handleAiSearch}
              disabled={!filters.companyDescription?.trim() || isLoading}
            >
              {isLoading && filters.smartSearchMode ? (
                <span className="flex items-center gap-2">
                  <span className="h-3 w-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  AI ищет...
                </span>
              ) : (
                <span className="flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5" />
                  Найти по описанию компании
                </span>
              )}
            </Button>
            {canSaveDescriptionFree ? (
              <Button
                size="sm"
                variant="outline"
                disabled={saveStatus !== 'idle'}
                className="bg-amber-500/10 border-amber-500/30 text-amber-700 hover:bg-amber-500/20 h-8 text-xs font-bold transition-all active:scale-95 disabled:opacity-70"
                onClick={() => handleSave(false)}
              >
                {saveStatus === 'saving' ? (
                  <span className="flex items-center gap-2">
                    <span className="h-3 w-3 border-2 border-amber-700/30 border-t-amber-700 rounded-full animate-spin" />
                    Сохранение...
                  </span>
                ) : saveStatus === 'saved' ? (
                  <span className="flex items-center gap-1 text-emerald-600">
                    Сохранено! ✅
                  </span>
                ) : (
                  'Сохранить в профиль'
                )}
              </Button>
            ) : null}
            {(!canSaveDescriptionFree || showPayOption) && (
              <Button
                size="sm"
                variant="default"
                disabled={saveStatus !== 'idle'}
                className="bg-amber-500 hover:bg-amber-600 text-white h-8 text-xs font-bold transition-all active:scale-95 disabled:opacity-70"
                onClick={() => handleSave(true)}
              >
                {saveStatus === 'saving' ? (
                  <span className="flex items-center gap-2">
                    <span className="h-3 w-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Сохранение...
                  </span>
                ) : (
                  'Сохранить за 299 ₽'
                )}
              </Button>
            )}
          </div>
        </div>
      )}
      {/* Main Search */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 transition-colors ${isLoading ? 'text-primary' : 'text-muted-foreground'}`} />
          <Input
            placeholder="Поиск по названию, ключевым словам, заказчику..."
            value={filters.search}
            onChange={(e) => updateFilter('search', e.target.value)}
            className={`pl-10 h-11 transition-all ${isLoading ? 'border-primary/50 shadow-[0_0_10px_rgba(var(--primary),0.1)]' : ''}`}
          />
        </div>

        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="gap-2 transition-transform active:scale-95"
          >
            <SlidersHorizontal className="h-4 w-4" />
            <span className="hidden sm:inline">Фильтры</span>
            {hasActiveFilters && (
              <Badge variant="secondary" className="ml-1 h-5 w-5 p-0 flex items-center justify-center text-xs animate-in zoom-in duration-300">
                !
              </Badge>
            )}
          </Button>

          {hasActiveFilters && (
            <Button variant="ghost" onClick={clearFilters} className="gap-2 transition-transform active:scale-95">
              <X className="h-4 w-4" />
              <span className="hidden sm:inline">Сбросить</span>
            </Button>
          )}
        </div>
      </div>

      {/* Quick Filters */}
      <div className="flex flex-col sm:flex-row flex-wrap gap-2">
        <Select value={filters.source || 'all'} onValueChange={(v) => updateFilter('source', v === 'all' ? '' : v)}>
          <SelectTrigger className="w-full sm:w-[180px] h-9 transition-all hover:bg-secondary">
            <SelectValue placeholder="Источник" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все источники</SelectItem>
            <SelectItem value="ЕИС Закупки">ЕИС Закупки</SelectItem>
            <SelectItem value="Сбербанк-АСТ">Сбербанк-АСТ</SelectItem>
            <SelectItem value="Росэлторг">Росэлторг</SelectItem>
            <SelectItem value="РТС-тендер">РТС-тендер</SelectItem>
            <SelectItem value="Газпромбанк">Газпромбанк</SelectItem>
            <SelectItem value="Национальная ЭП">Национальная ЭП</SelectItem>
            <SelectItem value="ЛОТ-Онлайн">ЛОТ-Онлайн</SelectItem>
            <SelectItem value="ЗаказРФ">ЗаказРФ</SelectItem>
            <SelectItem value="ТЭК-Торг">ТЭК-Торг</SelectItem>
          </SelectContent>
        </Select>
        <Select value={filters.region || 'all'} onValueChange={(v) => updateFilter('region', v === 'all' ? '' : v)}>
          <SelectTrigger className="w-full sm:w-[180px] h-9 transition-all hover:bg-secondary">
            <SelectValue placeholder="Регион" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все регионы</SelectItem>
            {regions.filter(Boolean).map((region) => (
              <SelectItem key={region} value={region}>{region}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filters.category || 'all'} onValueChange={(v) => updateFilter('category', v === 'all' ? '' : v)}>
          <SelectTrigger className="w-full sm:w-[220px] h-9 transition-all hover:bg-secondary">
            <SelectValue placeholder="Категория" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все категории</SelectItem>
            {categories.filter(Boolean).map((cat) => (
              <SelectItem key={cat} value={cat}>{cat}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={filters.procurementType || 'all'} onValueChange={(v) => updateFilter('procurementType', v === 'all' ? '' : v)}>
          <SelectTrigger className="w-full sm:w-[200px] h-9 transition-all hover:bg-secondary">
            <SelectValue placeholder="Тип закупки" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все типы</SelectItem>
            {procurementTypes.filter(Boolean).map((type) => (
              <SelectItem key={type} value={type}>{type}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2 px-2 h-9 bg-secondary/30 rounded-md border border-border">
          <Badge
            variant={filters.law44 ? "default" : "outline"}
            className={`cursor-pointer transition-all ${filters.law44 ? 'bg-primary hover:bg-primary/90' : 'hover:bg-secondary text-muted-foreground animate-in fade-in'}`}
            onClick={() => updateFilter('law44', !filters.law44)}
          >
            44-ФЗ
          </Badge>
          <Badge
            variant={filters.law223 ? "default" : "outline"}
            className={`cursor-pointer transition-all ${filters.law223 ? 'bg-primary hover:bg-primary/90' : 'hover:bg-secondary text-muted-foreground animate-in fade-in'}`}
            onClick={() => updateFilter('law223', !filters.law223)}
          >
            223-ФЗ
          </Badge>
        </div>

        <Select
          value={sortField + '-' + sortOrder}
          onValueChange={(v) => {
            const [field, order] = v.split('-') as [SortField, SortOrder];
            onSortChange(field, order);
          }}
        >
          <SelectTrigger className="w-full sm:w-[180px] h-9 transition-all hover:bg-secondary">
            <SelectValue placeholder="Сортировка" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="publishedAt-desc">Сначала новые</SelectItem>
            <SelectItem value="publishedAt-asc">Сначала старые</SelectItem>
            <SelectItem value="budget-desc">По бюджету ↓</SelectItem>
            <SelectItem value="budget-asc">По бюджету ↑</SelectItem>
            <SelectItem value="deadline-asc">По дедлайну ↑</SelectItem>
            <SelectItem value="deadline-desc">По дедлайну ↓</SelectItem>
          </SelectContent>
        </Select>

        {onSubscribeClick && (
          <Button
            variant={hasTelegramConnected ? "secondary" : "outline"}
            size="sm"
            className="h-9 gap-2"
            onClick={() => {
              if (hasTelegramConnected) {
                import('sonner').then(({ toast }) => toast.info('Вы уже получаете уведомления в Telegram'));
              } else {
                onSubscribeClick();
              }
            }}
            title={hasTelegramConnected ? "Уведомления в Telegram включены" : "Подписаться на уведомления по выбранным фильтрам"}
          >
            <Bell className={`h-4 w-4 ${hasTelegramConnected ? 'fill-primary text-primary' : ''}`} />
            <span className="hidden sm:inline">{hasTelegramConnected ? "Подписано" : "Уведомления в TG"}</span>
          </Button>
        )}
      </div>

      {/* Advanced Filters */}
      {
        showAdvanced && (
          <div className="p-4 rounded-lg bg-secondary/50 border border-border animate-in slide-in-from-top-2 duration-300 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="space-y-2">
                <Label className="text-sm text-muted-foreground">Бюджет от</Label>
                <Input
                  type="number"
                  placeholder="0"
                  value={filters.budgetFrom || ''}
                  onChange={(e) => updateFilter('budgetFrom', e.target.value ? Number(e.target.value) : null)}
                  className="h-9 transition-all focus:ring-1"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-sm text-muted-foreground">Бюджет до</Label>
                <Input
                  type="number"
                  placeholder="∞"
                  value={filters.budgetTo || ''}
                  onChange={(e) => updateFilter('budgetTo', e.target.value ? Number(e.target.value) : null)}
                  className="h-9 transition-all focus:ring-1"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-sm text-muted-foreground">Новые за</Label>
                <Select
                  value={filters.hoursAgo?.toString() || 'all'}
                  onValueChange={(v) => updateFilter('hoursAgo', v === 'all' ? null : Number(v))}
                >
                  <SelectTrigger className="h-9 transition-all hover:bg-secondary">
                    <Clock className="h-3.5 w-3.5 mr-2 text-muted-foreground" />
                    <SelectValue placeholder="Любое время" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Любое время</SelectItem>
                    <SelectItem value="1">1 час</SelectItem>
                    <SelectItem value="6">6 часов</SelectItem>
                    <SelectItem value="24">24 часа</SelectItem>
                    <SelectItem value="72">3 дня</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-end pb-1">
                <div className="flex items-center space-x-2">
                  <Switch
                    id="hide-micro"
                    checked={filters.hideMicroLots}
                    onCheckedChange={(checked) => updateFilter('hideMicroLots', checked)}
                  />
                  <Label htmlFor="hide-micro" className="text-sm cursor-pointer hover:text-foreground transition-colors">
                    Скрыть микролоты (&lt;100K)
                  </Label>
                </div>
              </div>
            </div>
          </div>
        )
      }

      {/* Results Count */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <div className="flex items-center gap-4">
          <span>
            Найдено: <span className="font-medium text-foreground">{filteredCount}</span> из {totalCount} тендеров
          </span>
          {isLoading && (
            <span className="flex items-center gap-2 text-primary animate-pulse font-medium">
              <span className="h-2 w-2 rounded-full bg-primary animate-bounce" />
              Поиск...
            </span>
          )}
        </div>
        <span className="flex items-center gap-1.5 transition-all">
          <span className={`h-2 w-2 rounded-full transition-all duration-500 ${isLoading ? 'bg-primary animate-pulse scale-150' : 'bg-accent'}`} />
          {isLoading ? 'Синхронизация данных...' : 'Обновлено только что'}
        </span>
      </div>
    </div >
  );
};
