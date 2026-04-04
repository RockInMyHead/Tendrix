import { Star } from "lucide-react";

const reviews = [
  {
    name: "Алексей К.",
    role: "Генеральный директор",
    text: "Tendrix.io помог нам увеличить количество выигранных тендеров на 40%. ИИ-подбор экономит часы работы.",
    rating: 5,
  },
  {
    name: "Мария С.",
    role: "Генеральный директор",
    text: "Удобная платформа с понятным интерфейсом. Подготовка документов стала в разы быстрее.",
    rating: 5,
  },
  {
    name: "Дмитрий В.",
    role: "Индивидуальный предприниматель",
    text: "Отличный сервис для малого бизнеса. Бесплатный тариф позволяет начать без рисков.",
    rating: 4,
  },
  {
    name: "Елена П.",
    role: "Генеральный директор",
    text: "Автоматические уведомления и аналитика — это именно то, что нам было нужно. Рекомендую!",
    rating: 5,
  },
];

const Reviews = () => {
  return (
    <section id="reviews" className="py-20 bg-section-bg">
      <div className="container">
        <h2 className="text-3xl lg:text-4xl font-bold text-center text-foreground mb-16">
          Отзывы
        </h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {reviews.map((review, i) => (
            <div key={i} className="bg-card rounded-xl p-6 shadow-sm space-y-4">
              <div className="flex gap-0.5">
                {Array.from({ length: 5 }).map((_, j) => (
                  <Star
                    key={j}
                    className={`w-4 h-4 ${j < review.rating ? "fill-yellow-400 text-yellow-400" : "text-border"}`}
                  />
                ))}
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">"{review.text}"</p>
              <div className="pt-2 border-t">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                    <span className="text-primary font-semibold text-sm">{review.name[0]}</span>
                  </div>
                  <div>
                    <div className="font-semibold text-sm text-foreground">{review.name}</div>
                    <div className="text-xs text-muted-foreground">{review.role}</div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Reviews;
