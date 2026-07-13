# Kyiv Live Radar — рефакторинг організації коду (behavior-preserving)

## Context

Після domain-v2 (Alert→Attack→Track) backend виріс до 29 плоских модулів у `backend/app/`, frontend — до 23 файлів у плоскому `src/`. Аудит показав: `parser.py::parse_message` — 184-рядковий моноліт з 13 inline-прапорами; `ingest.py::_process_parsed` — 283 рядки на 8 гілок; приватні символи ingest (`_process_parsed`, `_should_fallback`) імпортуються з інших модулів; `Broadcast` живе в ingest, але потрібен sweeper/broadcast; health-моніторинг приклеєний до Telethon-листенера (звідси lazy-імпорти в sweeper/main); citywide-sentinel lookup реалізований 3×; у feed↔map дубльована presentation-логіка; кольори в трьох паралельних системах. Плюс процесні прогалини: Telethon-handler без try/except (отруйне повідомлення "вбиває" видимість фіду), нуль логування в доменних модулях, захардкоджені fusion-ваги.

Мета: розкласти файли по логічних пакетах, прибрати дублікати, закрити прогалини, закласти конвенції для швидкого росту. **Без зміни поведінки** — evals (run_eval + track_eval) мають збігтися з базовими числами точно.

**Передумова:** стартуємо з чистого main — поточний некомічений domain-v2 diff мейнтейнер спершу тестує і комітить сам. Working agreement: кожна фаза = окремий діф, підготував → прогнав гейти → СТОП, чекаю «пуш»/«комітимо».

**Повний гейт** (після кожної backend-фази; frontend-фази — лише build+smoke):
```bash
cd backend
.venv/bin/pytest tests/ -q                    # 168 тестів
.venv/bin/python eval/run_eval.py
DATABASE_URL="sqlite+aiosqlite:///./eval_backfill.db" .venv/bin/python eval/track_eval.py
# smoke: REPLAY_REAL_DATA=true TELEGRAM_ENABLED=false uvicorn app.main:app --port 8137 — без трейсбеків
#   (локальний .env має TELEGRAM_ENABLED=true — без явного override REPLAY-smoke спробує
#   підняти реальний Telethon і вдариться в заблокований kyiv_radar.session)
cd ../frontend && npm run build
```

## Цільове дерево — backend/app/

```
app/
├── main.py, worker.py, config.py, db.py, models.py, schemas.py,
│   gazetteer.py, seed.py, migrate.py, telegram_login.py     # НЕ переїжджають
├── logging_setup.py     # NEW (Ф4): єдиний basicConfig (зараз 2×: main.py:17, worker.py:21)
├── timeutil.py           # NEW (Ф2): within(a,b,gap) — зараз 2× (telegram_listener:44, routes:78)
├── parsing/
│   ├── __init__.py      # API пакета: parse_message, ParseResult, DistrictHit, DistrictMatcher, normalize
│   ├── vocab.py         # parser.py:17–306 — усі ~15 кураторських словників + regex-літерали
│   ├── matcher.py       # normalize, _stem, DistrictHit, _is_street_reference, DistrictMatcher (309–436)
│   ├── rules.py         # ParseResult, _kw_regex+compiled REs, _target_type/_status, parse_message
│   ├── alert_parser.py  # as-is
│   └── llm.py           # llm_fallback.py as-is
├── domain/              # DB-backed доменна логіка, без I/O і FastAPI
│   ├── tracking.py, lifecycle.py, fusion.py, incidents.py, alerts.py, attack.py, geometry.py
│   └── districts.py     # NEW: ЄДИНИЙ кешований citywide_district_id(session) + reset_cache()
│                        #   (замінює ingest._citywide_district_id, broadcast._sentinel_district_id,
│                        #    inline-запит routes.py:148–150)
├── pipeline/
│   ├── results.py       # NEW: dataclass Broadcast (з ingest.py:111–118) — leaf для ingest/sweeper/broadcast
│   ├── ingest.py        # (Ф3 розбиває _process_parsed на handler-и)
│   ├── broadcast.py, sweeper.py, reprocess.py
├── feeds/
│   ├── health.py        # NEW: _state/get_status/feed_health з telegram_listener.py:33–66 —
│   │                    #   вбиває lazy-імпорти sweeper.py:62 і main.py:88–89
│   ├── telegram.py      # telegram_listener.py мінус health
│   ├── replay.py, simulator.py
│   └── common.py        # NEW (Ф3): build_matcher() — select(District)→DistrictMatcher, зараз 3×
└── api/
    ├── routes.py, ws.py
    └── serialize.py     # serialize.py сюди — це ORM→API presentation-шар
```

Свідомо НЕ переїжджають: `main.py`/`worker.py`/`telegram_login.py` (задокументовані entrypoints — railpack.json, CLAUDE.md), `models/schemas/config/db/gazetteer` (когезивні leaf-и, `migrations/env.py:18` `from app import models` — load-bearing для Base.metadata).

## Цільове дерево — frontend/src/

```
src/
├── main.tsx, App.tsx, router.ts, api.ts, ws.ts, i18n.ts, types.ts, store.ts, changelog.ts  # root
├── theme.ts             # + HOME_COLOR ('#38bdf8', зараз 4 raw-літерали), − мертві STATUS_COLORS
├── threatDisplay.tsx    # NEW: спільна feed↔map presentation-логіка (див. Ф6)
├── threatIcons.ts       # ThreatType union видаляється → TargetType з types.ts
├── lib/
│   ├── geo.ts           # тільки generic-геометрія: bearing, inRing, districtAt
│   └── storage.ts       # усі 5 localStorage-ключів (klr-*) + safe get/set
└── components/
    ├── map/             # MapView, MapLegend, track.ts (trackPoints/hasMovement/headingOf — доменна половина geo.ts)
    ├── feed/             # ThreatLog, feedGrouping.ts (kyivDayKey/groupFeed/clusterNotices)
    ├── banners/          # AlertBanner, IncidentBanner
    ├── chrome/           # SettingsPanel, HomeControl, VersionInfo, LanguageSwitcher, DisclaimerModal
    └── changelog/        # ChangelogPage
```

`store.ts` НЕ розбиваємо (208 рядків — ок), лише localStorage → `lib/storage.ts`. `changelog.ts` лишається в root (CLAUDE.md release-правило називає цей шлях).

## Фази

### Ф0 — Baseline
Повний гейт на свіжому main; записати точні числа run_eval і track_eval (72%/91%/69%) у нотатку. Це acceptance-критерій Ф2–Ф4.

**✅ ЗНЯТО 2026-07-13 (на робочій копії = майбутньому v2-коміті):**
- pytest: **168 passed**
- run_eval: target_type **100%**, status **100%**, is_new_target **100%**, district recall/precision/F1 **97.8%** (TP=45 FP=1 FN=1); decoy 1/1, hypersonic 2/2, negated 4/4
- reprocess (--no-llm): 871 повідомлень → 431 з подіями, **192 треки, 603 події**
- track_eval: session purity **46/64 (72%)**, track purity **165/181 (91%)**, vector accuracy **31/45 (69%)**
- npm run build: чистий

Примітка: eval_backfill.db на диску була до-baseline-ної схеми (без incidents/notices, threats без incident_id) — перезібрана: свіжа схема alembic head + перенесені districts/sources/raw_messages + reprocess_raw.py --no-llm. Бекапи старої: `eval_backfill.db.bak-pre-migration` (незаймана), `eval_backfill.db.old-schema` (частково мігрована) — можна видалити після коміту v2.

### Ф1 — Packaging-гігієна (крихітна)
- `backend/pytest.ini` → `backend/pyproject.toml`: `[tool.pytest.ini_options]` з `asyncio_mode="auto"`, `pythonpath=["."]`.
- 12 `sys.path.insert`-рядків у eval/scripts/migrations **лишаємо** — editable install зв'язав би кожен venv/Railway-білд з install-кроком заради видалення 12 робочих рядків. Переглянути тільки якщо з'явиться другий пакет.

**✅ ГОТОВО 2026-07-13:** `pytest.ini` видалено, `pyproject.toml` створено з точним вмістом вище. Гейт == Ф0 точно (168 passed, run_eval 100/100/100/97.8%, track_eval 46/64·165/181·31/45).

### Ф2 — Backend-переїзди (git mv + механічні імпорти; тіла функцій не змінюються)
1. Створити пакети, `git mv` цілі файли за деревом.
2. Розрізати parser.py по секційних межах (vocab ≤306 / matcher 309–436 / rules — решта); `parsing/__init__.py` ре-експортує 5 публічних імен — 12 споживачів міняють лише `app.parser` → `app.parsing`.
3. Перенесення символів (cut-paste): `Broadcast` → `pipeline/results.py`; health-блок → `feeds/health.py` (lazy-імпорти sweeper.py:62 / main.py:88–89 → нормальні top-level); citywide lookup → `domain/districts.py`; `_within` → `timeutil.within`.
4. Перейменувати де-факто публічні privates: `_process_parsed`→`process_parsed`, `_process_parsed_alert`→`process_parsed_alert`, `_should_fallback`→`should_fallback` (споживачі: reprocess, eval/compare_llm, тести). `_recent_type`/`_note_and_inherit_type` лишаються приватними (white-box у тестах — ок).
5. Оновити ВСІ зовнішні call sites: `tests/conftest.py:3–4` + скиди глобалів (`districts.reset_cache()`), 14 тест-модулів, 8 eval-скриптів, 3 scripts/, docs. Постійних shim-ів немає (єдиний непорожній `__init__` — `parsing/`).
6. У тому ж діфі: шляхи в CLAUDE.md (архітектурна секція) і WORKFLOW.md. `.claude/plans/domain-model-v2.md` не чіпаємо (історичний документ).
- Стратегія: точковий проєктний replace по модулю + фінальний grep-sweep за старими шляхами (`app\.parser\b`, `app\.ingest\b`, `app\.telegram_listener` …) + грепнути lazy-імпорти в тілах функцій.
- Гейт: повний + явно `pytest tests/test_migrations.py -q`.

**✅ ГОТОВО 2026-07-13:** усі 4 пакети створені за деревом; `domain/districts.py` замінив 3 дублі citywide-lookup (ingest/broadcast/routes); `Broadcast` → `pipeline/results.py`; health-блок (`_state`/`get_status`/`feed_health`) → `feeds/health.py`, lazy-імпорти в sweeper.py/main.py стали top-level; `timeutil.within()` замінив дубль `_within` (telegram.py/routes.py). Перейменування privates зроблено. Call sites оновлено всюди — включно з `test_reprocess.py`, якого не було у первинній мапі залежностей (виявлено фінальним grep-sweep). `test_telegram_listener.py` розділено на нього (reconnect/backoff) + новий `test_feed_health.py` (health-статус), бо самі функції фізично переїхали в інший модуль. CLAUDE.md/WORKFLOW.md оновлені. Гейт == Ф0 точно: 168 passed (двічі поспіль), run_eval 100/100/100/97.8%, track_eval 46/64·165/181·31/45, REPLAY-smoke чистий (health/threats/events/incidents/notices ендпоінти вручну перевірені), npm run build чистий.

### Ф3 — Розбиття великих функцій (найризиковіша, eval-gated; за потреби — 2 окремі діфи)
1. `parse_message` (parsing/rules.py): кожен flag-блок → іменований предикат (`_clear_scope`, `_impact`, `_aftermath`, `_ad_action`, `_negated`, `_siren_only`, `_day_recap`, `_political_quote`, `_lost_signal`, `_summary`, `_citywide`, `_target_pulse`, `_matched`) у ТОЧНО поточному порядку; ланцюг залежностей (impact→aftermath; suppressors→citywide→pulse→matched; district-clearing) — дослівно. `parse_message` → ~50-рядковий оркестратор.
2. `process_parsed` (pipeline/ingest.py): 8 гілок → handler-функції (`_handle_clear` 297–308, `_handle_lost_signal` 316–336, `_handle_target_pulse` 343–365, `_handle_summary` 370–373, `_handle_destroyed` 383–418, `_handle_impact` 429–460, `_handle_citywide` 470–502, `_handle_sighting` 509–542) + маленький `@dataclass IngestContext` (групування параметрів, не фреймворк). Диспетчер — plain-послідовність if-ів.
3. `feeds/common.py::build_matcher()` — замість потрійного shell-а. Самі message-loops НЕ уніфікуємо (реально різні).
- Гейт: run_eval і track_eval == Ф0 ТОЧНО; REPLAY-smoke обов'язковий (pulse/citywide/destroyed шляхи).
- Правило: жодних «покращень» умов при переносі — спокуси записуються в нотатку для окремого PR.

**✅ ГОТОВО 2026-07-13:** усі 3 підкроки зроблені одним діфом. `parse_message` розбитий на 13 предикатів у точному порядку. `process_parsed` розбитий на 8 handler-ів + `IngestContext`; ВАЖЛИВО — `_handle_target_pulse` єдиний handler з fallthrough (повертає `None`, коли немає відкритого citywide-алерту, диспетчер тоді йде далі по гілках); решта завжди повертають. `feeds/common.py::build_matcher()` замінив дубль у telegram.py/replay.py/simulator.py (reprocess.py НЕ займали — інша форма, комбінується з sources/raws). Гейт == Ф0 точно: 168 passed, run_eval 100/100/100/97.8%, track_eval 46/64·165/181·31/45, REPLAY-smoke (з явним `TELEGRAM_ENABLED=false` — інакше лоадер підхоплює реальний Telethon з локального `.env`) підтвердив усі статуси (tracking/impact/lost/destroyed) + clear/summary notices, нуль трейсбеків.

### Ф4 — Backend-фікси прогалин (кожен маленький, файли — уже нові шляхи)
1. `feeds/telegram.py` handler (стар. 263–282): `_state["last_message_at"]` ставити одразу при отриманні повідомлення (health = liveness фіду, не успіх пайплайна); ingest+broadcast у try/except (CancelledError re-raise / Exception → log.exception) — отруйне повідомлення не летить у диспетчер Telethon.
2. `_backfill` (стар. 205–217): per-message try/except за патерном replay.py:118–128 (одне погане повідомлення не зриває весь бекфіл).
3. `api/ws.py:36–39`: логувати відкидання мертвого WS-клієнта; `main.py:106–107`: bare except → log.exception.
4. Логування в domain/{tracking,lifecycle,fusion,incidents,alerts} + pipeline/broadcast: INFO на create/promote/close треку і start/end інциденту, WARNING на fusion-конфлікт, DEBUG per-event. Без логів у чистих хелперах (attack.classify, geometry, serialize).
5. `fusion.py:97–103` ваги → config.py (`fusion_conf_one_source=0.5`, `_two=0.75`, `_three_plus=0.9`, `fusion_conflict_penalty=0.2`); `sweeper._INTERVAL_S` → `settings.sweeper_interval_s=60`. Reconnect-backoff Telethon лишається модульними константами.
6. `api/serialize.py::threat_out_shallow`: рукописні 13 полів → introspection по `ThreatOut.model_fields` (нове поле підхоплюється автоматично; drift ламається гучно). `model_validate` не можна — торкнеться lazy `th.events`.
7. `logging_setup.setup_logging()` — main.py і worker.py викликають один.
8. `gazetteer.py:270–275`: sentinel lat/lon ← `KYIV_CENTER` замість дубля літерала.
9. Нові тести: `tests/test_fusion.py` (origin-dedup, конфлікт, config-ваги), `tests/test_serialize.py` (drift-тест: shallow == full мінус events). Broadcast/sweeper — транзитивно, окремі тести = async-mock-церемонія, скіпаємо.
- Гейт: повний; ваги за замовчуванням ті самі → eval-числа не змінюються.

**✅ ГОТОВО 2026-07-13:** усі 9 пунктів зроблено одним діфом. (1-2) `feeds/telegram.py`: `_state["last_message_at"]` ставиться ПЕРШИМ рядком handler-а (до будь-якого parsing/DB); live-handler і `_backfill` обгорнуті в try/except (CancelledError re-raise, Exception → `log.exception`) — отруйне повідомлення більше не вбиває ні диспетчер Telethon, ні решту бекфілу. (3) `ws.py`: `log.info` при відкиданні мертвого клієнта; `main.py`: bare `except Exception` у `ws_threats` тепер `log.exception`. (4) Логування додано в `domain/{tracking,lifecycle,fusion→ні,incidents,alerts}` + `pipeline/broadcast` + **також `pipeline/ingest.py`** (розширення за межі буквального списку файлів плану — "create track" не мало домену-рівня точки без цього, оскільки `Threat(...)` конструюється прямо в ingest-хендлерах, не в tracking.py): INFO на create (ingest.py, 3 місця)/promote/close (lifecycle.py) треку і start/end інциденту (incidents.py) + start/close алерту (alerts.py, по аналогії); WARNING на fusion-конфлікт + DEBUG per-event fusion recompute — ОБИДВА в `tracking.py::apply_fusion`, НЕ в `fusion.py::compute_fusion` (той лишився чистим хелпером без логів, як attack.classify/geometry — pure function, no I/O); DEBUG per-broadcast у `pipeline/broadcast.py`. Перевірено НЕ через buffered REPLAY-smoke (uvicorn+redirected-file чомусь не флашить app-рівня log-рядки в цьому середовищі — pre-existing quirk, не регресія), а прямим unbuffered `python -u` викликом ingest_message з `force=True` logging — усі 5 очікуваних рядків (created/fusion/incident started/closed) підтверджені. (5) fusion-ваги (`fusion_conf_one_source=0.5`, `_two_sources=0.75`, `_three_plus_sources=0.9`, `fusion_conflict_penalty=0.2`) і `sweeper_interval_s=60` → config.py; `fusion.py`/`sweeper.py` читають з `settings`. (6) `threat_out_shallow` тепер `{name: getattr(th, name) for name in ThreatOut.model_fields if name != "events"}`. (7) `logging_setup.py::setup_logging()`, викликається з main.py і worker.py. (8) `KYIV_CENTER` переміщено ПЕРЕД `DISTRICTS` (був після — сентинел-запис тепер посилається на `KYIV_CENTER["lat"/"lon"]`). (9) `test_fusion.py` (12 тестів: corroboration/origin-dedup/repost-collapse/conflict/family-collapse/unknown-exclusion/config-ваги через monkeypatch) + `test_serialize.py` (2 тести: shallow==full мінус events, усі non-events поля співпадають з ORM). Гейт: 180 passed (168+12 нових), run_eval 100/100/100/97.8%, track_eval 46/64·165/181·31/45 — точний збіг з Ф0 (дефолтні ваги не змінились), REPLAY-smoke чистий (0 active→3 active, нуль трейсбеків), npm run build чистий.

### Ф5 — Frontend-переїзди (механічні)
- `git mv` за деревом; розріз `geo.ts` → `lib/geo.ts` (generic) + `components/map/track.ts` (доменні trackPoints/hasMovement/headingOf); `lib/storage.ts` з 5 ключами (store.ts:23–32, MapLegend:8, SettingsPanel:8, DisclaimerModal:7, i18n:7).
- Гейт: `npm run build` (tsc ловить усе) + оком `npm run dev` проти REPLAY-бекенда. Динамічних import() немає (перевірено).

**✅ ГОТОВО 2026-07-13:** усі 11 компонентів `git mv` за деревом (map/{MapView,MapLegend}, feed/ThreatLog, banners/{AlertBanner,IncidentBanner}, chrome/{SettingsPanel,HomeControl,VersionInfo,LanguageSwitcher,DisclaimerModal}, changelog/ChangelogPage). `geo.ts` розрізаний: `lib/geo.ts` (Pt, bearing, districtAt, приватний inRing) + `components/map/track.ts` (trackPoints/hasMovement/headingOf, доменні — імпортують `Threat`/`ThreatEvent` типи + `bearing` з lib/geo). Новий `lib/storage.ts`: `STORAGE_KEYS` (5 klr-* ключів) + `safeGet`/`safeSet`/`safeRemove` (try/catch навколо localStorage — приватний режим браузера/quota більше не кидає виняток; це свідоме зміцнення, узгоджене зі словом "safe" у плані, не побічний ефект). Усі 5 споживачів (store.ts, MapLegend, SettingsPanel, DisclaimerModal, i18n.ts) переведені на safe-обгортки; `DISCLAIMER_HIDE_KEY` (раніше експортувався з DisclaimerModal.tsx і читався напряму в App.tsx) централізовано — App.tsx тепер читає через `safeGet(STORAGE_KEYS.disclaimerHide)`. MapView.tsx→banners/IncidentBanner.tsx (notableIncident) — єдиний міжпапковий імпорт після переїзду, полагоджений. `feedGrouping.ts`-виокремлення з ThreatLog.tsx НЕ робили — це в буквальному тексті Ф5 не значилось (тільки в ілюстративному дереві), залишено як є, щоб не змішувати механічний переїзд із дедуплікацією (Ф6). Гейт: `npm run build` чистий (tsc -b + vite build, 1885 модулів); дод. перевірка — короткий `npm run dev` boot-check + HTTP-запит на кожен переїханий/змінений файл через Vite dev-transform (усі 200, нуль помилок у логу). "Оком" візуальну перевірку в браузері агент виконати не може — це залишається на мейнтейнера.

### Ф6 — Frontend дедуплікація + фікси
1. `threatDisplay.tsx`: `threatState()` (уніфікує ThreatLog:14–19 і MapView:199–206, fix-гілка через opts), `typeLabel()` (правило suppression impact+unknown — зараз 3 місця), `<CorroborationLine/>` (дослівний дубль ThreatLog:337–340 / MapView:154–156), `<CountBadge/>` (×N amber, 2 місця — обрати ОДНУ кольорову схему, зафіксувати яка сторона візуально зміниться).
2. Видалити `ThreatType` (threatIcons.ts:12) → `TargetType`; прибрати касти.
3. `theme.ts`: `HOME_COLOR='#38bdf8'` (4 літерали); IncidentBanner:38 hex-и → іменовані константи; вичистити мертві STATUS_COLORS-ключі (перевірити повторно ПІСЛЯ правки IncidentBanner — `confirmed`/`conflict` можуть ожити).
4. i18n: ChangelogPage/VersionInfo hardcoded-українська → `t()` + ключі в uk.json/en.json.
- Гейт: build + візуальний smoke (гліфи, бейджі, банери, /change-log обома мовами).

**✅ ГОТОВО 2026-07-13:** усі 4 пункти зроблено одним діфом. (1) новий `threatDisplay.tsx`: `threatState(threat, opts)` (ThreatLog викликає без opts → завжди 'active'/'impact'/'destroyed'; MapView передає `{heading, directional}` → може дати 'fix' — дослівна поведінка обох старих копій збережена); `typeLabel(threat, t)` (suppression impact+unknown) застосовано у ВСІХ 3 місцях — ThreatLog, MapView ThreatPopup (обидва вже мали правило) і MapView InspectBadge (НЕ мав — це була прихована неконсистентність, тепер виправлена: impact з unknown-типом більше не показує слово "Невідомо" в inspect-бейджі); `<CorroborationLine as="span"|"div">` і `<CountBadge as="span"|"b">` — `as` param зберігає точний оригінальний тег/стиль на кожній стороні (жодної візуальної зміни в MapView). (2) `ThreatType` видалено з threatIcons.ts, скрізь `TargetType` з types.ts; обидва каsти (`as ThreatType` у ThreatLog/MapView) прибрані — типи вже збігаються. (3) `HOME_COLOR='#38bdf8'` у theme.ts, усі 4 raw-літерали замінені (MapLegend dotSwatch, MapView homeIcon SVG fill + Circle pathOptions, ThreatLog notice-color fallback); rgba(56,189,248,.6) у drop-shadow homeIcon НЕ займали (5-те, не рахувалось у "4 літерали" плану, інший формат). IncidentBanner: замість довільних нових констант — `INCIDENT_SEVERITY_COLOR.ballistic/.other` в theme.ts, що напряму перевикористовують `STATUS_COLORS.confirmed`/`.conflict` (значення співпадали побайтово) — це й вирішило питання "чи мертві" ці два ключі: НІ, ожили через IncidentBanner. Видалено лише `STATUS_COLORS.unconfirmed` (єдиний реально мертвий ключ — нуль посилань у коді). (4) i18n: новий namespace `changelog.{back,title,semverRules,version,history}` в uk.json/en.json; ChangelogPage.tsx і VersionInfo.tsx переведені на `t()`. `SEMVER_RULES`/`CHANGELOG` дані з changelog.ts (вже українською за задумом — CLAUDE.md release-правило) НЕ займали — це контент, не UI chrome. Гейт: `npm run build` чистий (tsc -b + vite build, 1886 модулів) + dev-server boot-check на кожен змінений файл (усі 200, нуль помилок); "оком" перевірка — не в змозі агента, лишається мейнтенеру.

### Ф7 — Docs + changelog
- Фінальний прохід CLAUDE.md (шляхи модулів, «read WORKFLOW.md before touching parser.py/tracking.py» → нові шляхи) і WORKFLOW.md.
- Changelog: ОДИН `patch`-запис на всю серію — операторськи-помітне у Ф4/Ф6 (фід не «вмирає» від отруйного повідомлення; бекфіл переживає погані повідомлення; уніфіковані кольори бейджів), українською; переїзди пакетів не наративимо.

**✅ ГОТОВО 2026-07-13 (ОСТАННЯ ФАЗА ПЛАНУ — рефакторинг завершено):** CLAUDE.md вже був повністю актуальний (шляхи оновлено ще в Ф2, звірено фінальним grep-свіпом — нуль старих `app.parser`/`app.ingest`/... посилань). WORKFLOW.md отримав 3 точкові правки, які накопичились ПІСЛЯ Ф2 (тобто через Ф4-Ф6, не через саму реорганізацію пакетів): (1) bearing/vector математика — `geo.ts` → `lib/geo.ts` (bearing) + `components/map/track.ts` (trackPoints/headingOf), відображає Ф5-розріз; (2) фьюжн-ваги розділ (0.5/0.75/0.9/-0.2) — додано речення, що це тепер `config.py`-налаштування (`fusion_conf_*`, `fusion_conflict_penalty`), не хардкод, відображає Ф4; (3) `MapView.tsx`/`ThreatLog.tsx` → повні шляхи `components/map/MapView.tsx`/`components/feed/ThreatLog.tsx`, відображає Ф5. Побічно виявлено (НЕ виправлено, поза межами цього рефакторингу): WORKFLOW.md п.1 «слабких місць» стверджує «умовний спосіб і майбутній час — досі взагалі не обробляються», але код (`_has_conditional_hedge` у vocab.py/rules.py) це ВЖЕ обробляє — розбіжність існувала ДО старту цього рефакторингу (не моя зміна поведінки), контентний аудит weak-points списку — окрема задача, не частина цього організаційного рефакторингу. Changelog: один запис `0.4.3` (patch, 2026-07-13) у `frontend/src/changelog.ts` — "Стійкість фіду до поганих повідомлень": (a) отруйне повідомлення більше не обриває живий фід/бекфіл, (b) inspect-бейдж більше не показує «Невідомо» для impact з невідомим типом (InspectBadge-неконсистентність з Ф6), (c) ×N-бейдж уніфікований на один відтінок бурштинового. Внутрішні переїзди пакетів (Ф1-Ф3, Ф5) свідомо НЕ згадані в changelog — вони operator-invisible. Гейт: `npm run build` чистий (1886 модулів, APP_VERSION коректно похідний від CHANGELOG[0]='0.4.3').

## Підсумок — весь план виконано
Усі 7 фаз (Ф0 baseline → Ф1 packaging → Ф2 backend-пакети → Ф3 розбиття функцій → Ф4 backend-фікси → Ф5 frontend-переїзди → Ф6 frontend-дедуп → Ф7 docs+changelog) завершені 2026-07-13, behavior-preserving на всіх кроках (run_eval/track_eval == Ф0 точно на кожному backend-гейті). Ф1-Ф3 закомічено (e7cea40); Ф4-Ф6 закомічено (a3d2948); Ф7 — цей коміт. Конвенції-фундамент нижче лишаються чинними для майбутнього росту коду.

## Чого НЕ робити (guardrails)
- Editable install / packaging-машинерія — 12 sys.path-рядків лишаються.
- Re-export shims старих шляхів — усі споживачі в репо, тести ловлять.
- Barrel-файли: `domain/`, `pipeline/`, `feeds/` `__init__` — порожні; лише `parsing/` має API.
- FeedSource ABC/protocol — фіди ділять тільки `build_matcher()`.
- Розбиття models.py/schemas.py/config.py/store.ts — когезивні файли ≤320 рядків.
- DI/event bus/plugin registry для предикатів чи handler-ів — plain if-послідовності.
- Перейменування доменного словника (Broadcast, ParseResult, DistrictMatcher, track/pulse/citywide) — WORKFLOW.md і ментальна модель мейнтейнера індексовані на ці імена.
- Повний «вибух» MapView/ThreatLog на підкомпоненти — виносимо лише те, що потребує дедуплікація.

## Конвенції-фундамент (закріпити після серії, дописати в CLAUDE.md у Ф7)
- Правило розміщення: текст→структура = `parsing/` (словники ТІЛЬКИ у vocab.py); переходи DB-стану = `domain/`; усе, що торкається ingest-lock чи Broadcast = `pipeline/`; усе з мережевим сокетом = `feeds/`; форма HTTP/WS = `api/`.
- Напрям імпортів — закон: parsing ← domain ← pipeline ← feeds; api ← domain; ніхто не імпортує main/worker. Lazy-імпорт у функції = smell (легітимні лише optional-startup у main.lifespan). Виняток: `feeds/health.py` — використовується і `pipeline/sweeper.py`, і `main.py` (health = process-liveness leaf без залежностей назад на pipeline/feeds), тому pipeline легітимно імпортує саме цей один модуль з feeds/.
- Новий домен-модуль ⇒ тест-модуль з тим самим ім'ям. Символ, імпортований іншим app-модулем, втрачає підкреслення.
- Новий tunable ⇒ config.py з коментарем про емпіричну основу; нове слово-фільтр ⇒ vocab.py + рядок у eval_set.
- Frontend: спільна threat-презентація тільки в threatDisplay.tsx, кольори тільки в theme.ts, localStorage тільки через lib/storage.ts, видимі рядки тільки через t().
- Ритуал Ф0 («записати eval-числа до, звірити після») — для БУДЬ-ЯКОЇ зміни parser/tracking/ingest, не лише рефакторингу.

## Верифікація
Кожна фаза: повний гейт (див. вище). Ф3 — eval-числа звіряти з Ф0 точно. Ф2 — додатково прогнати suite двічі поспіль (перевірка, що скиди глобалів у conftest справді ізолюють). Ф5/Ф6 — build + візуальний smoke проти `REPLAY_REAL_DATA=true`. Після кожної фази — діф готовий, СТОП до «пуш»/«комітимо».

## Ключові файли
- Розрізи: `backend/app/parser.py`, `backend/app/ingest.py`, `backend/app/telegram_listener.py`, `frontend/src/geo.ts`
- Оновлення call sites: `backend/tests/conftest.py` (глобали ingest/broadcast!), 14 тестів, `backend/eval/*.py`, `backend/scripts/*.py`, `backend/migrations/env.py` (не ламається — models.py не їде)
- Дедуплікація FE: `frontend/src/components/{ThreatLog,MapView}.tsx`, `theme.ts`, `threatIcons.ts`, `store.ts`
- Docs: `CLAUDE.md`, `WORKFLOW.md`
