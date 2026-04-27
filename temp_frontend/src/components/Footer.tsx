const Footer = () => {
  return (
    <footer className="bg-foreground text-background py-12">
      <div className="container">
        <div className="grid md:grid-cols-4 gap-8 mb-8">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
                <span className="text-primary-foreground font-bold text-sm">T</span>
              </div>
              <span className="font-bold text-lg">TENDRIX.IO</span>
            </div>
            <p className="text-sm text-background/60">
              Агрегатор тендеров с искусственным интеллектом
            </p>
          </div>
          <div>
            <h4 className="font-semibold mb-4">Продукт</h4>
            <ul className="space-y-2 text-sm text-background/60">
              <li><a href="#" className="hover:text-background transition-colors">Возможности</a></li>
              <li><a href="#pricing" className="hover:text-background transition-colors">Тарифы</a></li>
              <li><a href="#" className="hover:text-background transition-colors">API</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold mb-4">Компания</h4>
            <ul className="space-y-2 text-sm text-background/60">
              <li><a href="#" className="hover:text-background transition-colors">О нас</a></li>
              <li><a href="#" className="hover:text-background transition-colors">Блог</a></li>
              <li><a href="#" className="hover:text-background transition-colors">Контакты</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold mb-4">Поддержка</h4>
            <ul className="space-y-2 text-sm text-background/60">
              <li><a href="#" className="hover:text-background transition-colors">Документация</a></li>
              <li><a href="#" className="hover:text-background transition-colors">FAQ</a></li>
              <li><a href="#" className="hover:text-background transition-colors">Обратная связь</a></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-background/20 pt-8 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-background/40">
          <span>© 2024 Tendrix.io. Все права защищены.</span>
          <div className="flex gap-6">
            <a
              href="/legal/privacy-policy.pdf"
              target="_blank"
              rel="noreferrer"
              className="hover:text-background transition-colors"
            >
              Политика конфиденциальности
            </a>
            <a
              href="/legal/cookie-policy.pdf"
              target="_blank"
              rel="noreferrer"
              className="hover:text-background transition-colors"
            >
              Cookies
            </a>
            <a
              href="/legal/offer-user-agreement.pdf"
              target="_blank"
              rel="noreferrer"
              className="hover:text-background transition-colors"
            >
              Оферта / Пользовательское соглашение
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
