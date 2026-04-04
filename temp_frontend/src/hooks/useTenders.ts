import { useState, useMemo, useCallback, useEffect } from 'react';
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
  aiSearch: false,
  page: 1,
  recordsPerPage: 50,
};

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
  if (!dateStr || typeof dateStr !== 'string') return new Date(0).toISOString(); // 1970 — при ошибке показываем «Срок истёк»
  const s = String(dateStr).trim();
  if (!s) return new Date(0).toISOString();

  // Уже ISO: 2026-02-24 или 2026-02-24T09:00:00
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

export const useTenders = () => {
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [filters, setFilters] = useState<TenderFilters>(defaultFilters);
  const [sortField, setSortField] = useState<SortField>('publishedAt');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const [showFavorites, setShowFavorites] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const fetchTenders = useCallback(async (opts?: { append?: boolean; pageOverride?: number }) => {
    const append = opts?.append ?? false;
    const pageToUse = opts?.pageOverride ?? filters.page;
    const token = localStorage.getItem('access_token');
    if (!token) {
      console.warn('No access token found, skipping fetch');
      setIsLoading(false);
      return;
    }

    if (!append) setIsLoading(true);
    else setIsLoadingMore(true);
    try {
      const params = new URLSearchParams({
        search_string: filters.search,
        law_44: filters.law44.toString(),
        law_223: filters.law223.toString(),
        page: pageToUse.toString(),
        records_per_page: '50',
        sort: mapSortToApi(sortField, sortOrder),
      });

      if (filters.budgetFrom !== null) params.append('price_from', filters.budgetFrom.toString());
      if (filters.budgetTo !== null) params.append('price_to', filters.budgetTo.toString());
      if (filters.region) params.append('region', filters.region);
      if (filters.source && filters.source !== 'all') params.append('source', filters.source);
      if (filters.companyDescription) params.append('company_description', filters.companyDescription);
      if (filters.category) params.append('stage', filters.category);
      if (filters.hoursAgo !== null) params.append('hours_ago', filters.hoursAgo.toString());
      if (filters.hideMicroLots) params.append('hide_micro', 'true');
      if (filters.aiSearch) params.append('ai_search', 'true');

      console.log('Fetching tenders with params:', params.toString());

      const response = await fetch(`/api/search?${params.toString()}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        if (response.status === 401) {
          localStorage.removeItem('access_token');
          window.location.href = '/auth';
          return;
        }
        throw new Error('Ошибка загрузки тендеров');
      }

      const result: { status?: string; data?: unknown; total?: number } = await response.json();
      console.log('API Response:', result);

      if (result.status === 'success') {
        const rawData = Array.isArray(result.data) ? result.data : [];
        const mapped: Tender[] = (rawData as ApiTenderRow[]).map((r) => ({
          id: String(r.number ?? ''),
          title: r.subject ?? '',
          customer: r.customer ?? '',
          budget: r.price ?? 0,
          category: r.stage || 'Закупка',
          region: r.region || 'Россия',
          procurementType: r.procurement_type || '44-ФЗ',
          deadline: parseRussianDate(r.update_date),
          publishedAt: parseRussianDate(r.update_date),
          source: getSourceFromProcurementType(r.procurement_type ?? null),
          sourceUrl: r.link ?? '',
          description: r.reason || '',
          isViewed: false,
          isFavorite: false,
          relevance: r.relevance
        }));
        if (append) {
          setTenders(prev => [...prev, ...mapped]);
        } else {
          setTenders(mapped);
        }
        setTotalCount(result.total || 0);
        const loaded = append ? tenders.length + mapped.length : mapped.length;
        setHasMore(mapped.length >= 50 && loaded < (result.total || 0));
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setIsLoading(false);
      setIsLoadingMore(false);
    }
  }, [filters, sortField, sortOrder]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchTenders({ append: false });
    }, 150);
    return () => clearTimeout(timer);
  }, [fetchTenders]);

  const filteredTenders = useMemo(() => {
    let result = [...tenders];
    if (showFavorites) {
      result = result.filter(t => t.isFavorite);
    }
    // Local filters (already filtered by backend mostly, but for immediate feel)
    if (filters.region && filters.region !== '') {
      result = result.filter(t => t.region.toLowerCase().includes(filters.region.toLowerCase()));
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
        comparison = b.budget - a.budget;
      } else if (sortField === 'deadline') {
        comparison = safeTs(b.deadline) - safeTs(a.deadline);
      }
      return sortOrder === 'desc' ? comparison : -comparison;
    });

    return result;
  }, [tenders, showFavorites, filters.region, sortField, sortOrder]);

  const toggleFavorite = useCallback((id: string) => {
    setTenders(prev => prev.map(t =>
      t.id === id ? { ...t, isFavorite: !t.isFavorite } : t
    ));
  }, []);

  const markViewed = useCallback((id: string) => {
    setTenders(prev => prev.map(t =>
      t.id === id ? { ...t, isViewed: true } : t
    ));
  }, []);

  const loadMore = useCallback(() => {
    if (!hasMore || isLoadingMore) return;
    setFilters(prev => ({ ...prev, page: prev.page + 1 }));
    fetchTenders({ append: true, pageOverride: filters.page + 1 });
  }, [hasMore, isLoadingMore, filters.page, fetchTenders]);

  const clearFilters = useCallback(() => {
    setFilters(defaultFilters);
  }, []);

  const handleSortChange = useCallback((field: SortField, order: SortOrder) => {
    setSortField(field);
    setSortOrder(order);
    setFilters(prev => ({ ...prev, page: 1 }));
  }, []);

  const favoritesCount = useMemo(() =>
    tenders.filter(t => t.isFavorite).length
    , [tenders]);

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
    isLoading
  };
};
