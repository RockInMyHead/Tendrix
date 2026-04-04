import { Database, Bell, LineChart, Lock, Users, Globe } from "lucide-react";

const features = [
  { icon: <Database className="w-5 h-5" />, title: "Единая база тендеров", description: "Агрегация данных с 5+ торговых площадок в реальном времени" },
  { icon: <Bell className="w-5 h-5" />, title: "Умные уведомления", description: "Настраиваемые уведомления через email, Telegram и SMS" },
  { icon: <LineChart className="w-5 h-5" />, title: "Аналитика и отчёты", description: "Детальная статистика участия и прогноз вероятности победы" },
  { icon: <Lock className="w-5 h-5" />, title: "Безопасность данных", description: "Шифрование данных и соответствие требованиям 152-ФЗ" },
  { icon: <Users className="w-5 h-5" />, title: "Командная работа", description: "Совместная работа над тендерами с разграничением ролей" },
  { icon: <Globe className="w-5 h-5" />, title: "Все регионы РФ", description: "Покрытие тендеров по всем регионам Российской Федерации" },
];

const MoreInfo = () => {
  return (
    <section className="py-20 bg-background">
      <div className="container">
        <h2 className="text-3xl lg:text-4xl font-bold text-center text-foreground mb-4">
          Ещё немного о сервисе
        </h2>
        <p className="text-center text-muted-foreground mb-16 max-w-2xl mx-auto">
          Дополнительные возможности, которые делают работу с тендерами эффективнее
        </p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {features.map((f, i) => (
            <div key={i} className="flex gap-4 p-5 rounded-xl border bg-card hover:shadow-sm transition-shadow">
              <div className="shrink-0 w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                {f.icon}
              </div>
              <div>
                <h3 className="font-semibold text-foreground mb-1">{f.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{f.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default MoreInfo;
