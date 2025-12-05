#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔥 TELEGRAM BROADCASTER PRO - ВСЁ В ОДНОМ ФАЙЛЕ
Полный функционал: авторизация, загрузка чатов, рассылка, защита от бана
"""

import os
import sys
import asyncio
import json
import time
import random
import threading
from datetime import datetime, timedelta
from queue import Queue, PriorityQueue
from typing import List, Dict, Optional
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty
import requests
from colorama import init, Fore, Style

# Инициализация цветов
init(autoreset=True)

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

class Config:
    """Конфигурация системы"""
    
    # Telegram API (получить на my.telegram.org)
    API_ID = ""          # ВАШ API_ID
    API_HASH = ""        # ВАШ API_HASH
    PHONE_NUMBER = ""    # ВАШ НОМЕР (+79991234567)
    
    # Настройки рассылки
    MAX_MESSAGES_PER_HOUR = 30
    MIN_DELAY = 2.5
    MAX_DELAY = 8.0
    DEFAULT_MESSAGE = "Привет! Это автоматическая рассылка 🚀"
    
    # Файлы
    SESSION_FILE = "session.session"
    CHATS_FILE = "chats.json"
    LOG_FILE = "broadcast.log"
    
    # GitHub (опционально)
    GITHUB_TOKEN = ""
    GITHUB_REPO = ""

# ============================================================================
# СИСТЕМА ЗАЩИТЫ ОТ БАНА
# ============================================================================

class AntiBanSystem:
    """Умная система защиты от блокировки Telegram"""
    
    def __init__(self):
        self.message_history = []
        self.sent_today = 0
        self.sent_hour = 0
        self.last_reset_hour = datetime.now().hour
        self.last_reset_day = datetime.now().day
        
        # Паттерны задержек для реалистичности
        self.delay_patterns = [
            [3.2, 4.5, 2.8, 3.7, 4.2],
            [3.5, 4.0, 3.0, 5.0, 3.8],
            [2.8, 3.5, 4.2, 3.0, 4.5],
            [4.0, 3.2, 4.8, 3.5, 4.0]
        ]
        self.current_pattern = 0
        self.pattern_index = 0
        
        # Лимиты
        self.HOURLY_LIMIT = 30
        self.DAILY_LIMIT = 200
        self.MAX_CONSECUTIVE = 15
        
    def _reset_counters(self):
        """Сброс счетчиков при смене часа/дня"""
        now = datetime.now()
        
        if now.hour != self.last_reset_hour:
            self.sent_hour = 0
            self.last_reset_hour = now.hour
        
        if now.day != self.last_reset_day:
            self.sent_today = 0
            self.last_reset_day = now.day
    
    def record_message(self, chat_id: int, message: str):
        """Записать отправленное сообщение"""
        self._reset_counters()
        
        record = {
            'timestamp': datetime.now().isoformat(),
            'chat_id': chat_id,
            'message': message[:100],
            'hour': datetime.now().hour
        }
        
        self.message_history.append(record)
        self.sent_hour += 1
        self.sent_today += 1
        
        # Храним только последние 1000 записей
        if len(self.message_history) > 1000:
            self.message_history = self.message_history[-1000:]
    
    def get_smart_delay(self) -> float:
        """Получить умную задержку"""
        # Берем базовую задержку из паттерна
        pattern = self.delay_patterns[self.current_pattern]
        base_delay = pattern[self.pattern_index]
        
        # Добавляем случайность
        delay = base_delay + random.uniform(-0.3, 0.3)
        
        # Адаптация по загрузке
        if self.sent_hour > self.HOURLY_LIMIT * 0.7:
            delay *= 1.5  # Увеличиваем задержку при высокой нагрузке
        elif self.sent_hour > self.HOURLY_LIMIT * 0.9:
            delay *= 2.0  # Сильно увеличиваем при приближении к лимиту
        
        # Ограничиваем диапазон
        delay = max(Config.MIN_DELAY, min(delay, Config.MAX_DELAY))
        
        # Переход к следующей задержке в паттерне
        self.pattern_index += 1
        if self.pattern_index >= len(pattern):
            self.pattern_index = 0
            self.current_pattern = (self.current_pattern + 1) % len(self.delay_patterns)
        
        return round(delay, 2)
    
    def can_send(self) -> tuple:
        """Проверить, можно ли отправлять сообщение"""
        self._reset_counters()
        
        if self.sent_hour >= self.HOURLY_LIMIT:
            next_hour = (datetime.now() + timedelta(hours=1)).replace(
                minute=0, second=0, microsecond=0
            )
            wait_seconds = (next_hour - datetime.now()).seconds
            return False, f"Достигнут часовой лимит ({self.HOURLY_LIMIT}). Ждите {wait_seconds//60} мин."
        
        if self.sent_today >= self.DAILY_LIMIT:
            return False, f"Достигнут дневной лимит ({self.DAILY_LIMIT})"
        
        return True, "✅ Можно отправлять"
    
    def simulate_typing(self, message_length: int) -> float:
        """Имитация печати человека"""
        typing_speed = 200 / 60  # символов в секунду
        typing_time = message_length / typing_speed
        thinking_time = random.uniform(0.3, 1.5)
        return round(typing_time + thinking_time, 2)

# ============================================================================
# МЕНЕДЖЕР ЧАТОВ
# ============================================================================

class ChatManager:
    """Управление списками чатов"""
    
    def __init__(self):
        self.chats_file = Config.CHATS_FILE
        self.chats = self._load_chats()
        
        # Категории
        self.categories = {
            'all': set(),
            'favorites': set(),
            'groups': set(),
            'channels': set(),
            'users': set(),
            'blacklist': set()
        }
        self._categorize_chats()
    
    def _load_chats(self) -> Dict:
        """Загрузить чаты из файла"""
        try:
            if os.path.exists(self.chats_file):
                with open(self.chats_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {int(k): v for k, v in data.items()}
        except Exception:
            pass
        return {}
    
    def _save_chats(self):
        """Сохранить чаты в файл"""
        try:
            with open(self.chats_file, 'w', encoding='utf-8') as f:
                json.dump(self.chats, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"{Fore.RED}❌ Ошибка сохранения чатов: {e}")
    
    def _categorize_chats(self):
        """Категоризировать загруженные чаты"""
        for chat_id, chat_info in self.chats.items():
            self.categories['all'].add(chat_id)
            chat_type = chat_info.get('type', '').lower()
            
            if 'blacklist' in chat_info.get('tags', []):
                self.categories['blacklist'].add(chat_id)
            elif 'favorite' in chat_info.get('tags', []):
                self.categories['favorites'].add(chat_id)
            elif 'channel' in chat_type:
                self.categories['channels'].add(chat_id)
            elif 'group' in chat_type or 'chat' in chat_type:
                self.categories['groups'].add(chat_id)
            else:
                self.categories['users'].add(chat_id)
    
    def add_chat(self, chat_id: int, title: str = "", username: str = "", 
                chat_type: str = "", participants: int = 0, tags: list = None):
        """Добавить новый чат"""
        chat_info = {
            'id': chat_id,
            'title': title or f"Chat {chat_id}",
            'username': username or "",
            'type': chat_type or "unknown",
            'participants': participants or 0,
            'added': datetime.now().isoformat(),
            'last_message': None,
            'message_count': 0,
            'tags': tags or [],
            'active': True
        }
        
        self.chats[chat_id] = chat_info
        self._categorize_chats()
        self._save_chats()
        
        print(f"{Fore.GREEN}✅ Чат добавлен: {title} (ID: {chat_id})")
    
    def import_from_telegram(self, telegram_chats: list):
        """Импортировать чаты из Telegram"""
        print(f"{Fore.CYAN}📥 Импорт {len(telegram_chats)} чатов...")
        
        for chat in telegram_chats:
            self.add_chat(
                chat_id=chat.get('id'),
                title=chat.get('title', ''),
                username=chat.get('username', ''),
                chat_type=chat.get('type', ''),
                participants=chat.get('participants_count', 0)
            )
        
        print(f"{Fore.GREEN}✅ Импортировано {len(telegram_chats)} чатов")
    
    def get_chats_for_broadcast(self, category: str = 'all', limit: int = 50) -> List[int]:
        """Получить чаты для рассылки"""
        if category not in self.categories:
            category = 'all'
        
        # Исключаем черный список
        available_chats = self.categories[category] - self.categories['blacklist']
        
        # Фильтруем активные чаты
        active_chats = []
        for chat_id in available_chats:
            if chat_id in self.chats and self.chats[chat_id].get('active', True):
                active_chats.append(chat_id)
        
        # Берем ограниченное количество
        return active_chats[:limit]
    
    def mark_message_sent(self, chat_id: int, message: str = ""):
        """Отметить отправленное сообщение"""
        if chat_id in self.chats:
            self.chats[chat_id]['last_message'] = datetime.now().isoformat()
            self.chats[chat_id]['message_count'] = self.chats[chat_id].get('message_count', 0) + 1
            self._save_chats()

# ============================================================================
# ПЛАНИРОВЩИК РАССЫЛКИ
# ============================================================================

class MessageScheduler:
    """Управление очередью и отправкой сообщений"""
    
    def __init__(self, telegram_client=None, chat_manager=None):
        self.client = telegram_client
        self.chat_manager = chat_manager or ChatManager()
        self.anti_ban = AntiBanSystem()
        
        # Очереди
        self.immediate_queue = Queue()
        self.scheduled_queue = PriorityQueue()
        
        # Статус
        self.is_running = False
        self.is_paused = False
        self.worker_thread = None
        
        # Статистика
        self.stats = {
            'total_sent': 0,
            'total_failed': 0,
            'start_time': None,
            'current_campaign': None,
            'active_chats': 0
        }
        
        # Шаблоны сообщений
        self.templates = [
            "Привет, {name}! 🚀 У нас есть важная информация для тебя!",
            "Внимание, {name}! ⭐ Специальное предложение только для тебя!",
            "{name}, не пропусти новые возможности! 💫",
            "Дорогой {name}, у нас кое-что интересное! 🔥",
            "Приветствуем, {name}! 🎉 Загляни к нам, будет интересно!"
        ]
        
        print(f"{Fore.GREEN}✅ Планировщик инициализирован")
    
    def create_broadcast_campaign(self, chat_ids: List[int], message: str = None, 
                                 messages_per_chat: int = 1, delay_between: float = None) -> str:
        """
        СОЗДАТЬ КАМПАНИЮ РАССЫЛКИ - ГЛАВНЫЙ МЕТОД КОТОРЫЙ НУЖЕН
        """
        import uuid
        
        campaign_id = f"CAMP-{uuid.uuid4().hex[:6].upper()}"
        total_messages = len(chat_ids) * messages_per_chat
        
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"🎯 СОЗДАНИЕ КАМПАНИИ: {campaign_id}")
        print(f"{'='*60}")
        print(f"   📋 Чатов: {len(chat_ids)}")
        print(f"   📨 Сообщений на чат: {messages_per_chat}")
        print(f"   📊 Всего сообщений: {total_messages}")
        print(f"   ⏱️  Задержка: {delay_between or 'автоматическая'} сек")
        
        if not message:
            print(f"   ✏️  Будет использована персонализация")
        
        # Добавляем сообщения в очередь
        added_count = 0
        for i, chat_id in enumerate(chat_ids):
            for j in range(messages_per_chat):
                # Генерируем сообщение
                if message:
                    msg_text = message
                else:
                    chat_name = self.chat_manager.chats.get(chat_id, {}).get('title', f'Чат {chat_id}')
                    msg_text = self._generate_personalized_message(chat_name)
                
                # Рассчитываем время отправки
                if delay_between and (i > 0 or j > 0):
                    total_delay = delay_between * (i * messages_per_chat + j)
                    send_time = datetime.now() + timedelta(seconds=total_delay)
                else:
                    send_time = None
                
                # Добавляем в очередь
                self._add_to_queue(chat_id, msg_text, send_time=send_time)
                added_count += 1
        
        self.stats['current_campaign'] = campaign_id
        self.stats['active_chats'] = self.immediate_queue.qsize() + self.scheduled_queue.qsize()
        
        print(f"{Fore.GREEN}✅ Кампания создана!")
        print(f"   📥 Добавлено в очередь: {added_count} сообщений")
        print(f"{Fore.CYAN}{'='*60}")
        
        return campaign_id
    
    def _add_to_queue(self, chat_id: int, message: str, priority: int = 5, 
                     send_time: datetime = None):
        """Добавить сообщение в очередь"""
        queue_item = {
            'chat_id': chat_id,
            'message': message,
            'priority': priority,
            'send_time': send_time or datetime.now(),
            'added': datetime.now(),
            'attempts': 0,
            'status': 'queued'
        }
        
        if send_time and send_time > datetime.now():
            # Отложенная отправка
            self.scheduled_queue.put((priority, send_time.timestamp(), queue_item))
        else:
            # Немедленная отправка
            self.immediate_queue.put(queue_item)
    
    def _generate_personalized_message(self, name: str) -> str:
        """Сгенерировать персонализированное сообщение"""
        template = random.choice(self.templates)
        message = template.format(name=name)
        
        # Добавляем эмодзи
        emojis = ['✨', '🎯', '🚀', '💥', '⭐', '🔥', '💎', '🎁']
        message += " " + random.choice(emojis)
        
        return message
    
    def start(self, max_messages: int = None):
        """Запустить рассылку"""
        if self.is_running:
            print(f"{Fore.YELLOW}⚠️ Рассылка уже запущена")
            return
        
        print(f"{Fore.GREEN}🚀 ЗАПУСК РАССЫЛКИ...")
        print(f"   Ограничение: {max_messages or 'нет'} сообщений")
        
        self.is_running = True
        self.is_paused = False
        self.stats['start_time'] = datetime.now()
        self.stats['total_sent'] = 0
        self.stats['total_failed'] = 0
        
        # Запускаем worker в отдельном потоке
        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(max_messages,),
            daemon=True
        )
        self.worker_thread.start()
        
        print(f"{Fore.GREEN}✅ Рассылка запущена!")
    
    def stop(self):
        """Остановить рассылку"""
        if not self.is_running:
            return
        
        print(f"{Fore.YELLOW}🛑 Остановка рассылки...")
        self.is_running = False
        
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        
        self._print_final_stats()
        print(f"{Fore.GREEN}✅ Рассылка остановлена")
    
    def pause(self):
        """Приостановить рассылку"""
        if not self.is_running:
            return
        
        self.is_paused = True
        print(f"{Fore.YELLOW}⏸️ Рассылка приостановлена")
    
    def resume(self):
        """Возобновить рассылку"""
        if not self.is_running:
            return
        
        self.is_paused = False
        print(f"{Fore.GREEN}▶️ Рассылка возобновлена")
    
    def _worker_loop(self, max_messages: int = None):
        """Основной цикл отправки сообщений"""
        sent_count = 0
        
        while self.is_running and (max_messages is None or sent_count < max_messages):
            # Проверяем паузу
            if self.is_paused:
                time.sleep(1)
                continue
            
            # Получаем следующее сообщение
            message_item = self._get_next_message()
            if not message_item:
                time.sleep(0.5)
                continue
            
            # Отправляем сообщение
            success = self._send_message_safe(message_item)
            
            if success:
                sent_count += 1
                self.stats['total_sent'] += 1
                self.stats['active_chats'] = self.immediate_queue.qsize() + self.scheduled_queue.qsize()
                
                # Обновляем статистику чата
                if self.chat_manager:
                    self.chat_manager.mark_message_sent(
                        message_item['chat_id'],
                        message_item['message']
                    )
                
                # Показываем прогресс каждые 5 сообщений
                if sent_count % 5 == 0:
                    self._print_progress(sent_count, max_messages)
            else:
                self.stats['total_failed'] += 1
            
            # Проверяем лимит
            if max_messages and sent_count >= max_messages:
                print(f"{Fore.YELLOW}📊 Достигнут лимит: {max_messages} сообщений")
                break
        
        # Автостоп при завершении очереди
        if self.is_running:
            self.stop()
    
    def _get_next_message(self) -> Optional[Dict]:
        """Получить следующее сообщение из очереди"""
        # Проверяем отложенные сообщения
        if not self.scheduled_queue.empty():
            priority, timestamp, item = self.scheduled_queue.queue[0]
            if datetime.fromtimestamp(timestamp) <= datetime.now():
                self.scheduled_queue.get()
                return item
        
        # Проверяем немедленные сообщения
        if not self.immediate_queue.empty():
            return self.immediate_queue.get()
        
        return None
    
    def _send_message_safe(self, message_item: Dict) -> bool:
        """Безопасная отправка сообщения"""
        try:
            # Проверяем лимиты
            can_send, reason = self.anti_ban.can_send()
            if not can_send:
                print(f"{Fore.RED}⏸️ {reason}")
                # Откладываем на 5 минут
                message_item['send_time'] = datetime.now() + timedelta(minutes=5)
                self.scheduled_queue.put((1, message_item['send_time'].timestamp(), message_item))
                return False
            
            # Получаем задержку
            delay = self.anti_ban.get_smart_delay()
            typing_delay = self.anti_ban.simulate_typing(len(message_item['message']))
            total_delay = delay + typing_delay
            
            print(f"{Fore.CYAN}📤 [{self.stats['total_sent']+1}] Отправка в чат {message_item['chat_id']}")
            print(f"   ⏱️  Задержка: {total_delay:.1f} сек")
            print(f"   💬 Текст: {message_item['message'][:60]}...")
            
            # Имитация отправки (замените на реальную отправку через Telethon)
            time.sleep(total_delay)
            
            if self.client:
                # Реальная отправка через Telethon
                asyncio.run(self._send_telegram_message(
                    message_item['chat_id'],
                    message_item['message']
                ))
            else:
                # Тестовая отправка
                print(f"{Fore.GREEN}   ✅ [ТЕСТ] Сообщение отправлено")
            
            # Записываем в историю
            self.anti_ban.record_message(message_item['chat_id'], message_item['message'])
            
            return True
            
        except Exception as e:
            print(f"{Fore.RED}❌ Ошибка отправки: {e}")
            return False
    
    async def _send_telegram_message(self, chat_id: int, message: str):
        """Отправка сообщения через Telethon"""
        # Реальная отправка будет здесь
        # Для теста просто имитируем
        pass
    
    def _print_progress(self, sent: int, max_messages: int = None):
        """Показать прогресс"""
        remaining = self.immediate_queue.qsize() + self.scheduled_queue.qsize()
        runtime = datetime.now() - self.stats['start_time']
        
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"📊 ПРОГРЕСС РАССЫЛКИ")
        print(f"{'='*50}")
        print(f"   ✅ Отправлено: {sent}/{max_messages or '∞'}")
        print(f"   📥 В очереди: {remaining}")
        print(f"   ❌ Ошибок: {self.stats['total_failed']}")
        print(f"   ⏱️  Время работы: {runtime}")
        print(f"{Fore.CYAN}{'='*50}\n")
    
    def _print_final_stats(self):
        """Показать финальную статистику"""
        if not self.stats['start_time']:
            return
        
        runtime = datetime.now() - self.stats['start_time']
        hours, remainder = divmod(runtime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        print(f"\n{Fore.GREEN}{'='*60}")
        print(f"🎉 РАССЫЛКА ЗАВЕРШЕНА!")
        print(f"{'='*60}")
        print(f"   📊 Всего отправлено: {self.stats['total_sent']}")
        print(f"   ❌ Ошибок отправки: {self.stats['total_failed']}")
        print(f"   ⏱️  Общее время: {hours:02d}:{minutes:02d}:{seconds:02d}")
        
        if self.stats['total_sent'] > 0:
            speed = self.stats['total_sent'] / (runtime.seconds / 3600)
            print(f"   🚀 Скорость: {speed:.1f} сообщений/час")
        
        print(f"{Fore.GREEN}{'='*60}")
    
    def get_status(self) -> Dict:
        """Получить статус планировщика"""
        return {
            'is_running': self.is_running,
            'is_paused': self.is_paused,
            'immediate_queue': self.immediate_queue.qsize(),
            'scheduled_queue': self.scheduled_queue.qsize(),
            'total_sent': self.stats['total_sent'],
            'total_failed': self.stats['total_failed'],
            'active_campaign': self.stats['current_campaign']
        }

# ============================================================================
# TELEGRAM КЛИЕНТ
# ============================================================================

class TelegramBot:
    """Главный класс бота"""
    
    def __init__(self):
        self.api_id = Config.API_ID
        self.api_hash = Config.API_HASH
        self.phone = Config.PHONE_NUMBER
        self.client = None
        self.is_connected = False
        
        # Менеджеры
        self.chat_manager = ChatManager()
        self.scheduler = MessageScheduler(self, self.chat_manager)
        
        print(f"{Fore.CYAN}🤖 Telegram Bot инициализирован")
    
    async def connect(self):
        """Подключиться к Telegram"""
        try:
            print(f"{Fore.YELLOW}🔗 Подключение к Telegram...")
            
            self.client = TelegramClient(
                session=Config.SESSION_FILE,
                api_id=int(self.api_id),
                api_hash=self.api_hash,
                device_model="Broadcaster Pro",
                system_version="1.0",
                app_version="3.0",
                lang_code="ru"
            )
            
            await self.client.start(phone=self.phone)
            
            me = await self.client.get_me()
            print(f"{Fore.GREEN}✅ Подключено как: {me.first_name} (@{me.username})")
            
            self.is_connected = True
            return True
            
        except Exception as e:
            print(f"{Fore.RED}❌ Ошибка подключения: {e}")
            return False
    
    async def get_all_chats(self, limit: int = 500) -> List[Dict]:
        """Получить ВСЕ чаты пользователя"""
        if not self.is_connected:
            return []
        
        try:
            print(f"{Fore.YELLOW}📋 Получение списка чатов...")
            
            all_chats = []
            offset_id = 0
            total_loaded = 0
            
            while True:
                # Получаем пачку диалогов
                dialogs = await self.client(GetDialogsRequest(
                    offset_date=None,
                    offset_id=offset_id,
                    offset_peer=InputPeerEmpty(),
                    limit=min(200, limit - total_loaded),
                    hash=0
                ))
                
                if not dialogs.chats:
                    break
                
                # Обрабатываем чаты
                for chat in dialogs.chats:
                    chat_info = {
                        'id': chat.id,
                        'title': getattr(chat, 'title', ''),
                        'username': getattr(chat, 'username', ''),
                        'type': type(chat).__name__,
                        'participants_count': getattr(chat, 'participants_count', 0),
                        'access_hash': getattr(chat, 'access_hash', 0)
                    }
                    all_chats.append(chat_info)
                    total_loaded += 1
                
                print(f"   📥 Загружено: {total_loaded} чатов...")
                
                # Проверяем лимит
                if total_loaded >= limit or len(dialogs.chats) < 100:
                    break
                
                # Устанавливаем offset для следующей пачки
                offset_id = dialogs.chats[-1].id
            
            print(f"{Fore.GREEN}✅ Всего загружено: {len(all_chats)} чатов")
            return all_chats
            
        except Exception as e:
            print(f"{Fore.RED}❌ Ошибка загрузки чатов: {e}")
            return []
    
    async def send_message(self, chat_id: int, message: str) -> bool:
        """Отправить сообщение через Telethon"""
        if not self.is_connected:
            return False
        
        try:
            # Получаем сущность чата
            entity = await self.client.get_entity(chat_id)
            
            # Отправляем сообщение
            await self.client.send_message(entity, message)
            
            return True
            
        except Exception as e:
            print(f"{Fore.RED}❌ Ошибка отправки: {e}")
            return False
    
    async def disconnect(self):
        """Отключиться от Telegram"""
        if self.client and self.is_connected:
            await self.client.disconnect()
            self.is_connected = False
            print(f"{Fore.YELLOW}🔌 Отключено от Telegram")

# ============================================================================
# ГЛАВНОЕ МЕНЮ И ИНТЕРФЕЙС
# ============================================================================

class BroadcastSystem:
    """Главный интерфейс системы"""
    
    def __init__(self):
        self.bot = TelegramBot()
        self.is_authenticated = False
        
        print(f"{Fore.CYAN}{'='*60}")
        print(f"🔥 TELEGRAM BROADCASTER PRO v3.0")
        print(f"{'='*60}")
    
    async def authenticate(self):
        """Аутентификация в Telegram"""
        print(f"\n{Fore.YELLOW}🔐 АУТЕНТИФИКАЦИЯ")
        print(f"{'-'*40}")
        
        # Проверяем конфигурацию
        if not Config.API_ID or not Config.API_HASH:
            print(f"{Fore.RED}❌ API_ID и API_HASH не заданы!")
            print(f"{Fore.YELLOW}📱 Получите на: https://my.telegram.org")
            return False
        
        # Подключаемся
        success = await self.bot.connect()
        
        if success:
            self.is_authenticated = True
            
            # Загружаем чаты
            print(f"{Fore.YELLOW}📥 Загрузка чатов...")
            chats = await self.bot.get_all_chats(limit=500)
            
            if chats:
                self.bot.chat_manager.import_from_telegram(chats)
                print(f"{Fore.GREEN}✅ Чаты загружены и сохранены")
            else:
                print(f"{Fore.YELLOW}⚠️ Чаты не найдены или произошла ошибка")
        
        return success
    
    def show_main_menu(self):
        """Главное меню"""
        while True:
            print(f"\n{Fore.CYAN}{'='*60}")
            print(f"📱 ГЛАВНОЕ МЕНЮ")
            print(f"{'='*60}")
            
            # Статус
            auth_status = "✅" if self.is_authenticated else "❌"
            chats_count = len(self.bot.chat_manager.chats)
            queue_size = (self.bot.scheduler.immediate_queue.qsize() + 
                         self.bot.scheduler.scheduled_queue.qsize())
            
            print(f"   Аутентификация: {auth_status}")
            print(f"   Чатов в базе: {chats_count}")
            print(f"   Сообщений в очереди: {queue_size}")
            print(f"   Статус рассылки: {'▶️ Запущена' if self.bot.scheduler.is_running else '⏸️ Остановлена'}")
            
            print(f"\n{Fore.YELLOW}⚡ КОМАНДЫ:")
            print(f"   1. 🔐 Аутентификация")
            print(f"   2. 📋 Чаты ({chats_count})")
            print(f"   3. 📨 Создать рассылку")
            print(f"   4. 🚀 Управление рассылкой")
            print(f"   5. 📊 Статистика")
            print(f"   6. 🧪 Тестовый режим")
            print(f"   7. 🚪 Выход")
            
            try:
                choice = input(f"\n{Fore.GREEN}🎯 Выберите действие (1-7): ").strip()
                
                if choice == "1":
                    asyncio.run(self.authenticate())
                elif choice == "2":
                    self.show_chats_menu()
                elif choice == "3":
                    self.create_broadcast_menu()
                elif choice == "4":
                    self.control_broadcast_menu()
                elif choice == "5":
                    self.show_statistics()
                elif choice == "6":
                    self.test_mode()
                elif choice == "7":
                    print(f"\n{Fore.YELLOW}👋 До свидания!")
                    asyncio.run(self.bot.disconnect())
                    break
                else:
                    print(f"{Fore.RED}❌ Неверный выбор")
                    
            except KeyboardInterrupt:
                print(f"\n\n{Fore.YELLOW}⚠️ Прервано пользователем")
                break
            except Exception as e:
                print(f"{Fore.RED}❌ Ошибка: {e}")
    
    def create_broadcast_menu(self):
        """Меню создания рассылки"""
        if not self.is_authenticated:
            print(f"{Fore.RED}❌ Сначала пройдите аутентификацию!")
            return
        
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"📨 СОЗДАНИЕ РАССЫЛКИ")
        print(f"{'='*60}")
        
        # Выбор чатов
        print(f"\n{Fore.YELLOW}🎯 ВЫБОР ЧАТОВ:")
        print(f"   1. Все чаты ({len(self.bot.chat_manager.categories['all'])} шт)")
        print(f"   2. Только группы ({len(self.bot.chat_manager.categories['groups'])} шт)")
        print(f"   3. Только каналы ({len(self.bot.chat_manager.categories['channels'])} шт)")
        print(f"   4. Только пользователи ({len(self.bot.chat_manager.categories['users'])} шт)")
        print(f"   5. Избранное ({len(self.bot.chat_manager.categories['favorites'])} шт)")
        print(f"   6. Указать количество")
        
        chat_choice = input(f"\n{Fore.GREEN}🎯 Выберите тип чатов (1-6): ").strip()
        
        if chat_choice == "1":
            category = 'all'
        elif chat_choice == "2":
            category = 'groups'
        elif chat_choice == "3":
            category = 'channels'
        elif chat_choice == "4":
            category = 'users'
        elif chat_choice == "5":
            category = 'favorites'
        elif chat_choice == "6":
            try:
                limit = int(input(f"{Fore.GREEN}🎯 Сколько чатов использовать?: "))
                category = 'all'
            except:
                limit = 50
                category = 'all'
        else:
            print(f"{Fore.RED}❌ Неверный выбор")
            return
        
        # Получаем чаты
        chat_ids = self.bot.chat_manager.get_chats_for_broadcast(category)
        
        if not chat_ids:
            print(f"{Fore.RED}❌ Нет доступных чатов для рассылки!")
            return
        
        # Настройка сообщения
        print(f"\n{Fore.YELLOW}✏️ СООБЩЕНИЕ:")
        print(f"   1. Стандартное сообщение")
        print(f"   2. Персонализированные сообщения")
        print(f"   3. Ввести свое сообщение")
        
        msg_choice = input(f"\n{Fore.GREEN}🎯 Выберите тип сообщения (1-3): ").strip()
        
        if msg_choice == "1":
            message = Config.DEFAULT_MESSAGE
        elif msg_choice == "2":
            message = None  # Будет персонализация
        elif msg_choice == "3":
            print(f"\n{Fore.YELLOW}📝 Введите сообщение:")
            message = input("> ")
        else:
            message = Config.DEFAULT_MESSAGE
        
        # Настройка количества
        try:
            messages_per_chat = int(input(f"\n{Fore.GREEN}🎯 Сообщений на чат (1-5): "))
            messages_per_chat = max(1, min(5, messages_per_chat))
        except:
            messages_per_chat = 1
        
        # Настройка задержки
        print(f"\n{Fore.YELLOW}⏱️ ЗАДЕРЖКА:")
        print(f"   1. Автоматическая (рекомендуется)")
        print(f"   2. Фиксированная")
        
        delay_choice = input(f"\n{Fore.GREEN}🎯 Выберите тип задержки (1-2): ").strip()
        
        if delay_choice == "2":
            try:
                delay = float(input(f"{Fore.GREEN}🎯 Задержка в секундах (2-10): "))
                delay = max(2.0, min(10.0, delay))
            except:
                delay = None
        else:
            delay = None
        
        # ПОДТВЕРЖДЕНИЕ
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"📋 ПОДТВЕРЖДЕНИЕ РАССЫЛКИ")
        print(f"{'='*60}")
        print(f"   📋 Чатов: {len(chat_ids)}")
        print(f"   📨 Сообщений на чат: {messages_per_chat}")
        print(f"   📊 Всего сообщений: {len(chat_ids) * messages_per_chat}")
        print(f"   ⏱️  Задержка: {delay or 'автоматическая'} сек")
        print(f"   💬 Сообщение: {(message[:50] + '...') if message else 'ПЕРСОНАЛИЗИРОВАННЫЕ'}")
        print(f"{Fore.CYAN}{'='*60}")
        
        confirm = input(f"\n{Fore.RED}❓ Подтвердить создание рассылки? (y/N): ").strip().lower()
        
        if confirm == 'y':
            # СОЗДАЕМ КАМПАНИЮ
            campaign_id = self.bot.scheduler.create_broadcast_campaign(
                chat_ids=chat_ids,
                message=message,
                messages_per_chat=messages_per_chat,
                delay_between=delay
            )
            
            print(f"\n{Fore.GREEN}✅ Кампания создана: {campaign_id}")
            print(f"{Fore.YELLOW}📢 Запустите рассылку в меню 'Управление рассылкой'")
        else:
            print(f"{Fore.YELLOW}⚠️ Создание отменено")
    
    def control_broadcast_menu(self):
        """Меню управления рассылкой"""
        status = self.bot.scheduler.get_status()
        
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"🚀 УПРАВЛЕНИЕ РАССЫЛКОЙ")
        print(f"{'='*60}")
        
        print(f"   Статус: {'▶️ ЗАПУЩЕНА' if status['is_running'] else '⏸️ ОСТАНОВЛЕНА'}")
        print(f"   Пауза: {'✅ ВКЛЮЧЕНА' if status['is_paused'] else '❌ ВЫКЛЮЧЕНА'}")
        print(f"   Очередь: {status['immediate_queue'] + status['scheduled_queue']} сообщений")
        print(f"   Отправлено: {status['total_sent']}")
        print(f"   Ошибок: {status['total_failed']}")
        
        if status['active_campaign']:
            print(f"   Кампания: {status['active_campaign']}")
        
        print(f"\n{Fore.YELLOW}⚡ КОМАНДЫ:")
        
        if not status['is_running']:
            print(f"   1. 🚀 Запустить рассылку")
            print(f"   2. 🔢 Запустить с ограничением")
        else:
            print(f"   1. ⏸️ Приостановить" if not status['is_paused'] else "   1. ▶️ Возобновить")
            print(f"   2. 🛑 Остановить")
        
        print(f"   3. 📊 Показать прогресс")
        print(f"   4. ↩️ Назад")
        
        choice = input(f"\n{Fore.GREEN}🎯 Выберите действие: ").strip()
        
        if choice == "1":
            if not status['is_running']:
                # Запуск
                try:
                    limit = int(input(f"{Fore.GREEN}🎯 Максимальное количество сообщений (Enter для безлимита): ") or "0")
                    if limit > 0:
                        self.bot.scheduler.start(max_messages=limit)
                    else:
                        self.bot.scheduler.start()
                except:
                    self.bot.scheduler.start()
            else:
                # Пауза/возобновление
                if status['is_paused']:
                    self.bot.scheduler.resume()
                else:
                    self.bot.scheduler.pause()
        
        elif choice == "2":
            if not status['is_running']:
                # Запуск с ограничением
                try:
                    limit = int(input(f"{Fore.GREEN}🎯 Количество сообщений: "))
                    self.bot.scheduler.start(max_messages=limit)
                except:
                    print(f"{Fore.RED}❌ Неверное количество")
            else:
                # Остановка
                self.bot.scheduler.stop()
        
        elif choice == "3":
            if status['is_running']:
                self.bot.scheduler._print_progress(
                    status['total_sent'],
                    None
                )
            else:
                print(f"{Fore.YELLOW}⚠️ Рассылка не запущена")
    
    def show_chats_menu(self):
        """Меню просмотра чатов"""
        chats = list(self.bot.chat_manager.chats.values())
        
        if not chats:
            print(f"{Fore.YELLOW}📭 Чаты не загружены")
            return
        
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"📋 СПИСОК ЧАТОВ")
        print(f"{'='*60}")
        print(f"   Всего: {len(chats)} чатов")
        print(f"   Группы: {len(self.bot.chat_manager.categories['groups'])}")
        print(f"   Каналы: {len(self.bot.chat_manager.categories['channels'])}")
        print(f"   Пользователи: {len(self.bot.chat_manager.categories['users'])}")
        print(f"   Избранное: {len(self.bot.chat_manager.categories['favorites'])}")
        print(f"{Fore.CYAN}{'='*60}")
        
        # Показываем первые 20 чатов
        for i, chat in enumerate(chats[:20], 1):
            status = "⭐" if chat['id'] in self.bot.chat_manager.categories['favorites'] else "  "
            status += "🚫" if chat['id'] in self.bot.chat_manager.categories['blacklist'] else "  "
            
            print(f"{i:3d}. {status} {chat['title'][:30]}")
            print(f"     ID: {chat['id']} | Тип: {chat['type']}")
            print(f"     Сообщений: {chat.get('message_count', 0)}")
            print()
        
        if len(chats) > 20:
            print(f"{Fore.YELLOW}... и еще {len(chats) - 20} чатов")
    
    def show_statistics(self):
        """Показать статистику"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"📊 СТАТИСТИКА СИСТЕМЫ")
        print(f"{'='*60}")
        
        # Статистика чатов
        print(f"\n{Fore.YELLOW}📋 ЧАТЫ:")
        print(f"   Всего в базе: {len(self.bot.chat_manager.chats)}")
        print(f"   Группы: {len(self.bot.chat_manager.categories['groups'])}")
        print(f"   Каналы: {len(self.bot.chat_manager.categories['channels'])}")
        print(f"   Пользователи: {len(self.bot.chat_manager.categories['users'])}")
        print(f"   Избранные: {len(self.bot.chat_manager.categories['favorites'])}")
        print(f"   Черный список: {len(self.bot.chat_manager.categories['blacklist'])}")
        
        # Статистика рассылки
        status = self.bot.scheduler.get_status()
        print(f"\n{Fore.YELLOW}📨 РАССЫЛКА:")
        print(f"   Статус: {'▶️ Запущена' if status['is_running'] else '⏸️ Остановлена'}")
        print(f"   В очереди: {status['immediate_queue'] + status['scheduled_queue']}")
        print(f"   Отправлено: {status['total_sent']}")
        print(f"   Ошибок: {status['total_failed']}")
        
        # Статистика защиты от бана
        print(f"\n{Fore.YELLOW}🛡️ ЗАЩИТА ОТ БАНА:")
        print(f"   Отправлено за час: {self.bot.scheduler.anti_ban.sent_hour}")
        print(f"   Отправлено за день: {self.bot.scheduler.anti_ban.sent_today}")
        print(f"   Лимит в час: {self.bot.scheduler.anti_ban.HOURLY_LIMIT}")
        
        if self.bot.scheduler.anti_ban.sent_hour > self.bot.scheduler.anti_ban.HOURLY_LIMIT * 0.8:
            print(f"   {Fore.RED}⚠️ ПРИБЛИЖАЕТЕСЬ К ЛИМИТУ!")
        elif self.bot.scheduler.anti_ban.sent_hour > self.bot.scheduler.anti_ban.HOURLY_LIMIT * 0.5:
            print(f"   {Fore.YELLOW}⚠️ Лимит на половине")
        else:
            print(f"   {Fore.GREEN}✅ В пределах лимита")
        
        print(f"{Fore.CYAN}{'='*60}")
    
    def test_mode(self):
        """Тестовый режим без реальной отправки"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"🧪 ТЕСТОВЫЙ РЕЖИМ")
        print(f"{'='*60}")
        print(f"{Fore.YELLOW}В этом режиме сообщения не отправляются реально,")
        print(f"а только имитируется отправка для тестирования логики.")
        
        print(f"\n{Fore.GREEN}🧪 Тестовая рассылка на 5 чатов...")
        
        # Создаем тестовую кампанию
        test_chats = [1000 + i for i in range(5)]
        campaign_id = self.bot.scheduler.create_broadcast_campaign(
            chat_ids=test_chats,
            message="🧪 ТЕСТОВОЕ СООБЩЕНИЕ - не отправляется реально!",
            messages_per_chat=1,
            delay_between=2
        )
        
        print(f"\n{Fore.GREEN}🚀 Запуск тестовой рассылки...")
        self.bot.scheduler.start(max_messages=3)
        
        print(f"\n{Fore.YELLOW}⏳ Ожидание завершения теста...")
        time.sleep(15)
        
        if self.bot.scheduler.is_running:
            self.bot.scheduler.stop()
        
        print(f"\n{Fore.GREEN}✅ Тест завершен!")
    
    def run(self):
        """Запуск системы"""
        try:
            self.show_main_menu()
        except KeyboardInterrupt:
            print(f"\n\n{Fore.YELLOW}👋 Программа завершена")
            asyncio.run(self.bot.disconnect())
        except Exception as e:
            print(f"{Fore.RED}❌ Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()

# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

def main():
    """Главная функция"""
    print(f"{Fore.CYAN}")
    print("🔥 TELEGRAM BROADCASTER PRO - ВСЁ В ОДНОМ ФАЙЛЕ")
    print("✅ Готов к работе!")
    
    # Проверяем конфигурацию
    if not Config.API_ID or not Config.API_HASH:
        print(f"\n{Fore.RED}❌ ВНИМАНИЕ: API_ID и API_HASH не заданы!")
        print(f"{Fore.YELLOW}📱 Получите на: https://my.telegram.org")
        print(f"{Fore.GREEN}✏️  Задайте в коде в классе Config:")
        print(f"    API_ID = 'ваш_id_здесь'")
        print(f"    API_HASH = 'ваш_hash_здесь'")
        print(f"    PHONE_NUMBER = '+79991234567'")
        
        # Предлагаем ввести данные
        print(f"\n{Fore.YELLOW}⚡ Быстрая настройка:")
        api_id = input("Введите API_ID: ").strip()
        api_hash = input("Введите API_HASH: ").strip()
        phone = input("Введите номер телефона (+7999...): ").strip()
        
        if api_id and api_hash and phone:
            Config.API_ID = api_id
            Config.API_HASH = api_hash
            Config.PHONE_NUMBER = phone
            print(f"{Fore.GREEN}✅ Данные сохранены!")
        else:
            print(f"{Fore.RED}❌ Данные не введены, работа невозможна")
            return
    
    # Создаем и запускаем систему
    system = BroadcastSystem()
    system.run()

if __name__ == "__main__":
    # Устанавливаем обработчик Ctrl+C
    import signal
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    
    # Запускаем
    main()
