# Kyiv Live Radar — доменна модель v2: Тривога → Атака → Цілі → Треки

## Context

Проєкт ріс фічами без явної доменної моделі верхнього рівня. Аудит коду показав:

- **Сутності «повітряна тривога» немає взагалі**: сирена придушується парсером як шум (`parser.py::siren_only`), «відбій» — транзитна дія, а не стан. Єдиний проксі «атака триває» — відкритий `Incident`.
- **`Threat.status` змішує вид і життєвий цикл**: `impact` — це вид маркера, не статус; `lost` перевантажений трьома смислами (відбій / тиша / дорозвідка) — це блокує будь-який аналіз результату атаки.
- **Немає state machine** — переходи розкидані інлайн-мутаціями по `ingest.py`, `tracking.py`, `incidents.py`, `sweeper.py`.
- **Класифікація атаки** — лише «найнебезпечніший тип» на `Incident`; немає комбінованих атак і імітаційних (РЕБ).
- **Доменна логіка просочилась у фронтенд**: notability банера, debounced refetch `/incidents/active`, client-side дедуп відбоїв.
- Латентні баги: reply-less «знищено» у вікні 16–19 хв губиться (gap 15 vs stale 20); fusion `_origin_key` для репостів ключується на message_id без каналу.

**Рішення користувача**: джерело тривог — офіційний TG-канал **@KyivCityOfficial** (тривога + відбій для м. Київ і області) через існуючий Telethon-листенер; API (alerts.in.ua uid=31 / UkraineAlarm) — пізніше як основне джерело. Рефакторинг — **поетапний**, кожна фаза — окремий реліз, evals лишаються зеленими.

**Цільова модель**: `Alert` (офіційна тривога, city/oblast) ⟵ `Incident`=Атака (типізовані компоненти, комбінована/імітаційна класифікація, явна причина завершення) ⟵ `Threat`=трек цілі (kind + closed_reason) ⟵ `ThreatEvent`. Виняток «балістика прилітає до сирени» моделюється так: **атака ніколи не чекає тривогу; тривога ретроактивно всиновлює нещодавню атаку** (lookback ~10 хв).

## Керівні принципи

- **Тільки адитивні зміни** схеми/API/WS у кожній фазі. Фронтенд уже ігнорує невідомі WS-типи (`store.ts::handleWS` рано виходить без `msg.threat`) — нові фрейми безпечні. Деплой: спершу backend, потім frontend.
- **Evals — ворота**: `eval/run_eval.py` + `eval/track_eval.py` мають проходити після кожної фази.
- **Один власник переходів на життєвий цикл** — маленькі модулі, не фреймворк.
- **Все reprocessable**: повідомлення alert-каналу теж ідуть у `raw_messages`, `reprocess.py` вміє перебудувати і тривоги.

---

## Фаза 1 — Фундамент: Alembic + явний життєвий цикл треку + фікси латентних багів (patch)

**Alembic** (так, вводимо зараз — попереду ще 2 міграції з новою таблицею та FK):
- `backend/alembic.ini` + `backend/migrations/env.py` (async template, `render_as_batch=True` для SQLite; URL з `app.config.settings`).
- Міграція 0001 — baseline поточної схеми. `app/migrate.py::upgrade_to_head()`: якщо таблиці є, а `alembic_version` немає — `stamp` baseline, потім `upgrade head`. Викликається з lifespan `main.py` замість `init_db`-хака `_ensure_columns`; `reprocess.py` теж переходить на нього.

**Життєвий цикл треку** (міграція 0002, адитивно):
- `threats.kind` (`'track'|'impact'`, backfill з `status='impact'`); `threats.closed_reason` (`'destroyed'|'all_clear'|'stand_down'|'stale'`, NULL поки відкритий; історичні `lost` → `'stale'`, задокументувати в міграції).
- Новий `app/lifecycle.py` (~60 рядків, БЕЗ бібліотеки state machine): `TRACK_TRANSITIONS` dict, `close_track(threat, when, reason)` (ставить `closed_at`, `closed_reason` і legacy `status` для сумісності фронтенду), `promote_track(...)` (замінює потрійне інлайн `status="tracking"` в `ingest.py`). Переписати виклики: `tracking.py::close_all_active` (reason з ingest: `all_clear`/`stand_down`), `close_stale_tracks` (`stale`), ingest destroyed-гілку, створення impact (`kind='impact'`).

**Фікси латентних багів**:
1. Destroyed-in-the-gap: `find_open_track` отримує параметр `gap_minutes`; destroyed-гілка передає `track_stale_minutes` (=20) замість 15. Семантика групування sighting-ів не змінюється → track_eval не постраждає. Регресійний тест.
2. Fusion-репости: `forwarded_from_channel_id` (nullable) у `raw_messages` + `threat_events`; заповнюється в `telegram_listener.py` з `fwd_from`; `fusion.py::_origin_keys` fallback стає `("orig", channel_id, forwarded_from_id)`.

**Тести**: `tests/test_lifecycle.py` (таблиця переходів, mapping reason→legacy status, регресія destroyed-gap), `tests/test_migrations.py` (upgrade порожньої БД; stamp+upgrade існуючої), оновити assertions у `test_tracking.py`/`test_ingest.py`. Serializer output — byte-compatible (нові поля `kind`/`closed_reason` в `ThreatOut` — опціональні).

---

## Фаза 2 — Повітряна тривога як першокласна сутність (minor)

**Схема** (міграція 0003): таблиця `alerts`: `id`, `scope` (`'city'|'oblast'`), `alert_type` (default `'air_raid'`), `started_at`, `ended_at`, `provider` (`'telegram'`, пізніше `'alerts_in_ua'`/`'ukrainealarm'`), `started_raw_id`/`ended_raw_id` (FK на `raw_messages` — provenance для reprocess), `closed_reason` (`'official'|'failsafe'`). Плюс `sources.role` (`'spotter'|'alert'`).

**AlertSource-абстракція — навмисно тонка** (`app/alerts.py`):
- `@dataclass AlertSignal(scope, action: 'start'|'end', when, provider, raw_id)`.
- `apply_alert_signal(session, signal)` — **ідемпотентна** (повторний start/end — no-op без дубль-broadcast). Це і є вся мультипровайдерність: майбутній API-poller просто емить ті самі сигнали, TG стає fallback'ом. БЕЗ registry/плагінів.

**Парсер тривог** (`app/alert_parser.py`) — окремий від спотерського:
- ПЕРШИЙ крок фази: зняти реальну вибірку @KyivCityOfficial через `eval/backfill_once.py`, закомітити ~20 повідомлень як fixture `tests/data/alert_channel_sample.jsonl`, формули будувати з реального тексту.
- `parse_alert_message(text) -> AlertSignal | None`: «повітряна тривога» → start; «відбій»+«тривог» → end; scope з «область/обл.» → oblast, інакше city. Все інше → None (канал постить і міські новини).

**Маршрутизація**: alert-канал НЕ йде через спотерський парсер (офіційний «Відбій…» влучив би у `_CLEAR` і закрив би треки передчасно — це рішення Фази 3; плюс не забруднюємо fusion/стрічку). `config.py`: `alert_channels: str = ""` (порожньо = фаза повністю спляча — це і є rollback). `telegram_listener.py` роутить за `Source.role`. `ingest.py::ingest_alert_message(...)` під тим самим `_ingest_lock`: raw → parse → apply → `Broadcast('alert', ...)`. `reprocess.py`: wipe `alerts` + роутинг raw за роллю. **`siren_only`-придушення у спотерському парсері лишається як є.**

**Failsafe**: sweeper закриває тривогу, відкриту довше `alert_failsafe_hours=12`, з `closed_reason='failsafe'` + гучний лог (захист від мертвої Telethon-сесії, що з'їла відбій).

**Зв'язку з Incident у цій фазі НЕМАЄ** — «тиха тривога» природно представима (тривога відкрита, інцидентів нуль). Лінкування — Фаза 3.

**API/WS/Frontend**: `GET /alerts/active`, `GET /alerts/recent?limit=`; WS-фрейм `type='alert'` (задеплоєний фронтенд його ігнорує — перевірено). Frontend: тип `Alert`, `store.ts` `alerts[]` + гідрація в `App.tsx`, новий `components/AlertBanner.tsx` — постійна стрічка «Повітряна тривога — м. Київ / область» з таймером тривалості; зелений стан відбою. Живе поряд з `IncidentBanner` (різні питання: «чи сирена» vs «що летить»).

**Тести**: `test_alert_parser.py` на реальній fixture; `test_alerts.py` (ідемпотентність: подвійний start, end без start, паралельні city+oblast, failsafe); alert-повідомлення ніколи не створює Threat/Notice.

---

## Фаза 3 — Атака: класифікація, зв'язок з тривогою, серверний банер (minor)

**Еволюція `Incident` без перейменування** (rename таблиці = DDL+API churn без поведінки; «атака» — словник у доках). Міграція 0004: `incidents.attack_types` JSON `[]` (накопичуваний set типів членів без `unknown`, підтримується в `attach_to_incident`), `alert_id` (nullable FK), `ended_reason` (`'all_clear'|'alert_end'|'stale'`), `decoy_mentions` INT, `has_hypersonic` BOOL.

**Класифікація — derived, не stored** (`app/attack.py`):
- `classify(...)`: сім'ї `drone`={shahed,jet_drone}, `cruise_missile`={missile}, `ballistic`={ballistic}; **`combined`** при ≥2 сім'ях; **`decoy_suspected` — модифікатор-boolean**, не замінний лейбл (атака може бути комбінована І частково імітаційна). Обчислюється при серіалізації.
- Decoy-сигнали — тільки кураторський словник у `parser.py`: `_DECOY = ("імітаці", "реб", "обманк", "хибн", "фальшив")` («реб» — у whole-word guard як «каб») → `ParseResult.decoy`. Поведінкова інференція («всі треки зникли без імпактів» ⇒ імітація) — НЕ класифікатор, максимум hint при завершенні.
- **Гіперзвук — НЕ шостий `target_type`** (розповзлося б по evals/іконках/severity): `ParseResult.hypersonic` з `("кинджал", "циркон", "аеробаліст")` → прапор на інциденті; рендер «балістична (гіперзвук)».

**Життєвий цикл атаки та зв'язок з тривогою**:
- Stored-стани лишаються `active`/`ended` + `ended_reason` (БЕЗ forming/subsiding — «затухає» derived з віку `last_activity_at`).
- `attach_to_incident`: новий інцидент лінкує відкриту **city**-тривогу, якщо є.
- **Виняток балістики**: у `apply_alert_signal` на `start` — всиновити відкритий нелінкований інцидент, що почався в межах `alert_adopt_lookback_minutes=10`. Один запит, один тест.
- **Кінець тривоги завершує атаку**: офіційний `end(city)` → `end_active_incidents(ended_reason='alert_end')` + `lifecycle.close_track(reason='all_clear')` для відкритих треків. Спотерський «відбій» працює як зараз (`ended_reason='all_clear'`); обидва шляхи ідемпотентні → офіційний+спотерський відбій за секунди один від одного природно дедуплікуються. Type-scoped відбій інцидент НЕ завершує (як зараз).

**Серверний банер**: `IncidentOut` += `classification`, `attack_types`, `alert_id`, `decoy_suspected`, `notable` (порт `IncidentBanner.tsx::isNotable` у серіалізатор — єдине джерело правди). Новий WS-фрейм `type='attack'` при зміні інциденту → фронтенд прибирає debounced `refreshIncidents()` (fetch лишається тільки для гідрації), `IncidentBanner` споживає серверні `notable`/`classification`.

**Тести**: `test_attack.py` — накопичення типів, combined, decoy-модифікатор, adoption lookback (e2e: citywide балістика → інцидент без тривоги → start тривоги всиновлює), кінець тривоги завершує атаку, ідемпотентність подвійного відбою. Golden set: рядки для decoy/hypersonic (опціональні expected-прапори, старі рядки не чіпаємо). `track_eval.py` — зелений (групування не чіпали).

---

## Фаза 4 — Спостережуваність + залишки точності парсера + чистка контракту (minor)

1. **Health-нотифікація Telethon-сесії**: sweeper порівнює `last_message_at` з `feed_silence_warn_minutes`; фронтенд показує «джерело даних недоступне» (критично тепер, коли ВІДСУТНІСТЬ відбою має значення).
2. **`_NEW_TARGET` «ще N»**: noun-anchored regex `ще\s+(\d+)\s+(?:ракет|ціл|шахед|бпла|дрон|баліст)` (щоб «ще 20хв» не влучало) + golden rows + перевірка `track_eval.py`.
3. **Умовний спосіб**: кураторський список `("якщо піде", "може піти", "у разі", ...)` → suppression як `negated`; СПОЧАТКУ corpus-sweep по 871 реальних повідомленнях (дисципліна «Щасливого»).
4. **Чистка фронтенду**: прибрати refetch-дублікати; closed-track linger (6с), кластеризацію відбоїв, resurrection guard ЛИШИТИ client-side (це transport/presentation, не домен). Опційно: feed-лейбли зі `closed_reason` («знищено»/«втрачено»/«відбій») замість інференції зі `status`.
5. *(Stretch, тільки якщо після №2 track_eval показує домінування reply-мультитаргет false-merges)*: content-based reply-splitter — time-boxed spike, керований числами eval.

---

## Чого НЕ робити (анти-overengineering для single-user MVP)

- Бібліотеки state machine (`transitions`/`python-statemachine`) — dict + 2 функції дають ту саму централізацію без тертя з async ORM.
- Event sourcing / message bus / Redis — один інстанс, один lock.
- Plugin-framework для AlertSource — одна ідемпотентна функція і Є абстракція.
- Новий `target_type` для гіперзвуку; rename `incidents`→`attacks`; stored forming/subsiding; полігони тривог понад city|oblast; окрема сутність «вектор» (вектор — derived у `geo.ts`); поведінковий decoy-класифікатор; v2 API.

## Рекомендації по тулінгу (поза фазами, за бажанням)

- **Alembic** — єдина нова залежність (Фаза 1), решта — stdlib.
- **Проєктні Claude-скіли** (`.claude/skills/` — зараз відсутні): `/release` (чекліст: тести+evals+changelog+bump за SEMVER_RULES), `/add-toponym` (геокодування через `scripts/geocode_localities.py` + обов'язковий FP-sweep по корпусу + перевірка stem-колізій), `/eval` (прогнати всі три eval-и одною командою). Це кодифікує процеси, які зараз живуть у CLAUDE.md/пам'яті.
- Пізніше: API alerts.in.ua (uid=31, токен за формою, polling 6–10 c, ліміт 12 req/min) або UkraineAlarm (webhook) як основний провайдер `AlertSignal`, TG — fallback.

## Ключові файли

- `backend/app/models.py` — `Alert`, `threats.kind`/`closed_reason`, `incidents.attack_types`/`alert_id`/`ended_reason`
- `backend/app/lifecycle.py` (новий), `app/alerts.py` (новий), `app/alert_parser.py` (новий), `app/attack.py` (новий), `app/migrate.py` (новий)
- `backend/app/ingest.py`, `tracking.py`, `incidents.py`, `sweeper.py`, `fusion.py`, `telegram_listener.py`, `config.py`, `serialize.py`, `api/routes.py`, `broadcast.py`
- `frontend/src/types.ts`, `store.ts`, `App.tsx`, `components/AlertBanner.tsx` (новий), `components/IncidentBanner.tsx`, `changelog.ts`

## Верифікація (кожна фаза)

1. `cd backend && .venv/bin/pytest tests/ -q` — все зелене.
2. `.venv/bin/python eval/run_eval.py` — parser golden set без регресій.
3. `DATABASE_URL="sqlite+aiosqlite:///./eval_backfill.db" .venv/bin/python eval/track_eval.py --verbose` — track-level без регресій.
4. Локальний прогін з `REPLAY_REAL_DATA=true` — 871 реальне повідомлення через оновлений пайплайн, дивимось карту/стрічку/банери.
5. `cd frontend && npm run build` (це і type-check).
6. Запис у `frontend/src/changelog.ts` (укр., operator-facing; Фаза 1 — patch, 2–4 — minor).
7. Diff підготовано, БЕЗ commit/push — чекаємо «пуш»/«комітимо» від мейнтейнера.

## Мапа ризиків → фаза, що закриває

| # | Ризик (місце в коді) | Фаза |
|---|---|---|
| 1 | Немає сутності тривоги; сирена = шум (`parser.py::siren_only`) | 2 |
| 2 | Reply-less «знищено» у вікні 16–19 хв губиться (ingest destroyed → `find_open_track` 15хв vs sweeper 20хв) | 1 |
| 3 | `status` змішує kind+lifecycle; `lost` ×3 смисли (`close_all_active`+`close_stale_tracks`) | 1 |
| 4 | Reply-нитка на кілька фізичних цілей; «ще N» (`parser.py::_NEW_TARGET`) | 4 |
| 5 | Немає міграцій (`db.py::_ensure_columns`) | 1 |
| 6 | Потрійна неоднозначність завершення (спотерський відбій / офіційний / sweeper) без `ended_reason` | 3 |
| 7 | Fusion-репости: ключ на message_id без каналу (`fusion.py::_origin_keys`) | 1 |
| 8 | Мертва Telethon-сесія = тиха втрата даних І тривог | 2 (failsafe) + 4 (нотифікація) |
| 9 | Доменна логіка у фронтенді (notability, refetch) | 3 |
| 10 | Умовний спосіб («якщо піде на…») без guard | 4 |
