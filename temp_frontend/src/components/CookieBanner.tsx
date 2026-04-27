import { useEffect, useMemo, useState } from "react";

const SESSION_CONSENT_KEY = "tendrix_cookie_consent_session";
const CONSENT_VALUE_ACCEPTED = "accepted";
const ACCESS_TOKEN_KEY = "access_token";

type CookieBannerProps = {
  className?: string;
};

export default function CookieBanner({ className }: CookieBannerProps) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    try {
      const token = localStorage.getItem(ACCESS_TOKEN_KEY);
      if (token) {
        setIsVisible(false);
        return;
      }

      const v = sessionStorage.getItem(SESSION_CONSENT_KEY);
      setIsVisible(v !== CONSENT_VALUE_ACCEPTED);
    } catch {
      // If storage is blocked, still show banner until user accepts in-session.
      setIsVisible(true);
    }
  }, []);

  const accept = () => {
    try {
      sessionStorage.setItem(SESSION_CONSENT_KEY, CONSENT_VALUE_ACCEPTED);
    } catch {
      // Ignore: banner will still hide for current session.
    }
    setIsVisible(false);
  };

  const wrapperClassName = useMemo(() => {
    const base =
      "fixed inset-x-0 bottom-0 z-50 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80";
    return className ? `${base} ${className}` : base;
  }, [className]);

  if (!isVisible) return null;

  return (
    <div className={wrapperClassName}>
      <div className="container py-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="text-sm text-foreground/80">
            Мы используем cookies для работы сайта и улучшения сервиса. Подробнее —{" "}
            <a
              href="/legal/cookie-policy.pdf"
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-4 hover:text-foreground"
            >
              политика cookies
            </a>
            .
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={accept}
              className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Принять
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

