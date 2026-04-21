"""
⚔️ FITNESS RPG BOT
Твой персональный RPG-трекер здоровья в Telegram
"""

import logging
import json
import os
import asyncio
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
DATA_FILE = "data.json"

# ══════════════════════════════════════════
# RPG КОНСТАНТЫ
# ══════════════════════════════════════════

CLASSES = {
    "warrior": {
        "name": "⚔️ Воин",
        "desc": "Сила и выносливость. Бонус +20% XP за тренировки.",
        "bonus": "workout",
        "emoji": "⚔️"
    },
    "ranger": {
        "name": "🏹 Рейнджер",
        "desc": "Скорость и ловкость. Бонус +20% XP за шаги и кардио.",
        "bonus": "steps",
        "emoji": "🏹"
    },
    "mage": {
        "name": "🧙 Маг",
        "desc": "Дисциплина разума. Бонус +20% XP за питание и сон.",
        "bonus": "food",
        "emoji": "🧙"
    }
}

SKILLS = {
    "iron_will":   {"name": "🔥 Железная воля",   "desc": "+10% XP за любое действие",     "cost": 50,  "unlocked": False},
    "fast_legs":   {"name": "💨 Быстрые ноги",     "desc": "+500 бонусных шагов в день",    "cost": 80,  "unlocked": False},
    "meal_prep":   {"name": "🍗 Мастер готовки",   "desc": "+15% XP за питание",            "cost": 60,  "unlocked": False},
    "night_owl":   {"name": "🦉 Ночная стража",    "desc": "Ночные тренировки дают 2x XP",  "cost": 100, "unlocked": False},
    "berserker":   {"name": "💢 Берсерк",           "desc": "3 дня подряд = 3x XP на 4й",   "cost": 120, "unlocked": False},
}

BOSSES = [
    {"name": "🐷 Жирный Гоблин",    "hp": 100,  "reward_xp": 200,  "reward_sp": 30,  "min_level": 1},
    {"name": "🐻 Медведь Лени",     "hp": 300,  "reward_xp": 500,  "reward_sp": 60,  "min_level": 5},
    {"name": "🐉 Дракон Бездействия","hp": 700, "reward_xp": 1200, "reward_sp": 120, "min_level": 10},
    {"name": "👾 Повелитель Диванов","hp": 1500, "reward_xp": 3000, "reward_sp": 250, "min_level": 20},
]

LEVEL_THRESHOLDS = [0, 100, 250, 500, 900, 1400, 2000, 2800, 3800, 5000,
                    6500, 8500, 11000, 14000, 18000, 23000, 29000, 36000, 45000, 55000, 70000]

TITLES = {
    1:  "🥉 Новобранец",
    3:  "🥈 Искатель",
    5:  "🥇 Воитель",
    8:  "💎 Элита",
    10: "🏆 Легенда",
    15: "⭐ Мастер",
    20: "🌟 Чемпион",
}

# ══════════════════════════════════════════
# РАБОТА С ДАННЫМИ
# ══════════════════════════════════════════

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(user_id: str, data: dict) -> dict:
    if user_id not in data:
        data[user_id] = {
            "name": "Герой",
            "class": None,
            "level": 1,
            "xp": 0,
            "sp": 0,  # skill points
            "skills": {},
            "streak": 0,
            "last_active": None,
            "boss_hp": None,
            "boss_index": 0,
            "history": [],
            "today": {
                "date": str(date.today()),
                "steps": 0,
                "workouts": [],
                "food_logged": False,
                "calories": 0,
                "protein": 0,
            }
        }
    u = data[user_id]
    if u["today"]["date"] != str(date.today()):
        u["today"] = {
            "date": str(date.today()),
            "steps": 0,
            "workouts": [],
            "food_logged": False,
            "calories": 0,
            "protein": 0,
        }
    return u

def get_level_title(level: int) -> str:
    title = "🥉 Новобранец"
    for lvl, t in TITLES.items():
        if level >= lvl:
            title = t
    return title

def xp_for_next(level: int) -> int:
    if level >= len(LEVEL_THRESHOLDS) - 1:
        return LEVEL_THRESHOLDS[-1]
    return LEVEL_THRESHOLDS[level]

def add_xp(user: dict, amount: int, source: str = "") -> str:
    cls = user.get("class")
    bonus = 1.0

    if cls == "warrior" and source == "workout":
        bonus = 1.2
    elif cls == "ranger" and source == "steps":
        bonus = 1.2
    elif cls == "mage" and source == "food":
        bonus = 1.2

    if user["skills"].get("iron_will"):
        bonus += 0.1

    final = int(amount * bonus)
    user["xp"] += final

    leveled = []
    while user["level"] < len(LEVEL_THRESHOLDS) - 1 and user["xp"] >= xp_for_next(user["level"]):
        user["level"] += 1
        user["sp"] += 10
        leveled.append(user["level"])

    msg = f"+{final} XP"
    if leveled:
        msg += f"\n🎉 *LEVEL UP!* Уровень {leveled[-1]}! +10 SP"
    return msg

def boss_damage(user: dict, dmg: int) -> str:
    if user["boss_hp"] is None:
        boss_idx = user.get("boss_index", 0)
        bosses = [b for b in BOSSES if b["min_level"] <= user["level"]]
        if not bosses:
            return ""
        idx = min(boss_idx, len(bosses) - 1)
        user["boss_hp"] = bosses[idx]["hp"]

    user["boss_hp"] -= dmg
    boss_idx = min(user.get("boss_index", 0), len(BOSSES) - 1)
    bosses_avail = [b for b in BOSSES if b["min_level"] <= user["level"]]
    if not bosses_avail:
        return ""

    boss = bosses_avail[min(user.get("boss_index", 0), len(bosses_avail) - 1)]

    if user["boss_hp"] <= 0:
        user["boss_hp"] = None
        user["boss_index"] = (user.get("boss_index", 0) + 1) % len(BOSSES)
        xp_msg = add_xp(user, boss["reward_xp"], "boss")
        user["sp"] += boss["reward_sp"]
        return (
            f"\n\n⚔️ *БОСС ПОВЕРЖЕН!* {boss['name']}\n"
            f"🏆 Награда: {xp_msg}, +{boss['reward_sp']} SP"
        )
    else:
        hp_bar = make_bar(user["boss_hp"], boss["hp"], 10)
        return f"\n\n💥 Урон боссу: -{dmg} HP\n{boss['name']}: {hp_bar} {max(0, user['boss_hp'])}/{boss['hp']}"

def make_bar(current, maximum, length=10) -> str:
    filled = int((max(0, current) / maximum) * length)
    return "█" * filled + "░" * (length - filled)

# ══════════════════════════════════════════
# КОМАНДЫ
# ══════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    user["name"] = update.effective_user.first_name or "Герой"
    save_data(data)

    await update.message.reply_text(
        f"⚔️ *Добро пожаловать в FITNESS RPG, {user['name']}!*\n\n"
        "Твоё тело — это твой персонаж.\n"
        "Тренировки, шаги и питание = XP и уровни.\n"
        "Побеждай боссов. Качай скиллы. Становись легендой.\n\n"
        "Для начала — выбери свой *класс*:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚔️ Воин", callback_data="class_warrior"),
             InlineKeyboardButton("🏹 Рейнджер", callback_data="class_ranger"),
             InlineKeyboardButton("🧙 Маг", callback_data="class_mage")]
        ])
    )

async def profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    save_data(data)

    if not user["class"]:
        await update.message.reply_text("Сначала выбери класс — напиши /start")
        return

    cls = CLASSES[user["class"]]
    lvl = user["level"]
    xp = user["xp"]
    next_xp = xp_for_next(lvl)
    xp_bar = make_bar(xp, next_xp, 12)
    title = get_level_title(lvl)

    boss_line = ""
    if user.get("boss_hp") is not None:
        bosses_avail = [b for b in BOSSES if b["min_level"] <= lvl]
        if bosses_avail:
            boss = bosses_avail[min(user.get("boss_index", 0), len(bosses_avail) - 1)]
            hp_bar = make_bar(user["boss_hp"], boss["hp"], 10)
            boss_line = f"\n\n🐉 *ТЕКУЩИЙ БОСС:* {boss['name']}\n{hp_bar} {user['boss_hp']}/{boss['hp']} HP"

    skills_line = ""
    active_skills = [SKILLS[s]["name"] for s in user["skills"] if user["skills"][s]]
    if active_skills:
        skills_line = f"\n⚡ Скиллы: {', '.join(active_skills)}"

    today = user["today"]
    steps_bar = make_bar(today["steps"], 9000, 10)

    await update.message.reply_text(
        f"{cls['emoji']} *{user['name']}* — {title}\n"
        f"Класс: {cls['name']}\n\n"
        f"🏅 Уровень: *{lvl}*\n"
        f"✨ XP: {xp}/{next_xp}\n"
        f"{xp_bar}\n"
        f"💎 SP (очки скиллов): {user['sp']}\n"
        f"🔥 Streak: {user['streak']} дней подряд"
        f"{skills_line}"
        f"{boss_line}\n\n"
        f"*Сегодня:*\n"
        f"👟 Шаги: {today['steps']}/9000 {steps_bar}\n"
        f"🏋️ Тренировок: {len(today['workouts'])}\n"
        f"🍗 Белок: {today['protein']}г / цель 145г",
        parse_mode="Markdown"
    )

async def steps_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)

    args = ctx.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "Напиши количество шагов:\n`/steps 8500`",
            parse_mode="Markdown"
        )
        save_data(data)
        return

    steps = int(args[0])
    user["today"]["steps"] = steps

    xp_gain = steps // 100
    xp_msg = add_xp(user, xp_gain, "steps")
    dmg = steps // 500
    boss_msg = boss_damage(user, dmg)

    steps_bar = make_bar(steps, 9000, 12)
    goal_pct = min(100, int(steps / 9000 * 100))

    update_streak(user)
    save_data(data)

    await update.message.reply_text(
        f"👟 *Шаги записаны: {steps:,}*\n"
        f"{steps_bar} {goal_pct}%\n\n"
        f"{xp_msg}"
        f"{boss_msg}",
        parse_mode="Markdown"
    )

async def workout_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    save_data(data)

    await update.message.reply_text(
        "🏋️ *Что сделал сегодня?*\n\nВыбери упражнения:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🍑 Ягодичный мост", callback_data="ex_bridge"),
             InlineKeyboardButton("🦵 Подъём ног", callback_data="ex_leg_raise")],
            [InlineKeyboardButton("🧗 Планка", callback_data="ex_plank"),
             InlineKeyboardButton("💪 Отжимания", callback_data="ex_pushup")],
            [InlineKeyboardButton("🌀 Скручивания", callback_data="ex_crunch"),
             InlineKeyboardButton("🤸 Разведение рук", callback_data="ex_lateral")],
            [InlineKeyboardButton("✅ Готово!", callback_data="ex_done")]
        ])
    )

async def food_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    save_data(data)

    await update.message.reply_text(
        "🍽️ *Что ел сегодня?*\nВыбери приёмы пищи:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🍳 Завтрак (яйца+творог)", callback_data="food_breakfast"),
             InlineKeyboardButton("🍗 Обед с белком", callback_data="food_lunch")],
            [InlineKeyboardButton("🍚 Ужин (грудка+гарнир)", callback_data="food_dinner"),
             InlineKeyboardButton("🥛 Перекус йогурт", callback_data="food_snack")],
            [InlineKeyboardButton("🥤 Кола Zero (молодец)", callback_data="food_cola_zero"),
             InlineKeyboardButton("🥤 Обычная кола (ай-ай)", callback_data="food_cola_regular")],
            [InlineKeyboardButton("🌯 Донер (день читмила)", callback_data="food_cheat"),
             InlineKeyboardButton("✅ Сохранить", callback_data="food_done")]
        ])
    )

async def skills_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    save_data(data)

    sp = user["sp"]
    buttons = []
    for skill_id, skill in SKILLS.items():
        owned = user["skills"].get(skill_id, False)
        label = f"{'✅' if owned else '🔒'} {skill['name']} ({skill['cost']} SP)"
        buttons.append([InlineKeyboardButton(label, callback_data=f"skill_{skill_id}")])

    await update.message.reply_text(
        f"⚡ *Дерево скиллов*\n\nТвои SP: 💎 {sp}\n\nВыбери скилл для покупки/просмотра:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def boss_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)

    bosses_avail = [b for b in BOSSES if b["min_level"] <= user["level"]]
    if not bosses_avail:
        await update.message.reply_text("Ты ещё не достаточно крут для боссов. Качайся дальше! 💪")
        save_data(data)
        return

    boss_idx = min(user.get("boss_index", 0), len(bosses_avail) - 1)
    boss = bosses_avail[boss_idx]

    if user["boss_hp"] is None:
        user["boss_hp"] = boss["hp"]

    hp_bar = make_bar(user["boss_hp"], boss["hp"], 14)
    save_data(data)

    await update.message.reply_text(
        f"🐉 *БОСС: {boss['name']}*\n\n"
        f"HP: {hp_bar}\n"
        f"{user['boss_hp']}/{boss['hp']}\n\n"
        f"Атакуй его через шаги и тренировки!\n"
        f"Каждые 500 шагов = -{boss['hp']//20} HP боссу\n"
        f"Каждое упражнение = -15 HP боссу\n\n"
        f"Награда за победу: 🏆 {boss['reward_xp']} XP + {boss['reward_sp']} SP",
        parse_mode="Markdown"
    )

async def summary_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    save_data(data)

    today = user["today"]
    steps = today["steps"]
    workouts = today["workouts"]
    protein = today["protein"]
    calories = today["calories"]

    steps_ok = "✅" if steps >= 9000 else "❌"
    workout_ok = "✅" if len(workouts) >= 1 else "❌"
    protein_ok = "✅" if protein >= 120 else "⚠️" if protein >= 80 else "❌"

    total_xp = user["xp"]
    lvl = user["level"]
    next_xp = xp_for_next(lvl)
    xp_bar = make_bar(total_xp, next_xp, 12)

    await update.message.reply_text(
        f"📊 *Итог дня — {today['date']}*\n\n"
        f"{steps_ok} Шаги: {steps:,}/9000\n"
        f"{workout_ok} Тренировок: {len(workouts)}\n"
        f"  {', '.join(workouts) if workouts else 'нет'}\n"
        f"{protein_ok} Белок: {protein}г/145г\n"
        f"🔥 Калории: {calories} ккал\n\n"
        f"✨ XP: {total_xp}/{next_xp}\n"
        f"{xp_bar}\n"
        f"🔥 Streak: {user['streak']} дней",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚔️ *FITNESS RPG — Команды*\n\n"
        "👤 /profile — твой персонаж\n"
        "👟 /steps 8000 — записать шаги\n"
        "🏋️ /workout — отметить тренировку\n"
        "🍽️ /food — записать еду\n"
        "⚡ /skills — дерево скиллов\n"
        "🐉 /boss — текущий босс\n"
        "📊 /summary — итог дня\n\n"
        "Каждый день активности = streak 🔥\n"
        "3 дня подряд = бонус XP\n"
        "Побеждай боссов, качай скиллы!",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════
# CALLBACK HANDLERS
# ══════════════════════════════════════════

EX_NAMES = {
    "bridge":    ("🍑 Ягодичный мост", 20),
    "leg_raise": ("🦵 Подъём ног", 15),
    "plank":     ("🧗 Планка", 25),
    "pushup":    ("💪 Отжимания", 30),
    "crunch":    ("🌀 Скручивания", 15),
    "lateral":   ("🤸 Разведение рук", 15),
}

FOOD_DATA = {
    "breakfast": ("🍳 Завтрак", 450, 30),
    "lunch":     ("🍗 Обед с белком", 400, 35),
    "dinner":    ("🍚 Ужин", 650, 55),
    "snack":     ("🥛 Перекус", 180, 15),
    "cola_zero": ("🥤 Кола Zero", 0, 0),
    "cola_regular": ("🥤 Обычная кола (−10 XP 😅)", 240, 0),
    "cheat":     ("🌯 Читмил-донер", 700, 25),
}

def update_streak(user: dict):
    today_str = str(date.today())
    last = user.get("last_active")
    if last is None:
        user["streak"] = 1
    elif last == today_str:
        pass
    else:
        from datetime import timedelta
        last_date = date.fromisoformat(last)
        if (date.today() - last_date).days == 1:
            user["streak"] += 1
        else:
            user["streak"] = 1
    user["last_active"] = today_str

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    uid = str(query.from_user.id)
    user = get_user(uid, data)
    cb = query.data

    # CLASS SELECT
    if cb.startswith("class_"):
        cls_id = cb.replace("class_", "")
        if cls_id in CLASSES:
            user["class"] = cls_id
            cls = CLASSES[cls_id]
            save_data(data)
            await query.edit_message_text(
                f"{cls['emoji']} *Ты выбрал класс: {cls['name']}*\n\n"
                f"{cls['desc']}\n\n"
                f"Начни свой путь!\n"
                f"/profile — посмотреть персонажа\n"
                f"/steps 5000 — записать шаги\n"
                f"/workout — отметить тренировку\n"
                f"/help — все команды",
                parse_mode="Markdown"
            )
        return

    # EXERCISES
    if cb.startswith("ex_") and cb != "ex_done":
        ex_id = cb.replace("ex_", "")
        if ex_id in EX_NAMES:
            name, xp_val = EX_NAMES[ex_id]
            if name not in user["today"]["workouts"]:
                user["today"]["workouts"].append(name)
                xp_msg = add_xp(user, xp_val, "workout")
                boss_msg = boss_damage(user, 15)
                update_streak(user)
                save_data(data)
                await query.answer(f"{name}: {xp_msg}{' | Урон боссу!' if boss_msg else ''}", show_alert=True)
            else:
                await query.answer("Уже записано!", show_alert=True)
        return

    if cb == "ex_done":
        workouts = user["today"]["workouts"]
        save_data(data)
        await query.edit_message_text(
            f"🏋️ *Тренировка записана!*\n\n"
            f"Выполнено: {len(workouts)} упражнений\n"
            f"{chr(10).join(workouts) if workouts else 'Ничего не выбрано'}\n\n"
            f"Напиши /profile чтобы увидеть прогресс",
            parse_mode="Markdown"
        )
        return

    # FOOD
    if cb.startswith("food_") and cb != "food_done":
        food_id = cb.replace("food_", "")
        if food_id in FOOD_DATA:
            name, kcal, protein = FOOD_DATA[food_id]
            user["today"]["calories"] += kcal
            user["today"]["protein"] += protein
            xp_val = max(0, kcal // 20)
            if food_id == "cola_regular":
                xp_val = -10
            xp_msg = add_xp(user, xp_val, "food") if xp_val > 0 else "-10 XP 😅"
            save_data(data)
            await query.answer(f"{name}: {xp_msg}", show_alert=True)
        return

    if cb == "food_done":
        today = user["today"]
        save_data(data)
        await query.edit_message_text(
            f"🍽️ *Питание записано!*\n\n"
            f"🔥 Калории: {today['calories']} ккал\n"
            f"🥩 Белок: {today['protein']}г\n\n"
            f"{'✅ Белка достаточно!' if today['protein'] >= 120 else '⚠️ Добавь белка, цель 145г'}",
            parse_mode="Markdown"
        )
        return

    # SKILLS
    if cb.startswith("skill_"):
        skill_id = cb.replace("skill_", "")
        if skill_id in SKILLS:
            skill = SKILLS[skill_id]
            owned = user["skills"].get(skill_id, False)
            if owned:
                await query.answer(f"Уже куплено: {skill['name']}", show_alert=True)
            elif user["sp"] >= skill["cost"]:
                user["sp"] -= skill["cost"]
                user["skills"][skill_id] = True
                save_data(data)
                await query.answer(f"✅ Куплено: {skill['name']}! -{skill['cost']} SP", show_alert=True)
            else:
                await query.answer(f"Нужно {skill['cost']} SP, у тебя {user['sp']}", show_alert=True)
        return

    save_data(data)

# ══════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════

async def main():
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
    print("⚔️ Fitness RPG Bot запущен!")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())
