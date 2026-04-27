import { Search, Heart, FileX } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface EmptyStateProps {
  type: 'no-results' | 'no-favorites' | 'error';
  onClearFilters?: () => void;
}

export const EmptyState = ({ type, onClearFilters }: EmptyStateProps) => {
  const content = {
    'no-results': {
      icon: Search,
      title: 'Тендеры не найдены',
      description: 'Попробуйте изменить параметры поиска или сбросить фильтры',
      action: onClearFilters && (
        <Button variant="outline" onClick={onClearFilters}>
          Сбросить фильтры
        </Button>
      ),
    },
    'no-favorites': {
      icon: Heart,
      title: 'Избранное пусто',
      description: 'Добавляйте интересные тендеры в избранное, чтобы быстро к ним возвращаться',
      action: null,
    },
    'error': {
      icon: FileX,
      title: 'Произошла ошибка',
      description: 'Не удалось загрузить данные. Попробуйте обновить страницу',
      action: (
        <Button variant="outline" onClick={() => window.location.reload()}>
          Обновить
        </Button>
      ),
    },
  };

  const { icon: Icon, title, description, action } = content[type];

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center animate-fade-in">
      <div className="h-16 w-16 rounded-full bg-secondary flex items-center justify-center mb-4">
        <Icon className="h-8 w-8 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-medium text-foreground mb-2">{title}</h3>
      <p className="text-muted-foreground mb-6 max-w-sm">{description}</p>
      {action}
    </div>
  );
};
