import { Button } from "@/components/ui/button";
import { Bookmark, Sparkles, Send, Star, ArrowDownRight } from "lucide-react";
import { Link } from "react-router-dom";

const HeroSection = () => {
  return (
    <section className="relative overflow-hidden bg-background pt-10 pb-0">
      <div className="container">
        {/* Title row 1 - icons inline with text */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="w-12 h-12 rounded-2xl bg-muted flex items-center justify-center shrink-0">
            <Sparkles className="w-6 h-6 text-foreground" />
          </div>
          <div className="w-12 h-12 rounded-2xl bg-primary flex items-center justify-center shrink-0">
            <Send className="w-6 h-6 text-primary-foreground -rotate-[30deg]" />
          </div>
          <span className="text-[42px] lg:text-[56px] xl:text-[64px] font-extrabold leading-none text-foreground tracking-tight">
            Tendrix.io — тендеры
          </span>
          <div className="w-12 h-12 rounded-2xl bg-accent flex items-center justify-center shrink-0">
            <ArrowDownRight className="w-6 h-6 text-accent-foreground" />
          </div>
        </div>
        {/* Title row 2 */}
        <h1 className="text-[42px] lg:text-[56px] xl:text-[64px] font-extrabold leading-none text-foreground tracking-tight mt-2">
          с <span className="text-accent">искусственным</span> интеллектом
        </h1>

        {/* Subtitle */}
        <p className="mt-8 text-lg text-muted-foreground max-w-lg leading-relaxed italic">
          Мгновенный доступ к тысячам закупок. ИИ сам найдёт ваши лоты, расставит приоритеты и подскажет, где выиграть.
        </p>

        {/* Buttons */}
        <div className="flex flex-wrap gap-4 mt-8">
          <Button variant="outline" size="lg" className="rounded-full text-base px-8 h-12 border-2" asChild>
            <a href="#pricing">Тарифы</a>
          </Button>
          <Button size="lg" className="rounded-full text-base px-8 h-12" asChild>
            <Link to="/app">Смотреть тендеры</Link>
          </Button>
        </div>

        {/* Hero visual area */}
        <div className="relative mt-8 min-h-[400px] lg:min-h-[480px]">
          {/* Laptop mockup - positioned right */}
          <div className="absolute right-0 top-0 w-[65%] hidden md:block">
            <div className="bg-laptop-frame rounded-t-2xl pt-5 px-1 relative shadow-2xl">
              {/* Browser dots */}
              <div className="flex items-center gap-1.5 px-4 pb-3">
                <div className="w-2.5 h-2.5 rounded-full bg-destructive/60" />
                <div className="w-2.5 h-2.5 rounded-full bg-accent/50" />
                <div className="w-2.5 h-2.5 rounded-full bg-accent/70" />
                <div className="flex-1 mx-3 h-5 bg-primary-foreground/10 rounded" />
              </div>
              {/* Screen content mimicking the site itself */}
              <div className="bg-background rounded-t-lg mx-1 p-5 min-h-[260px]">
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-full bg-foreground flex items-center justify-center">
                      <Send className="w-3 h-3 text-background -rotate-[30deg]" />
                    </div>
                    <span className="font-bold text-foreground text-xs">TENDRIX</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="text-[8px] text-muted-foreground">tg - бот</span>
                    <span className="text-[8px] text-muted-foreground border rounded px-1">Начать</span>
                    <span className="text-[8px] bg-primary text-primary-foreground rounded px-1">Войти</span>
                  </div>
                </div>
                <div className="flex items-center gap-1 mb-1">
                  <div className="w-4 h-4 rounded bg-muted flex items-center justify-center">
                    <Sparkles className="w-2 h-2" />
                  </div>
                  <div className="w-4 h-4 rounded bg-primary flex items-center justify-center">
                    <Send className="w-2 h-2 text-primary-foreground -rotate-[30deg]" />
                  </div>
                </div>
                <h3 className="text-sm font-extrabold text-foreground leading-tight">
                  Tendrix — тендеры
                </h3>
                <div className="flex items-center gap-1">
                  <h3 className="text-sm font-extrabold leading-tight">
                    с <span className="text-accent">искуственным</span> интеллектом
                  </h3>
                  <div className="w-4 h-4 rounded bg-accent flex items-center justify-center">
                    <ArrowDownRight className="w-2 h-2 text-accent-foreground" />
                  </div>
                </div>
                <p className="text-[7px] text-muted-foreground mt-2 max-w-[180px] italic">
                  Мгновенный доступ к тысячам закупок. ИИ сам найдёт ваши лоты, расставит приоритеты и подскажет, где выиграть.
                </p>
                <div className="flex gap-1.5 mt-3">
                  <span className="text-[7px] text-foreground border rounded-full px-2 py-0.5">Тарифы</span>
                  <span className="text-[7px] bg-primary text-primary-foreground rounded-full px-2 py-0.5">Смотреть тендеры</span>
                </div>
              </div>
            </div>
            <div className="h-5 bg-gradient-to-b from-laptop-frame to-laptop-base rounded-b-xl" />
          </div>

          {/* Floating card - "Новый тендер" (left side) */}
          <div className="absolute left-0 bottom-32 hidden lg:block z-10 -rotate-6">
            <div className="bg-card/90 backdrop-blur-sm rounded-2xl shadow-xl p-4 w-72 border">
              <div className="flex items-start gap-3">
                <div className="w-12 h-12 rounded-xl bg-primary flex items-center justify-center shrink-0">
                  <Bookmark className="w-6 h-6 text-primary-foreground" />
                </div>
                <div className="flex-1">
                  <div className="font-extrabold text-xl text-foreground">Новый тендер</div>
                  <div className="text-sm text-muted-foreground">it - оборудование</div>
                </div>
                <span className="text-sm font-semibold text-foreground whitespace-nowrap">15.5 млн</span>
              </div>
              <div className="flex gap-2 mt-3">
                <span className="text-xs bg-accent text-accent-foreground px-3 py-1 rounded-full font-medium">Безопасная</span>
                <span className="text-xs bg-accent text-accent-foreground px-3 py-1 rounded-full font-medium">Гарант</span>
              </div>
            </div>
          </div>

          {/* Dashed green arrow */}
          <svg className="absolute left-[260px] bottom-20 hidden lg:block z-10" width="100" height="100" viewBox="0 0 100 100" fill="none">
            <path d="M10 10 C20 30 40 50 70 70 L90 90" stroke="hsl(var(--accent))" strokeWidth="2.5" strokeDasharray="8 6" strokeLinecap="round" />
            <path d="M75 85 L90 90 L82 78" stroke="hsl(var(--accent))" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>

          {/* Floating card - "Тендер ваш!" (center-bottom, green) */}
          <div className="absolute left-[25%] bottom-8 hidden lg:block z-10 rotate-3">
            <div className="bg-accent rounded-2xl shadow-xl p-4 flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-accent-foreground/20 flex items-center justify-center shrink-0">
                <Star className="w-6 h-6 text-accent-foreground" />
              </div>
              <div>
                <div className="font-extrabold text-lg text-accent-foreground">Тендер ваш!</div>
                <div className="text-sm text-accent-foreground/80">it - оборудование</div>
              </div>
              <span className="text-sm font-semibold text-accent-foreground ml-2 whitespace-nowrap">15.5 млн</span>
            </div>
          </div>
        </div>


        {/* Stats bar */}
        <div className="flex justify-center gap-6 lg:gap-10 py-14">
          <StatCard value="50к +" label="Тендеров" />
          <StatCard value="5" label="Источников" />
          <StatCard value="24 / 7" label="Обновления" />
        </div>
      </div>
    </section>
  );
};

const StatCard = ({ value, label }: { value: string; label: string }) => (
  <div className="flex items-center gap-5 border rounded-2xl px-8 py-6 bg-card shadow-sm">
    <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center">
      <Bookmark className="w-6 h-6 text-primary fill-primary" />
    </div>
    <div>
      <div className="font-extrabold text-3xl lg:text-4xl text-foreground">{value}</div>
      <div className="text-sm text-muted-foreground">{label}</div>
    </div>
  </div>
);

export default HeroSection;
