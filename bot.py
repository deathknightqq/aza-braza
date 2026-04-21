import json
import logging
import os
from datetime import date, datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATA_FILE = "data.json"

CLASSES = {
    "warrior": {
        "name": "⚔️ Воин",
        "desc": "Бонус +20% XP за тренировки.",
        "bonus": "workout",
    },
    "ranger": {
        "name": "🏹 Рейнджер",
        "desc": "Бонус +20% XP за шаги.",
        "bonus": "steps",
    },
    "mage": {
        "name": "🧙 Маг",
        "desc": "Бонус +20% XP за питание.",
        "bonus": "food",
    },
}

SKILLS = {
    "iron_will": {"name": "🔥 Железная воля", "desc": "+10% XP за всё", "cost": 50},
    "fast_legs": {"name": "💨 Быстрые ноги", "desc": "+500 бонус шагов", "cost": 80},
    "meal_prep": {"name": "🍗 Мастер готовки", "desc": "+15% XP за питание", "cost": 60},
    "berserker": {"name": "💢 Берсерк", "desc": "3 дня подряд = 3x XP", "cost": 120},
}

BOSSES = [
    {"name": "🐷 Жирный Гоблин", "hp": 100, "reward_xp": 200, "reward_sp": 30, "min_level": 1},
    {"name": "🐻 Медведь Лени", "hp": 300, "reward_xp": 500, "reward_sp": 60, "min_level": 5},
    {"name": "🐉 Дракон Бездействия", "hp": 700, "reward_xp": 1200, "reward_sp": 120, "min_level": 10},
    {"name": "👾 Повелитель Диванов", "hp": 1500, "reward_xp": 3000, "reward_sp": 250, "min_level": 20},
]

LEVEL_XP = [
    0, 100, 250, 500, 900, 1400, 2000, 2800, 3800, 5000,
    6500, 8500, 11000, 14000, 18000, 23000, 29000, 36000,
    45000, 55000, 70000,
]

TITLES = {
    1: "🥉 Новобранец",
    3: "🥈 Искатель",
    5: "🥇 Воитель",
    8: "💎 Элита",
    10: "🏆 Легенда",
    15: "⭐ Мастер",
    20: "🌟 Чемпион",
}

EX_NAMES = {
    "bridge": ("🍑 Ягодичный мост", 20),
    "leg_raise": ("🦵 Подъём ног", 15),
    "plank": ("🧗 Планка", 25),
    "pushup": ("💪 Отжимания", 30),
    "crunch": ("🌀 Скручивания", 15),
    "lateral": ("🤸 Разведение рук", 15),
}

FOOD_DATA = {
    "breakfast": ("🍳 Завтрак", 450, 30),
    "lunch": ("🍗 Обед с белком", 400, 35),
    "dinner": ("🍚 Ужин", 650, 55),
    "snack": ("🥛 Перекус йогурт", 180, 15),
    "cola_zero": ("🥤 Кола Zero", 0, 0),
    "cola_regular": ("🥤 Обычная кола", 240, 0),
    "cheat": ("🌯 Донер-читмил", 700, 25),
}


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.exception("Не удалось прочитать data.json")
    return {}


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def today_str() -> str:
    return str(date.today())


def get_user(uid: str, data: dict) -> dict:
    if uid not in data:
        data[uid] = {
            "name": "Герой",
            "class": None,
            "level": 1,
            "xp": 0,
            "sp": 0,
            "skills": {},
            "streak": 0,
            "last_active": None,
            "boss_hp": None,
            "boss_index": 0,
            "today": {
                "date": today_str(),
                "steps": 0,
                "workouts": [],
                "calories": 0,
                "protein": 0,
            },
        }

    user = data[uid]
    if user["today"]["date"] != today_str():
        user["today"] = {
            "date": today_str(),
            "steps": 0,
            "workouts": [],
            "calories": 0,
            "protein": 0,
        }

    return user


def get_title(level: int) -> str:
    result = "🥉 Новобранец"
    for lvl, title in TITLES.items():
        if level >= lvl:
            result = title
    return result


def xp_next(level: int) -> int:
    return LEVEL_XP[min(level, len(LEVEL_XP) - 1)]


def bar(cur: int, mx: int, n: int = 12) -> str:
    if mx <= 0:
        return "░" * n
    filled = int(max(0, cur) / mx * n)
    filled = max(0, min(n, filled))
    return "█" * filled + "░" * (n - filled)


def update_streak(user: dict) -> None:
    current = today_str()
    last = user.get("last_active")

    if last is None:
        user["streak"] = 1
    elif last == current:
        pass
    else:
        try:
            last_date = datetime.fromisoformat(last).date()
            diff = (date.today() - last_date).days
            user["streak"] = user["streak"] + 1 if diff == 1 else 1
        except Exception:
            user["streak"] = 1

    user["last_active"] = current


def add_xp(user: dict, amount: int, source: str = "") -> str:
    bonus = 1.0
    user_class = user.get("class")

    if user_class == "warrior" and source == "workout":
        bonus = 1.2
    elif user_class == "ranger" and source == "steps":
        bonus = 1.2
    elif user_class == "mage" and source == "food":
        bonus = 1.2

    if user["skills"].get("iron_will"):
        bonus += 0.1

    final = int(amount * bonus)
    user["xp"] += final
    level_ups = []

    while user["level"] < len(LEVEL_XP) - 1 and user["xp"] >= xp_next(user["level"]):
        user["level"] += 1
        user["sp"] += 10
        level_ups.append(user["level"])

    msg = f"+{final} XP"
    if level_ups:
        msg += f"\n🎉 LEVEL UP! Уровень {level_ups[-1]} | +10 SP"

    return msg


def boss_hit(user: dict, dmg: int) -> str:
    available_bosses = [b for b in BOSSES if b["min_level"] <= user["level"]]
    if not available_bosses:
        return ""

    idx = min(user.get("boss_index", 0), len(available_bosses) - 1)
    boss = available_bosses[idx]

    if user["boss_hp"] is None:
        user["boss_hp"] = boss["hp"]

    user["boss_hp"] -= dmg

    if user["boss_hp"] <= 0:
        user["boss_hp"] = None
        user["boss_index"] = (user.get("boss_index", 0) + 1) % len(BOSSES)
        xp_msg = add_xp(user, boss["reward_xp"], "boss")
        user["sp"] += boss["reward_sp"]
        return (
            f"\n\n⚔️ БОСС ПОВЕРЖЕН! {boss['name']}\n"
            f"🏆 {xp_msg}\n"
            f"💎 +{boss['reward_sp']} SP"
        )

    return (
        f"\n\n💥 Урон по боссу: -{dmg} HP\n"
        f"{boss['name']}: {bar(user['boss_hp'], boss['hp'], 10)} "
        f"{user['boss_hp']}/{boss['hp']}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    user["name"] = update.effective_user.first_name or "Герой"
    save_data(data)

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("⚔️ Воин", callback_data="class_warrior"),
            InlineKeyboardButton("🏹 Рейнджер", callback_data="class_ranger"),
            InlineKeyboardButton("🧙 Маг", callback_data="class_mage"),
        ]]
    )

    await update.message.reply_text(
        f"⚔️ Добро пожаловать в FITNESS RPG, {user['name']}!\n\n"
        "Тело — это персонаж.\n"
        "Тренировки и шаги — это XP.\n"
        "Побеждай боссов. Качай скиллы.\n\n"
        "Выбери свой класс:",
        reply_markup=keyboard,
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    save_data(data)

    if not user["class"]:
        await update.message.reply_text("Сначала выбери класс через /start")
        return

    cls = CLASSES[user["class"]]
    lvl = user["level"]
    xp = user["xp"]
    nx = xp_next(lvl)
    today = user["today"]

    boss_line = ""
    available_bosses = [b for b in BOSSES if b["min_level"] <= lvl]
    if available_bosses:
        idx = min(user.get("boss_index", 0), len(available_bosses) - 1)
        boss = available_bosses[idx]
        hp = user["boss_hp"] if user["boss_hp"] is not None else boss["hp"]
        boss_line = (
            f"\n\n🐉 Босс: {boss['name']}\n"
            f"{bar(hp, boss['hp'], 10)} {hp}/{boss['hp']}"
        )

    skills_owned = [SKILLS[s]["name"] for s in user["skills"] if user["skills"][s]]
    skills_line = f"\n⚡ Скиллы: {', '.join(skills_owned)}" if skills_owned else ""

    text = (
        f"{cls['name']} {user['name']} — {get_title(lvl)}\n\n"
        f"🏅 Уровень: {lvl}\n"
        f"✨ XP: {xp}/{nx} {bar(xp, nx, 12)}\n"
        f"💎 SP: {user['sp']}\n"
        f"🔥 Streak: {user['streak']} дней"
        f"{skills_line}"
        f"{boss_line}\n\n"
        f"Сегодня:\n"
        f"👟 Шаги: {today['steps']}/9000 {bar(today['steps'], 9000, 10)}\n"
        f"🏋️ Тренировок: {len(today['workouts'])}\n"
        f"🍗 Белок: {today['protein']}г / 145г"
    )

    await update.message.reply_text(text)


async def steps_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Напиши так: /steps 8500")
        save_data(data)
        return

    steps = int(context.args[0])
    user["today"]["steps"] = steps
    xp_msg = add_xp(user, steps // 100, "steps")
    boss_msg = boss_hit(user, steps // 500)
    update_streak(user)
    save_data(data)

    pct = min(100, int(steps / 9000 * 100))
    await update.message.reply_text(
        f"👟 Шаги: {steps}\n"
        f"{bar(steps, 9000, 12)} {pct}%\n\n"
        f"{xp_msg}{boss_msg}"
    )


async def workout_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍑 Ягодичный мост", callback_data="ex_bridge"),
            InlineKeyboardButton("🦵 Подъём ног", callback_data="ex_leg_raise"),
        ],
        [
            InlineKeyboardButton("🧗 Планка", callback_data="ex_plank"),
            InlineKeyboardButton("💪 Отжимания", callback_data="ex_pushup"),
        ],
        [
            InlineKeyboardButton("🌀 Скручивания", callback_data="ex_crunch"),
            InlineKeyboardButton("🤸 Разведение рук", callback_data="ex_lateral"),
        ],
        [InlineKeyboardButton("✅ Готово", callback_data="ex_done")],
    ])

    await update.message.reply_text("🏋️ Что сделал? Выбирай:", reply_markup=keyboard)


async def food_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍳 Завтрак", callback_data="food_breakfast"),
            InlineKeyboardButton("🍗 Обед", callback_data="food_lunch"),
        ],
        [
            InlineKeyboardButton("🍚 Ужин", callback_data="food_dinner"),
            InlineKeyboardButton("🥛 Перекус", callback_data="food_snack"),
        ],
        [
            InlineKeyboardButton("🥤 Кола Zero", callback_data="food_cola_zero"),
            InlineKeyboardButton("🥤 Обычная кола", callback_data="food_cola_regular"),
        ],
        [
            InlineKeyboardButton("🌯 Донер", callback_data="food_cheat"),
            InlineKeyboardButton("✅ Сохранить", callback_data="food_done"),
        ],
    ])

    await update.message.reply_text("🍽️ Что ел? Отмечай:", reply_markup=keyboard)


async def skills_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    save_data(data)

    buttons = []
    for sid, sk in SKILLS.items():
        owned = user["skills"].get(sid, False)
        label = f"{'✅' if owned else '🔒'} {sk['name']} ({sk['cost']} SP)"
        buttons.append([InlineKeyboardButton(label, callback_data=f"skill_{sid}")])

    await update.message.reply_text(
        f"⚡ Скиллы\nТвои SP: 💎 {user['sp']}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def boss_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)

    available_bosses = [b for b in BOSSES if b["min_level"] <= user["level"]]
    if not available_bosses:
        await update.message.reply_text("Сначала качнись хотя бы до 1 уровня.")
        save_data(data)
        return

    idx = min(user.get("boss_index", 0), len(available_bosses) - 1)
    boss = available_bosses[idx]
    hp = user["boss_hp"] if user["boss_hp"] is not None else boss["hp"]
    save_data(data)

    await update.message.reply_text(
        f"🐉 БОСС: {boss['name']}\n\n"
        f"HP: {bar(hp, boss['hp'], 14)}\n"
        f"{hp}/{boss['hp']}\n\n"
        f"500 шагов = -1 HP\n"
        f"1 упражнение = -15 HP\n\n"
        f"Награда: {boss['reward_xp']} XP и {boss['reward_sp']} SP"
    )


async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    t = user["today"]
    save_data(data)

    workouts_text = ", ".join(t["workouts"]) if t["workouts"] else "нет"

    await update.message.reply_text(
        f"📊 Итог дня — {t['date']}\n\n"
        f"{'✅' if t['steps'] >= 9000 else '❌'} Шаги: {t['steps']}/9000\n"
        f"{'✅' if t['workouts'] else '❌'} Тренировок: {len(t['workouts'])}\n"
        f"Список: {workouts_text}\n"
        f"{'✅' if t['protein'] >= 120 else '⚠️'} Белок: {t['protein']}г/145г\n"
        f"🔥 Калории: {t['calories']} ккал\n\n"
        f"🔥 Streak: {user['streak']} дней подряд\n"
        f"✨ XP: {user['xp']}\n"
        f"💎 SP: {user['sp']}"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "FITNESS RPG — Команды\n\n"
        "/profile — персонаж и статы\n"
        "/steps 8000 — записать шаги\n"
        "/workout — отметить тренировку\n"
        "/food — записать еду\n"
        "/skills — купить скиллы\n"
        "/boss — текущий босс\n"
        "/summary — итог дня"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    try:
        data = load_data()
        uid = str(q.from_user.id)
        user = get_user(uid, data)
        cb = q.data

        if cb.startswith("class_"):
            cls_id = cb[6:]
            if cls_id in CLASSES:
                user["class"] = cls_id
                save_data(data)
                cls = CLASSES[cls_id]
                await q.edit_message_text(
                    f"{cls['name']} Класс выбран!\n\n"
                    f"{cls['desc']}\n\n"
                    "Команды:\n"
                    "/profile — посмотреть персонажа\n"
                    "/steps 5000 — записать шаги\n"
                    "/workout — тренировка\n"
                    "/help — все команды"
                )
            return

        if cb.startswith("ex_") and cb != "ex_done":
            ex_id = cb[3:]
            if ex_id in EX_NAMES:
                name, xp_val = EX_NAMES[ex_id]
                if name not in user["today"]["workouts"]:
                    user["today"]["workouts"].append(name)
                    xp_msg = add_xp(user, xp_val, "workout")
                    boss_msg = boss_hit(user, 15)
                    update_streak(user)
                    save_data(data)
                    await q.answer(f"{name}: {xp_msg}", show_alert=True)

                    if boss_msg:
                        await q.message.reply_text(boss_msg)
                else:
                    await q.answer("Уже записано", show_alert=True)
            return

        if cb == "ex_done":
            w = user["today"]["workouts"]
            save_data(data)
            await q.edit_message_text(
                "🏋️ Записано упражнений: "
                f"{len(w)}\n\n"
                f"{chr(10).join(w) if w else 'Ничего не выбрано'}\n\n"
                "/profile — посмотреть прогресс"
            )
            return

        if cb.startswith("food_") and cb != "food_done":
            fid = cb[5:]
            if fid in FOOD_DATA:
                name, kcal, prot = FOOD_DATA[fid]
                user["today"]["calories"] += kcal
                user["today"]["protein"] += prot
                xp_val = max(0, kcal // 20) if fid != "cola_regular" else -10

                if xp_val > 0:
                    xp_msg = add_xp(user, xp_val, "food")
                else:
                    user["xp"] += xp_val
                    xp_msg = "-10 XP 😅"

                save_data(data)
                await q.answer(f"{name}: {xp_msg}", show_alert=True)
            return

        if cb == "food_done":
            t = user["today"]
            save_data(data)
            await q.edit_message_text(
                f"🍽️ Питание сохранено\n\n"
                f"🔥 Калории: {t['calories']} ккал\n"
                f"🥩 Белок: {t['protein']}г\n\n"
                f"{'✅ Белка достаточно' if t['protein'] >= 120 else '⚠️ Добавь белка, цель 145г'}"
            )
            return

        if cb.startswith("skill_"):
            sid = cb[6:]
            if sid in SKILLS:
                sk = SKILLS[sid]
                if user["skills"].get(sid):
                    await q.answer(f"Уже куплено: {sk['name']}", show_alert=True)
                elif user["sp"] >= sk["cost"]:
                    user["sp"] -= sk["cost"]
                    user["skills"][sid] = True
                    save_data(data)
                    await q.answer(f"✅ Куплено: {sk['name']} | -{sk['cost']} SP", show_alert=True)
                else:
                    await q.answer(f"Нужно {sk['cost']} SP, у тебя {user['sp']}", show_alert=True)
            return

        save_data(data)

    except Exception as e:
        logger.exception("Ошибка в button_handler")
        try:
            await q.answer("Ошибка в кнопке", show_alert=True)
        except Exception:
            pass
        try:
            await q.message.reply_text(f"Ошибка: {e}")
        except Exception:
            pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception", exc_info=context.error)


def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("Переменная окружения BOT_TOKEN не задана")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("steps", steps_cmd))
    app.add_handler(CommandHandler("workout", workout_cmd))
    app.add_handler(CommandHandler("food", food_cmd))
    app.add_handler(CommandHandler("skills", skills_cmd))
    app.add_handler(CommandHandler("boss", boss_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_error_handler(error_handler)

    logger.info("⚔️ Fitness RPG Bot запущен")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
