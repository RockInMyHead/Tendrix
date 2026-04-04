import { Button } from "@/components/ui/button";
import { Send, Play, User } from "lucide-react";
import { Link } from "react-router-dom";

const Header = () => {
  return (
    <header className="sticky top-0 z-50 bg-background/80 backdrop-blur-md border-b">
      <div className="container flex items-center justify-between h-16">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
            <Send className="w-4 h-4 text-primary-foreground rotate-[-30deg]" />
          </div>
          <span className="font-bold text-lg text-foreground tracking-tight">TENDRIX.IO</span>
        </div>
        <nav className="hidden lg:flex items-center gap-6 text-sm font-medium text-muted-foreground">
          <a href="#about" className="text-foreground font-semibold">О сервисе</a>
          <a href="#how" className="hover:text-foreground transition-colors">Как это работает?</a>
          <a href="#advantages" className="hover:text-foreground transition-colors">Преимущества</a>
          <a href="#pricing" className="hover:text-foreground transition-colors">Тарифы</a>
          <a href="#reviews" className="hover:text-foreground transition-colors">Отзывы</a>
          <a href="#description" className="hover:text-foreground transition-colors">Описание</a>
        </nav>
        <div className="flex items-center gap-3">
          <div className="hidden md:flex items-center gap-2 border rounded-full px-4 py-2 bg-primary/5 border-primary/10">
            <Send className="w-4 h-4 text-primary" />
            <span className="text-sm font-medium text-foreground">tg - бот</span>
          </div>
          <Button variant="outline" size="sm" className="rounded-full gap-1.5 border-primary/10" asChild>
            <Link to="/app">
              <Play className="w-3 h-3 text-primary fill-primary" />
              Начать
            </Link>
          </Button>
          <Button size="sm" className="rounded-full gap-1.5" asChild>
            <Link to="/auth">
              <User className="w-3.5 h-3.5" />
              Войти
            </Link>
          </Button>
        </div>
      </div>
    </header>
  );
};

export default Header;
