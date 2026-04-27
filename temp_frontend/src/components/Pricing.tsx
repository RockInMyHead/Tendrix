import { Button } from "@/components/ui/button";
import { Star, Sparkles, ShoppingCart } from "lucide-react";

const plans = [
  {
    name: "Базовый",
    tags: ["Для старта", "Небольшие объемы", "Все еще надежно и полезно"],
    features: [
      "Агрегатор тендеров",
      "Фильтры",
      "Поиск",
      "Умные подсказки (наклейки на карточках с подсказками от ИИ)",
      "Подписка на уведомления в Telegram",
    ],
    oldPrice: "6 500 ₽",
    price: "1 490 ₽",
    highlighted: false,
  },
  {
    name: "Умный",
    tags: ["Для старта", "Небольшие объемы", "Все еще надежно и полезно"],
    features: [
      "Все, что в базовом",
      "Умный режим с ИИ анализом",
      "Обучение ИИ данными о вашей компании, ваших возможностях и пожеланиях",
      "ИИ фильтрация (поиск и анализ всех тендеров с учетом особенностей вашего бизнеса)",
      "Расширенные ИИ подсказки",
      "Глубокий ИИ анализ условий тендеров (10шт/мес)",
      "Глубокий ИИ анализ контрагента (изменения цен, судебные дела, задолженности, фиктивные победители, участники и др.) (10 шт/мес)",
      "ИИ анализ подводных камней (10шт/мес)",
    ],
    oldPrice: "14 500 ₽",
    price: "4 950 ₽",
    highlighted: true,
  },
];

const StarIcon = ({ highlighted }: { highlighted: boolean }) => {
  if (highlighted) {
    return (
      <div className="w-16 h-16 rounded-2xl bg-primary-foreground/15 flex items-center justify-center shrink-0 relative">
        <Star className="w-8 h-8 text-primary" fill="currentColor" />
        <Sparkles className="w-4 h-4 text-primary absolute -top-0.5 -right-0.5" />
        <Star className="w-3.5 h-3.5 text-primary/70 absolute bottom-1 -right-1" fill="currentColor" />
      </div>
    );
  }
  return (
    <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center shrink-0">
      <Star className="w-7 h-7 text-primary" fill="currentColor" />
    </div>
  );
};

const Pricing = () => {
  return (
    <section id="pricing" className="py-20 bg-background">
      <div className="container">
        <h2 className="text-3xl lg:text-4xl font-bold text-center text-foreground mb-16">
          Тарифы
        </h2>
        <div className="grid md:grid-cols-2 gap-8 max-w-5xl mx-auto items-stretch">
          {plans.map((plan, i) => (
            <div
              key={i}
              className={`relative rounded-3xl p-8 flex flex-col h-full min-h-0 ${
                plan.highlighted
                  ? "bg-primary text-primary-foreground"
                  : "bg-card text-card-foreground border border-border"
              }`}
            >
              <div className="flex min-h-0 flex-1 flex-col">
                <div className="flex items-start justify-between mb-5">
                  <h3 className="font-bold text-2xl lg:text-3xl">{plan.name}</h3>
                  <StarIcon highlighted={plan.highlighted} />
                </div>

                <div className="flex flex-wrap gap-2 mb-6">
                  {plan.tags.map((tag, j) => (
                    <span
                      key={j}
                      className={`text-xs font-medium px-3 py-1.5 rounded-full ${
                        plan.highlighted
                          ? "bg-primary-foreground/20 text-primary-foreground"
                          : "border border-border text-muted-foreground"
                      }`}
                    >
                      {tag}
                    </span>
                  ))}
                </div>

                <ul className="space-y-1.5">
                  {plan.features.map((f, j) => (
                    <li
                      key={j}
                      className={`text-sm leading-relaxed ${
                        plan.highlighted
                          ? "text-primary-foreground/90"
                          : "text-muted-foreground"
                      }`}
                    >
                      - {f}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="flex flex-col gap-4 pt-8 mt-auto shrink-0 sm:flex-row sm:items-center sm:justify-between">
                <Button
                  className={`rounded-full px-6 h-12 text-base font-semibold gap-2 ${
                    plan.highlighted
                      ? "bg-primary-foreground text-primary hover:bg-primary-foreground/90"
                      : "bg-primary text-primary-foreground hover:bg-primary/90"
                  }`}
                >
                  Подключить тариф
                  <ShoppingCart className="w-5 h-5" />
                </Button>
                <div className="flex items-baseline gap-3">
                  <span
                    className={`text-base line-through ${
                      plan.highlighted
                        ? "text-primary-foreground/50"
                        : "text-muted-foreground"
                    }`}
                  >
                    {plan.oldPrice}
                  </span>
                  <span className="text-3xl lg:text-4xl font-extrabold">
                    {plan.price}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Pricing;
