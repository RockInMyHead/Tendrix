const steps = [
  {
    number: "01",
    title: "Настройте",
    subtitle: "поиск",
    description: "Укажите интересующие регионы, категории и бюджет. Сохраните настройки для быстрого доступа.",
    tags: [
      { label: "Удобно", color: "accent" as const },
      { label: "Быстро", color: "primary" as const },
      { label: "Точно", color: "primary" as const },
    ],
  },
  {
    number: "02",
    title: "Получайте",
    subtitle: "релевантное",
    description: "Система автоматически отфильтрует дубликаты, микролоты и нерелевантные предложения.",
    tags: [
      { label: "Просто", color: "primary" as const },
      { label: "Быстро", color: "accent" as const },
      { label: "Актуально", color: "accent" as const },
    ],
  },
  {
    number: "03",
    title: "Не пропускайте",
    subtitle: "важное",
    description: "Настройте уведомления в Telegram или email. Без спама — только нужные тендеры.",
    tags: [
      { label: "Удобно", color: "accent" as const },
      { label: "Быстро", color: "primary" as const },
      { label: "Точно", color: "primary" as const },
    ],
  },
];

const HowItWorks = () => {
  return (
    <section id="how" className="py-20 bg-background">
      <div className="container">
        {/* Header row */}
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-8 mb-16">
          <h2 className="text-3xl lg:text-4xl font-bold text-foreground max-w-sm">
            Как это работает
          </h2>
          <p className="text-sm text-muted-foreground max-w-lg leading-relaxed text-justify">
            вся инфраструктура тендерных закупок теперь работает на вас. система сканирует площадки, находит лоты, а ии расставляет визуальные метки: «высокая вероятность победы», «срочно», «снижение ставки». достаточно подписаться на telegram-канал — и уведомления с карточками приходят мгновенно. ничего не потерялось, всё под контролем.
          </p>
        </div>

        {/* Steps grid */}
        <div className="grid md:grid-cols-3 gap-8">
          {steps.map((step, i) => (
            <div key={i} className="relative">
              {/* Card */}
              <div className="bg-card rounded-2xl border p-6 space-y-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-bold text-lg text-foreground">{step.title}</h3>
                    <span className="font-bold text-lg text-accent">{step.subtitle}</span>
                  </div>
                  <div className="w-14 h-14 rounded-2xl border-2 border-accent/30 flex items-center justify-center">
                    <span className="font-bold text-lg text-accent">{step.number}</span>
                  </div>
                </div>
                {/* Decorative large number watermark */}
                <div className="h-24 relative overflow-hidden">
                  <span className="absolute text-[120px] font-extrabold text-muted/30 leading-none -bottom-6 left-0 select-none pointer-events-none">
                    {step.number}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed">{step.description}</p>
                <div className="flex flex-wrap gap-2 pt-2">
                  {step.tags.map((tag, j) => (
                    <span
                      key={j}
                      className={`text-xs font-medium px-3 py-1 rounded-full ${
                        tag.color === "accent"
                          ? "bg-accent/10 text-accent"
                          : "bg-primary/10 text-primary"
                      }`}
                    >
                      {tag.label}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default HowItWorks;
