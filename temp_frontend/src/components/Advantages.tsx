import { Brain, Clock, Shield, Zap, BarChart3, Settings } from "lucide-react";

const advantages = [
  {
    icon: <Brain className="w-7 h-7" />,
    title: "ИИ-мониторинг 24/7",
    description: "Искусственный интеллект непрерывно отслеживает новые тендеры и уведомляет вас о подходящих",
  },
  {
    icon: <Zap className="w-7 h-7" />,
    title: "Только подходящие",
    description: "Алгоритмы анализируют ваш профиль и подбирают тендеры с высокой вероятностью победы",
  },
  {
    icon: <Settings className="w-7 h-7" />,
    title: "Удобные инструменты",
    description: "Все необходимые инструменты для работы с тендерами в одном месте",
  },
];

const Advantages = () => {
  return (
    <section id="advantages" className="py-20 bg-primary text-primary-foreground relative overflow-hidden">
      {/* Decorative elements */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute top-20 right-20 w-64 h-64 border border-primary-foreground rounded-full" />
        <div className="absolute bottom-10 left-10 w-96 h-96 border border-primary-foreground rounded-full" />
      </div>
      
      <div className="container relative z-10">
        <h2 className="text-3xl lg:text-4xl font-bold text-center mb-4">
          Преимущества сервиса Tendrix.io
        </h2>
        <p className="text-center text-primary-foreground/70 mb-16 max-w-2xl mx-auto">
          Мы создали платформу, которая делает процесс участия в тендерах простым и эффективным
        </p>
        <div className="grid md:grid-cols-3 gap-8">
          {advantages.map((adv, i) => (
            <div
              key={i}
              className="bg-primary-foreground/10 backdrop-blur-sm border border-primary-foreground/20 rounded-2xl p-8 hover:bg-primary-foreground/15 transition-colors space-y-4"
            >
              <div className="w-14 h-14 rounded-xl bg-primary-foreground/20 flex items-center justify-center">
                {adv.icon}
              </div>
              <h3 className="font-bold text-xl">{adv.title}</h3>
              <p className="text-primary-foreground/70 leading-relaxed">{adv.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Advantages;
