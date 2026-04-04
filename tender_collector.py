"""
Система для сбора тендеров и закупок с 20-30 площадок
Поддерживает ЕИС, ЭТП, региональные порталы и коммерческие площадки
"""

import requests
from bs4 import BeautifulSoup
import feedparser
from datetime import datetime
import json
from typing import List, Dict, Optional
import time
import re

class TenderCollector:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        self.tender_sources = []
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def add_source(self, name: str, url: str, parser_type: str = 'html', 
                   category: str = 'other', rss_url: str = None, 
                   selectors: Dict = None):
        """
        Добавить источник тендеров
        
        Args:
            name: Название источника
            url: URL сайта
            parser_type: 'rss', 'html', 'api', 'custom'
            category: 'eis', 'etp', 'regional', 'commercial', 'corporate', 'small'
            rss_url: URL RSS фида (если есть)
            selectors: CSS селекторы для парсинга (для HTML)
        """
        self.tender_sources.append({
            'name': name,
            'url': url,
            'parser_type': parser_type,
            'category': category,
            'rss_url': rss_url,
            'selectors': selectors or {}
        })
    
    def load_sources_from_config(self, config_file: str = 'tenders_config.json'):
        """Загрузить источники из JSON файла конфигурации"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                for source in config.get('sources', []):
                    self.add_source(
                        source['name'],
                        source['url'],
                        source.get('parser_type', 'html'),
                        source.get('category', 'other'),
                        source.get('rss_url'),
                        source.get('selectors', {})
                    )
            print(f"Загружено {len(config.get('sources', []))} источников из {config_file}")
        except FileNotFoundError:
            print(f"Файл конфигурации {config_file} не найден.")
        except Exception as e:
            print(f"Ошибка при загрузке конфигурации: {e}")
    
    def parse_rss_tenders(self, source: Dict) -> List[Dict]:
        """Парсинг тендеров из RSS/Atom фида"""
        try:
            if not source.get('rss_url'):
                return []
            
            feed = feedparser.parse(source['rss_url'])
            tenders = []
            
            for entry in feed.entries[:20]:  # Берем последние 20
                tender = {
                    'source': source['name'],
                    'category': source['category'],
                    'number': self._extract_tender_number(entry.get('title', '')),
                    'title': entry.get('title', 'Без названия'),
                    'link': entry.get('link', ''),
                    'description': entry.get('description', ''),
                    'published': entry.get('published', ''),
                    'price': self._extract_price(entry.get('description', '')),
                    'deadline': self._extract_deadline(entry.get('description', '')),
                    'customer': self._extract_customer(entry.get('description', '')),
                    'timestamp': datetime.now().isoformat()
                }
                tenders.append(tender)
            
            return tenders
        except Exception as e:
            print(f"Ошибка при парсинге RSS {source['name']}: {e}")
            return []
    
    def parse_html_tenders(self, source: Dict) -> List[Dict]:
        """Парсинг тендеров из HTML (универсальный метод)"""
        try:
            response = self.session.get(source['url'], timeout=15)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.content, 'html.parser')
            tenders = []
            
            selectors = source.get('selectors', {})
            
            # Универсальный поиск тендеров
            tender_containers = []
            
            # Попытка найти по кастомным селекторам
            if selectors.get('container'):
                tender_containers = soup.select(selectors['container'])
            
            # Если не нашли, пробуем разные варианты
            if not tender_containers:
                # Ищем по классам
                patterns = [
                    ('tr', lambda x: x and any(word in x.lower() for word in ['tender', 'lot', 'purchase', 'auction', 'zakup', 'zayav'])),
                    ('div', lambda x: x and any(word in x.lower() for word in ['tender', 'lot', 'purchase', 'auction', 'zakup', 'zayav', 'item', 'card'])),
                    ('li', lambda x: x and any(word in x.lower() for word in ['tender', 'lot', 'purchase', 'auction', 'zakup'])),
                    ('article', lambda x: x and any(word in x.lower() for word in ['tender', 'lot', 'purchase', 'auction'])),
                ]
                
                for tag, class_filter in patterns:
                    found = soup.find_all(tag, class_=class_filter)
                    if found:
                        tender_containers = found[:30]
                        break
                
                # Если все еще не нашли, берем все ссылки с ключевыми словами
                if not tender_containers:
                    links = soup.find_all('a', href=True)
                    for link in links[:50]:
                        href = link.get('href', '').lower()
                        text = link.get_text(strip=True)
                        if any(word in href or word in text.lower() for word in ['tender', 'lot', 'purchase', 'auction', 'zakup', 'zayav', 'тендер', 'лот', 'закуп']):
                            # Берем родительский элемент
                            parent = link.find_parent(['tr', 'div', 'li', 'article', 'td'])
                            if parent and parent not in tender_containers:
                                tender_containers.append(parent)
                                if len(tender_containers) >= 30:
                                    break
            
            # Ограничиваем количество
            for container in tender_containers[:30]:
                tender = self._extract_tender_from_element(container, source, selectors)
                if tender and tender.get('title') and tender.get('title') not in [t.get('title') for t in tenders]:
                    tenders.append(tender)
            
            return tenders
        except Exception as e:
            print(f"Ошибка при парсинге HTML {source['name']}: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _extract_tender_from_element(self, element, source: Dict, selectors: Dict) -> Optional[Dict]:
        """Извлечь данные тендера из HTML элемента"""
        try:
            selectors = selectors or {}
            
            # Извлечение заголовка
            title = ''
            if selectors.get('title'):
                title_elem = element.select_one(selectors['title'])
            else:
                title_elem = (
                    element.find(['h1', 'h2', 'h3', 'h4']) or
                    element.find('a', class_=lambda x: x and ('title' in x.lower() or 'name' in x.lower())) or
                    element.find('td', class_=lambda x: x and ('title' in x.lower() or 'name' in x.lower())) or
                    element.find('a')
                )
            
            if title_elem:
                title = title_elem.get_text(strip=True)
            
            # Фильтрация некорректных заголовков
            if not title or len(title) < 5:
                return None
            
            # Пропускаем email адреса и короткие тексты
            if '@' in title or title.lower().startswith('http') or len(title) < 10:
                return None
            
            # Извлечение ссылки
            link = ''
            if selectors.get('link'):
                link_elem = element.select_one(selectors['link'])
            else:
                # Ищем ссылку более тщательно
                link_elem = (
                    element.find('a', href=True, class_=lambda x: x and ('tender' in x.lower() or 'lot' in x.lower() or 'purchase' in x.lower())) or
                    element.find('a', href=lambda x: x and ('tender' in x.lower() or 'lot' in x.lower() or 'purchase' in x.lower() or 'auction' in x.lower())) or
                    element.find('a', href=True)
                )
            
            if link_elem:
                link = link_elem.get('href', '')
                if link:
                    from urllib.parse import urlparse, urljoin
                    
                    # Обработка относительных ссылок
                    if link.startswith('//'):
                        link = 'https:' + link
                    elif link.startswith('/'):
                        parsed = urlparse(source['url'])
                        link = f"{parsed.scheme}://{parsed.netloc}{link}"
                    elif not link.startswith('http'):
                        link = urljoin(source['url'], link)
                    
                    # Нормализуем URL
                    parsed_link = urlparse(link)
                    parsed_source = urlparse(source['url'])
                    
                    # Проверяем, что это не главная страница
                    link_path = parsed_link.path.rstrip('/')
                    source_path = parsed_source.path.rstrip('/')
                    
                    # Если ссылка ведет на главную или очень похожа на главную - не показываем
                    if (parsed_link.netloc == parsed_source.netloc and 
                        (link_path == '' or link_path == '/' or link_path == source_path)):
                        link = ''
                    
                    # Также проверяем, что в ссылке есть признаки конкретной страницы
                    if link and not any(word in link.lower() for word in ['tender', 'lot', 'purchase', 'auction', 'zakup', 'zayav', 'id=', 'view=', 'detail', 'page=', 'item=']):
                        # Если ссылка слишком простая - возможно это не страница тендера
                        if len(link_path.split('/')) < 3:  # Например, /tenders/123 - это хорошо, но /tenders - плохо
                            link = ''
            
            # Извлечение номера
            number = self._extract_tender_number(title + ' ' + element.get_text())
            
            # Извлечение цены
            price = ''
            if selectors.get('price'):
                price_elem = element.select_one(selectors['price'])
                if price_elem:
                    price = price_elem.get_text(strip=True)
            else:
                price = self._extract_price(element.get_text())
            
            # Извлечение заказчика
            customer = ''
            if selectors.get('customer'):
                customer_elem = element.select_one(selectors['customer'])
                if customer_elem:
                    customer = customer_elem.get_text(strip=True)
            else:
                customer = self._extract_customer(element.get_text())
            
            # Извлечение дедлайна
            deadline = ''
            if selectors.get('deadline'):
                deadline_elem = element.select_one(selectors['deadline'])
                if deadline_elem:
                    deadline = deadline_elem.get_text(strip=True)
            else:
                deadline = self._extract_deadline(element.get_text())
            
            # Фильтруем элементы, которые явно не являются тендерами
            # Но если есть хотя бы название и источник - оставляем
            if not title or len(title) < 10:
                return None
            
            # Если нет ссылки, но есть другие данные - оставляем, но без ссылки
            # (некоторые сайты могут не давать прямых ссылок)
            
            return {
                'source': source['name'],
                'category': source['category'],
                'number': number,
                'title': title[:200] if len(title) > 200 else title,  # Ограничиваем длину
                'link': link if link and link != source['url'] else '',  # Не показываем ссылку на главную
                'description': '',
                'published': '',
                'price': price,
                'deadline': deadline,
                'customer': customer[:100] if customer and len(customer) > 100 else customer,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return None
    
    def _extract_tender_number(self, text: str) -> str:
        """Извлечь номер тендера из текста"""
        # Паттерны для номеров тендеров
        patterns = [
            r'№\s*(\d+[-\d]*)',
            r'№\s*([А-Я]{2,}\d+[-\d]*)',
            r'(\d{13,})',  # 13-значные номера ЕИС
            r'([А-Я]{2,}\d+[-\d]*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return ''
    
    def _extract_price(self, text: str) -> str:
        """Извлечь цену из текста"""
        # Паттерны для цен
        patterns = [
            r'(\d[\d\s]*[,.]?\d*)\s*(?:руб|₽|RUB)',
            r'(\d[\d\s]*[,.]?\d*)\s*(?:млн|млрд)',
            r'цена[:\s]+(\d[\d\s]*[,.]?\d*)',
            r'начальная[:\s]+цена[:\s]+(\d[\d\s]*[,.]?\d*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip() + ' руб.'
        
        return ''
    
    def _extract_customer(self, text: str) -> str:
        """Извлечь заказчика из текста"""
        # Простой поиск по ключевым словам
        patterns = [
            r'заказчик[:\s]+([А-Я][А-Яа-я\s]{10,50})',
            r'организатор[:\s]+([А-Я][А-Яа-я\s]{10,50})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:100]
        
        return ''
    
    def _extract_deadline(self, text: str) -> str:
        """Извлечь дедлайн из текста"""
        # Паттерны для дат
        patterns = [
            r'(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
            r'(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4})',
            r'срок[:\s]+(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
            r'до[:\s]+(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return ''
    
    def collect_all_tenders(self) -> List[Dict]:
        """Собрать все тендеры со всех источников"""
        all_tenders = []
        
        print(f"\n{'='*80}")
        print(f"Начинаю сбор тендеров из {len(self.tender_sources)} источников...")
        print(f"{'='*80}\n")
        
        for i, source in enumerate(self.tender_sources, 1):
            print(f"[{i}/{len(self.tender_sources)}] Обрабатываю {source['name']} ({source['category']})...")
            
            try:
                if source['parser_type'] == 'rss':
                    tenders = self.parse_rss_tenders(source)
                elif source['parser_type'] == 'html':
                    tenders = self.parse_html_tenders(source)
                else:
                    tenders = []
                
                if tenders:
                    print(f"  [OK] Найдено тендеров: {len(tenders)}")
                    all_tenders.extend(tenders)
                else:
                    print(f"  [--] Тендеры не найдены")
                
            except Exception as e:
                print(f"  [ERROR] Ошибка: {e}")
            
            time.sleep(2)  # Задержка между запросами
        
        # Сортируем по дате публикации
        all_tenders.sort(key=lambda x: x.get('published', '') or x.get('timestamp', ''), reverse=True)
        
        print(f"\n{'='*80}")
        print(f"Всего собрано тендеров: {len(all_tenders)}")
        print(f"{'='*80}\n")
        
        return all_tenders
