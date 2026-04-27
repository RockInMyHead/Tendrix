export interface Tender {
  id: string;
  title: string;
  customer: string;
  budget: number | null;
  category: string;
  region: string;
  procurementType: string;
  deadline: string;
  publishedAt: string;
  source: string;
  sourceUrl: string;
  description: string;
  isViewed: boolean;
  isFavorite: boolean;
  relevance?: number;
  /** Текст от ИИ: почему тендер подходит под описание компании (умный поиск) */
  relevanceReason?: string;
}

export interface TenderFilters {
  search: string;
  region: string;
  source: string;
  budgetFrom: number | null;
  budgetTo: number | null;
  category: string;
  procurementType: string;
  hoursAgo: number | null;
  hideMicroLots: boolean;
  excludeCategories: string[];
  excludeCustomers: string[];
  companyDescription: string;
  law44: boolean;
  law223: boolean;
  /** true только после «Найти по описанию компании»; держим для подгрузки страниц с ai_search */
  smartSearchMode?: boolean;
  page: number;
  recordsPerPage: number;
}

export type SortField = 'publishedAt' | 'budget' | 'deadline';
export type SortOrder = 'asc' | 'desc';
