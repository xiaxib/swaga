# Telegram Math Solver Bot (aiogram 3.x, MVP)

MVP-бот для решения математических задач по тексту и фото.

## Что умеет бот
- Принимает задачу текстом или фото.
- Для фото запускает OCR (опционально, через Tesseract).
- Решает задачу через `solver_service` (локальный adapter, расширяемо под LLM/API).
- Отправляет:
  - краткий ответ,
  - пошаговое решение,
  - финальный ответ,
  - PNG-изображение с красиво оформленным решением.
- Ограничения:
  - бесплатный тариф: 3 запроса в день,
  - подписка: 199 ₽ / месяц.
- Админ-команды для выдачи подписки и просмотра статистики.

## Архитектура
Проект построен в стиле modular monolith (один сервис, четкие слои):
- `handlers/` — Telegram handlers и маршрутизация команд/сообщений.
- `services/` — бизнес-логика (лимиты, подписки, OCR, solver, история, статистика).
- `database/` — SQLAlchemy-модели, сессия, инициализация БД.
- `middlewares/` — middleware (подключение DB session в контекст).
- `config/` — настройки через Pydantic Settings и logging.
- `utils/` — клавиатуры и вспомогательные части.
- `images/` — входные/выходные изображения.
- `logs/` — логи приложения.

## Дерево файлов
```text
.
├── bot.py
├── main.py
├── .env.example
├── requirements.txt
├── README.md
├── config/
│   ├── __init__.py
│   ├── logging_config.py
│   └── settings.py
├── database/
│   ├── __init__.py
│   ├── base.py
│   ├── init_db.py
│   ├── models.py
│   └── session.py
├── handlers/
│   ├── __init__.py
│   ├── admin.py
│   ├── commands.py
│   └── tasks.py
├── middlewares/
│   ├── __init__.py
│   └── db.py
├── services/
│   ├── __init__.py
│   ├── history_service.py
│   ├── image_service.py
│   ├── ocr_service.py
│   ├── payment_service.py
│   ├── solver_service.py
│   ├── stats_service.py
│   ├── subscription_service.py
│   ├── usage_service.py
│   └── user_service.py
├── utils/
│   ├── __init__.py
│   └── keyboards.py
├── images/
└── logs/
```

## Установка и запуск
1. Создайте виртуальное окружение и установите зависимости:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Скопируйте `.env.example` в `.env` и заполните:
   ```bash
   cp .env.example .env
   ```

3. Укажите:
   - `BOT_TOKEN`
   - `ADMIN_IDS` (через запятую)

4. Запуск:
   ```bash
   python main.py
   ```

## Команды
- `/start` — приветствие и кнопки
- `/help` — инструкция
- `/limits` — текущий тариф и остаток лимита
- `/subscribe` — инфо о подписке 199 ₽/мес
- `/profile` — профиль пользователя
- `/admin_grant_sub <telegram_id> [days]` — выдать подписку
- `/admin_stats` — статистика

## Примечания по OCR
- По умолчанию OCR выключен (`ENABLE_TESSERACT_OCR=false`).
- Чтобы включить, установите Tesseract OCR в системе и поставьте:
  - `ENABLE_TESSERACT_OCR=true`
- Если OCR недоступен, бот попросит прислать более четкое фото или текст.

## Платежи (MVP)
Реализован `PaymentService` + `MockPaymentService`.
На этапе MVP платежи реальные не проводятся, подписка выдается админом.

## БД (SQLite)
Таблицы:
- `users`
- `usage`
- `subscriptions`
- `requests_history`

Создаются автоматически при старте.
