import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Sparkles, Check, Loader2 } from "lucide-react";

interface ProModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isPro: boolean;
  onBuy: () => void;
  loading: boolean;
}

const PRO_FEATURES = [
  "AI-анализ соответствия тендера вашим критериям с процентом релевантности",
  "Глубокий AI-анализ всех вкладок тендера — документы, требования, условия",
  "Поиск подводных камней и рисков в документации закупки",
  "Приоритетная поддержка и обновления",
];

export const ProModal = ({
  open,
  onOpenChange,
  isPro,
  onBuy,
  loading,
}: ProModalProps) => {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} modal>
      <DialogContent className="sm:max-w-md z-[100]">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-r from-amber-400 to-orange-500 flex items-center justify-center">
              <Sparkles className="h-5 w-5 text-white fill-white" />
            </div>
            <div>
              <DialogTitle className="text-xl">Tendrix Pro</DialogTitle>
              <DialogDescription>
                Расширенные возможности для профессионалов закупок
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <p className="text-sm text-muted-foreground">
            {isPro
              ? "У вас активна подписка Pro. Все функции доступны."
              : "Получите доступ ко всем AI-инструментам для эффективного поиска тендеров:"}
          </p>
          <ul className="space-y-3">
            {PRO_FEATURES.map((feature, i) => (
              <li key={i} className="flex gap-3 text-sm">
                <Check className="h-5 w-5 shrink-0 text-emerald-500 mt-0.5" />
                <span>{feature}</span>
              </li>
            ))}
          </ul>
        </div>

        {!isPro && (
          <DialogFooter className="flex-col sm:flex-row gap-2">
            <Button
              className="w-full sm:w-auto bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white border-0"
              onClick={onBuy}
              disabled={loading}
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>Купить 499 ₽/мес</>
              )}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
};
