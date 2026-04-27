import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { Tender, TenderFilters, SortField, SortOrder } from '@/types/tender';
import { toast } from 'sonner';

/** Ответ /api/search: элемент data[] */
interface ApiTenderRow {
  number?: string;
  subject?: string;
  customer?: string;
  price?: number | null;
  stage?: string | null;
  region?: string | null;
  procurement_type?: string | null;
  update_date?: string | null;
  link?: string | null;
  reason?: string | null;
  relevance?: number | null;
}

const defaultFilters: TenderFilters = {
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
  companyDescription: '',
  law44: true,
  law223: true,
  smartSearchMode: false,
  page: 1,
  recordsPerPage: 50,
};

/** Всё, что влияет на запрос к API, кроме page (пагинация «ещё» — отдельно). */
const buildSearchKey = (
  f: TenderFilters,
  sortField: SortField,
  sortOrder: SortOrder
): string =>
  JSON.stringify({
    search: f.search,
    region: f.region,
    source: f.source,
    budgetFrom: f.budgetFrom,
    budgetTo: f.budgetTo,
    category: f.category,
    procurementType: f.procurementType,
    hoursAgo: f.hoursAgo,
    hideMicroLots: f.hideMicroLots,
    excludeCategories: f.excludeCategories,
    excludeCustomers: f.excludeCustomers,
    companyDescription: f.companyDescription,
    law44: f.law44,
    law223: f.law223,
    smartSearchMode: f.smartSearchMode,
    sortField,
    sortOrder,
  });

// Извлечь источник из procurement_type для отображения
const getSourceFromProcurementType = (pt: string | null): string => {
  if (!pt) return 'ЕИС Закупки';
  if (pt.includes('Сбербанк-АСТ')) return 'Сбербанк-АСТ';
  if (pt.includes('Росэлторг')) return 'Росэлторг';
  if (pt.includes('РТС-тендер')) return 'РТС-тендер';
  if (pt.includes('Газпромбанк')) return 'Газпромбанк';
  if (pt.includes('Национальная ЭП')) return 'Национальная ЭП';
  if (pt.includes('ЛОТ-Онлайн')) return 'ЛОТ-Онлайн';
  if (pt.includes('ЗаказРФ')) return 'ЗаказРФ';
  if (pt.includes('ТЭК-Торг')) return 'ТЭК-Торг';
  return 'ЕИС Закупки';
};

/** Парсит дату из API (DD.MM.YYYY, DD.MM.YY, DD.MM.YYYY HH:MM, ISO). Возвращает валидный ISO-строка. */
const parseRussianDate = (dateStr: string | null | undefined): string => {
  if (!dateStr || typeof dateStr !== 'string') return new Date(0).toISOString();
  const s = String(dateStr).trim();
  if (!s) return new Date(0).toISOString();

  if (s.includes('-') && /^\d{4}-\d{2}-\d{2}/.test(s)) return s;

  const parts = s.split(/\s+/);
  const datePart = parts[0] || '';
  const timePart = parts[1] || '';

  const dParts = datePart.split('.');
  if (dParts.length >= 3) {
    let year = (dParts[2] || '').split(/\s/)[0] || dParts[2];
    if (year.length === 2) {
      const y = parseInt(year, 10);
      year = String(y >= 50 ? 1900 + y : 2000 + y);
    }
    const month = (dParts[1] || '01').padStart(2, '0');
    const day = (dParts[0] || '01').padStart(2, '0');
    let iso = `${year}-${month}-${day}`;
    if (timePart && /^\d{1,2}:\d{2}/.test(timePart)) {
      const [h, m] = timePart.split(':');
      iso += `T${String(h || '00').padStart(2, '0')}:${String(m || '00').padStart(2, '0')}:00`;
    }
    const parsed = new Date(iso);
    return isNaN(parsed.getTime()) ? new Date(0).toISOString() : parsed.toISOString();
  }
  return new Date(0).toISOString();
};

/** Маппинг фронтенд-сортировки → бэкенд-параметр sort */
const mapSortToApi = (field: SortField, order: SortOrder): string => {
  if (field === 'publishedAt' || field === 'deadline') return `date-${order}`;
  if (field === 'budget') return `price-${order}`;
  return 'date-desc';
};

export type UseTendersOptions = {
  /** Пока false — не дергаем /api/search (после подтягивания профиля включить). */
  searchEnabled?: boolean;
};

export const useTenders = (options?: UseTendersOptions) => {
  const searchEnabled = options?.searchEnabled !== false;

  const [tenders, setTenders] = useState<Tender[]>([]);
  const [filters, setFilters] = useState<TenderFilters>(defaultFilters);
  const [sortField, setSortField] = useState<SortField>('publishedAt');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const sortFieldRef = useRef(sortField);
  const sortOrderRef = useRef(sortOrder);
  sortFieldRef.current = sortField;
  sortOrderRef.current = sortOrder;

  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const fetchSeqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const [showFavorites, setShowFavorites] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const searchKey = useMemo(
    () => buildSearchKey(filters, sortField, sortOrder),
    [filters, sortField, sortOrder]
  );

  const fetchTenders = useCallback(async (opts?: { append?: boolean; pageOverride?: number }) => {
    const append = opts?.append ?? false;
    const f = filtersRef.current;
    const pageToUse = opts?.pageOverride ?? f.page;
    const token = localStorage.getItem('access_token');
    if (!token) {
      console.warn('No access token found, skipping fetch');
      setIsLoading(false);
      return;
    }

    if (!append) {
      abortRef.current?.abort();
      abortRef.current = new AbortController();
      fetchSeqRef.current += 1;
      const seq = fetchSeqRef.current;
      setTenders([]);
      setIsLoading(true);
      try {
        const combinedSearch = f.smartSearchMode
          ? ''
          : [f.search, f.category].filter(Boolean).join(' ').trim();

        const params = new URLSearchParams({
          search_string: combinedSearch,
          page: String(pageToUse),
          records_per_page: '50',
          sort: mapSortToApi(sortFieldRef.current, sortOrderRef.current),
        });

        if (f.procurementType === '44-ФЗ') {
          params.set('law_44', 'true');
          params.set('law_223', 'false');
        } else if (f.procurementType === '223-ФЗ') {
          params.set('law_44', 'false');
          params.set('law_223', 'true');
        } else {
          params.set('law_44', f.law44.toString());
          params.set('law_223', f.law223.toString());
          const procurementKind = ['Аукцион', 'Конкурс', 'Запрос котировок', 'Запрос предложений'];
          if (f.procurementType && procurementKind.includes(f.procurementType)) {
            params.append('procurement_kind', f.procurementType);
          }
        }

        if (f.budgetFrom !== null) params.append('price_from', f.budgetFrom.toString());
        if (f.budgetTo !== null) params.append('price_to', f.budgetTo.toString());
        if (f.region) params.append('region', f.region);
        if (f.source && f.source !== 'all') params.append('source', f.source);
        if (f.smartSearchMode && f.companyDescription?.trim()) {
          params.append('company_description', f.companyDescription.trim());
        }
        if (f.hoursAgo !== null) params.append('hours_ago', f.hoursAgo.toString());
        if (f.hideMicroLots) params.append('hide_micro', 'true');
        if (f.smartSearchMode) params.append('ai_search', 'true');

        const response = await fetch(`/api/search?${params.toString()}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: abortRef.current.signal,
        });

        if (seq !== fetchSeqRef.current) return;

        if (!response.ok) {
          if (response.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = '/auth';
            return;
          }
          let msg = 'Ошибка загрузки тендеров';
          try {
            const errBody = await response.json();
            const d = errBody?.detail;
            if (typeof d === 'string') msg = d;
            else if (Array.isArray(d)) msg = d.map((x: { msg?: string }) => x?.msg ?? String(x)).join(' ');
          } catch {
            /* ignore */
          }
          throw new Error(msg);
        }

        const result: { status?: string; data?: unknown; total?: number } = await response.json();

        if (seq !== fetchSeqRef.current) return;

        if (result.status === 'success') {
          const rawData = Array.isArray(result.data) ? result.data : [];
          const showAi = !!f.smartSearchMode;
          const mapped: Tender[] = (rawData as ApiTenderRow[]).map((r) => ({
            id: String(r.number ?? ''),
            title: r.subject ?? '',
            customer: r.customer ?? '',
            budget: r.price ?? null,
            category: r.stage || 'Закупка',
            region: r.region || 'Россия',
            procurementType: r.procurement_type || '44-ФЗ',
            deadline: parseRussianDate(r.update_date),
            publishedAt: parseRussianDate(r.update_date),
            source: getSourceFromProcurementType(r.procurement_type ?? null),
            sourceUrl: r.link ?? '',
            description: '',
            isViewed: false,
            isFavorite: false,
            relevance: showAi ? (r.relevance ?? undefined) : undefined,
            relevanceReason: showAi ? (typeof r.reason === 'string' ? r.reason.trim() : '') || undefined : undefined,
          }));
          setTenders(mapped);
          setTotalCount(result.total || 0);
          setHasMore(mapped.length >= 50 && mapped.length < (result.total || 0));
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') return;
        if (seq !== fetchSeqRef.current) return;
        toast.error(err instanceof Error ? err.message : 'Ошибка загрузки');
      } finally {
        if (seq === fetchSeqRef.current) setIsLoading(false);
      }
      return;
    }

    setIsLoadingMore(true);
    try {
      const f2 = filtersRef.current;
      const combinedSearch = f2.smartSearchMode
        ? ''
        : [f2.search, f2.category].filter(Boolean).join(' ').trim();

      const params = new URLSearchParams({
        search_string: combinedSearch,
        page: String(pageToUse),
        records_per_page: '50',
        sort: mapSortToApi(sortFieldRef.current, sortOrderRef.current),
      });

      if (f2.procurementType === '44-ФЗ') {
        params.set('law_44', 'true');
        params.set('law_223', 'false');
      } else if (f2.procurementType === '223-ФЗ') {
        params.set('law_44', 'false');
        params.set('law_223', 'true');
      } else {
        params.set('law_44', f2.law44.toString());
        params.set('law_223', f2.law223.toString());
        const procurementKind = ['Аукцион', 'Конкурс', 'Запрос котировок', 'Запрос предложений'];
        if (f2.procurementType && procurementKind.includes(f2.procurementType)) {
          params.append('procurement_kind', f2.procurementType);
        }
      }

      if (f2.budgetFrom !== null) params.append('price_from', f2.budgetFrom.toString());
      if (f2.budgetTo !== null) params.append('price_to', f2.budgetTo.toString());
      if (f2.region) params.append('region', f2.region);
      if (f2.source && f2.source !== 'all') params.append('source', f2.source);
      if (f2.smartSearchMode && f2.companyDescription?.trim()) {
        params.append('company_description', f2.companyDescription.trim());
      }
      if (f2.hoursAgo !== null) params.append('hours_ago', f2.hoursAgo.toString());
      if (f2.hideMicroLots) params.append('hide_micro', 'true');
      if (f2.smartSearchMode) params.append('ai_search', 'true');

      const response = await fetch(`/api/search?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        if (response.status === 401) {
          localStorage.removeItem('access_token');
          window.location.href = '/auth';
          return;
        }
        let msg = 'Ошибка загрузки тендеров';
        try {
          const errBody = await response.json();
          const d = errBody?.detail;
          if (typeof d === 'string') msg = d;
          else if (Array.isArray(d)) msg = d.map((x: { msg?: string }) => x?.msg ?? String(x)).join(' ');
        } catch {
          /* ignore */
        }
        throw new Error(msg);
      }

      const result: { status?: string; data?: unknown; total?: number } = await response.json();

      if (result.status === 'success') {
        const rawData = Array.isArray(result.data) ? result.data : [];
        const showAi = !!f2.smartSearchMode;
        const mapped: Tender[] = (rawData as ApiTenderRow[]).map((r) => ({
          id: String(r.number ?? ''),
          title: r.subject ?? '',
          customer: r.customer ?? '',
          budget: r.price ?? null,
          category: r.stage || 'Закупка',
          region: r.region || 'Россия',
          procurementType: r.procurement_type || '44-ФЗ',
          deadline: parseRussianDate(r.update_date),
          publishedAt: parseRussianDate(r.update_date),
          source: getSourceFromProcurementType(r.procurement_type ?? null),
          sourceUrl: r.link ?? '',
          description: '',
          isViewed: false,
          isFavorite: false,
          relevance: showAi ? (r.relevance ?? undefined) : undefined,
          relevanceReason: showAi ? (typeof r.reason === 'string' ? r.reason.trim() : '') || undefined : undefined,
        }));
        const total = result.total || 0;
        setTenders((prev) => {
          const next = [...prev, ...mapped];
          setHasMore(mapped.length >= 50 && next.length < total);
          return next;
        });
        setTotalCount(total);
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setIsLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    if (!searchEnabled) return;
    const timer = setTimeout(() => {
      setFilters((prev) => (prev.page === 1 ? prev : { ...prev, page: 1 }));
      fetchTenders({ append: false, pageOverride: 1 });
    }, 320);
    return () => clearTimeout(timer);
  }, [searchKey, searchEnabled, fetchTenders]);

  const filteredTenders = useMemo(() => {
    let result = [...tenders];
    if (showFavorites) {
      result = result.filter((t) => t.isFavorite);
    }
    if (filters.region && filters.region !== '') {
      result = result.filter((t) => t.region.toLowerCase().includes(filters.region.toLowerCase()));
    }

    const safeTs = (s: string) => {
      const t = new Date(s).getTime();
      return isNaN(t) ? 0 : t;
    };
    result.sort((a, b) => {
      let comparison = 0;
      if (sortField === 'publishedAt') {
        comparison = safeTs(b.publishedAt) - safeTs(a.publishedAt);
      } else if (sortField === 'budget') {
        comparison = (b.budget ?? -1) - (a.budget ?? -1);
      } else if (sortField === 'deadline') {
        comparison = safeTs(b.deadline) - safeTs(a.deadline);
      }
      return sortOrder === 'desc' ? comparison : -comparison;
    });

    return result;
  }, [tenders, showFavorites, filters.region, sortField, sortOrder]);

  const toggleFavorite = useCallback((id: string) => {
    setTenders((prev) => prev.map((t) => (t.id === id ? { ...t, isFavorite: !t.isFavorite } : t)));
  }, []);

  const markViewed = useCallback((id: string) => {
    setTenders((prev) => prev.map((t) => (t.id === id ? { ...t, isViewed: true } : t)));
  }, []);

  const loadMore = useCallback(() => {
    if (!hasMore || isLoadingMore || isLoading) return;
    const nextPage = filtersRef.current.page + 1;
    setFilters((prev) => ({ ...prev, page: nextPage }));
    fetchTenders({ append: true, pageOverride: nextPage });
  }, [hasMore, isLoadingMore, isLoading, fetchTenders]);

  const clearFilters = useCallback(() => {
    setFilters(defaultFilters);
  }, []);

  const handleSortChange = useCallback((field: SortField, order: SortOrder) => {
    setSortField(field);
    setSortOrder(order);
    setFilters((prev) => ({ ...prev, page: 1 }));
  }, []);

  const favoritesCount = useMemo(() => tenders.filter((t) => t.isFavorite).length, [tenders]);

  return {
    tenders,
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
  };
};
