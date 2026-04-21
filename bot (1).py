import logging
import json
import os
import asyncio
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATA_FILE = "data.json"

CLASSES = {
    "warrior": {"name": "⚔️ Воин",    "desc": "Бонус +20% XP за тренировки.", "bonus": "workout"},
    "ranger":  {"name": "🏹 Рейнджер", "desc": "Бонус +20% XP за шаги.",       "bonus": "steps"},
    "mage":    {"name": "🧙 Маг",      "desc": "Бонус +20% XP за питание.",     "bonus": "food"},
}

SKILLS = {
    "iron_will": {"name": "🔥 Железная воля",  "desc": "+10% XP за всё",           "cost": 50},
    "fast_legs": {"name": "💨 Быстрые ноги",   "desc": "+500 бонус шагов",         "cost": 80},
    "meal_prep": {"name": "🍗 Мастер готовки", "desc": "+15% XP за питание",       "cost": 60},
    "berserker": {"name": "💢 Берсерк",         "desc": "3 дня подряд = 3x XP",    "cost": 120},
}

BOSSES = [
    {"name": "🐷 Жирный Гоблин",     "hp": 100,  "reward_xp": 200,  "reward_sp": 30,  "min_level": 1},
    {"name": "🐻 Медведь Лени",      "hp": 300,  "reward_xp": 500,  "reward_sp": 60,  "min_level": 5},
    {"name": "🐉 Дракон Бездействия","hp": 700,  "reward_xp": 1200, "reward_sp": 120, "min_level": 10},
    {"name": "👾 Повелитель Диванов","hp": 1500, "reward_xp": 3000, "reward_sp": 250, "min_level": 20},
]

LEVEL_XP = [0,100,250,500,900,1400,2000,2800,3800,5000,6500,8500,11000,14000,18000,23000,29000,36000,45000,55000,70000]

TITLES = {1:"🥉 Новобранец",3:"🥈 Искатель",5:"🥇 Воитель",8:"💎 Элита",10:"🏆 Легенда",15:"⭐ Мастер",20:"🌟 Чемпион"}

EX_NAMES = {
    "bridge":    ("🍑 Ягодичный мост", 20),
    "leg_raise": ("🦵 Подъём ног",     15),
    "plank":     ("🧗 Планка",         25),
    "pushup":    ("💪 Отжимания",      30),
    "crunch":    ("🌀 Скручивания",    15),
    "lateral":   ("🤸 Разведение рук", 15),
}

FOOD_DATA = {
    "breakfast":    ("🍳 Завтрак",        450, 30),
    "lunch":        ("🍗 Обед с белком",  400, 35),
    "dinner":       ("🍚 Ужин",           650, 55),
    "snack":        ("🥛 Перекус йогурт", 180, 15),
    "cola_zero":    ("🥤 Кола Zero",      0,   0),
    "cola_regular": ("🥤 Обычная кола",   240, 0),
    "cheat":        ("🌯 Донер-читмил",   700, 25),
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(uid, data):
    if uid not in data:
        data[uid] = {
            "name": "Герой", "class": None, "level": 1, "xp": 0, "sp": 0,
            "skills": {}, "streak": 0, "last_active": None,
            "boss_hp": None, "boss_index": 0,
            "today": {"date": str(date.today()), "steps": 0, "workouts": [], "calories": 0, "protein": 0}
        }
    u = data[uid]
    if u["today"]["date"] != str(date.today()):
        u["today"] = {"date": str(date.today()), "steps": 0, "workouts": [], "calories": 0, "protein": 0}
    return u

def get_title(level):
    t = "🥉 Новобранец"
    for lvl, title in TITLES.items():
        if level >= lvl: t = title
    return t

def xp_next(level):
    return LEVEL_XP[min(level, len(LEVEL_XP)-1)]

def add_xp(user, amount, source=""):
    bonus = 1.0
    cls = user.get("class")
    if cls == "warrior" and source == "workout": bonus = 1.2
    elif cls == "ranger" and source == "steps":  bonus = 1.2
    elif cls == "mage"   and source == "food":   bonus = 1.2
    if user["skills"].get("iron_will"): bonus += 0.1
    final = int(amount * bonus)
    user["xp"] += final
    leveled = []
    while user["level"] < len(LEVEL_XP)-1 and user["xp"] >= xp_next(user["level"]):
        user["level"] += 1
        user["sp"] += 10
        leveled.append(user["level"])
    msg = f"+{final} XP"
    if leveled: msg += f"\n🎉 *LEVEL UP!* Уровень {leveled[-1]}\\! +10 SP"
    return msg

def boss_hit(user, dmg):
    bosses = [b for b in BOSSES if b["min_level"] <= user["level"]]
    if not bosses: return ""
    idx = min(user.get("boss_index", 0), len(bosses)-1)
    boss = bosses[idx]
    if user["boss_hp"] is None: user["boss_hp"] = boss["hp"]
    user["boss_hp"] -= dmg
    if user["boss_hp"] <= 0:
        user["boss_hp"] = None
        user["boss_index"] = (user.get("boss_index", 0) + 1) % len(BOSSES)
        xp_msg = add_xp(user, boss["reward_xp"], "boss")
        user["sp"] += boss["reward_sp"]
        return f"\n\n⚔️ *БОСС ПОВЕРЖЕН\\!* {boss['name']}\n🏆 {xp_msg}, \\+{boss['reward_sp']} SP"
    bar = "█" * int(user["boss_hp"]/boss["hp"]*10) + "░" * (10 - int(user["boss_hp"]/boss["hp"]*10))
    return f"\n\n💥 Урон: \\-{dmg} HP\n{boss['name']}: {bar} {user['boss_hp']}/{boss['hp']}"

def update_streak(user):
    today_str = str(date.today())
    last = user.get("last_active")
    if last is None: user["streak"] = 1
    elif last == today_str: pass
    else:
        from datetime import date as d
        last_date = d.fromisoformat(last)
        user["streak"] = user["streak"] + 1 if (date.today() - last_date).days == 1 else 1
    user["last_active"] = today_str

def bar(cur, mx, n=12):
    f = int(max(0,cur)/max(1,mx)*n)
    return "█"*f + "░"*(n-f)

# ── КОМАНДЫ ──────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    user["name"] = update.effective_user.first_name or "Герой"
    save_data(data)
    await update.message.reply_text(
        f"⚔️ *Добро пожаловать в FITNESS RPG, {user['name']}\\!*\n\n"
        "Тело — это персонаж\\.\nТренировки и шаги — это XP\\.\nПобеждай боссов\\. Качай скиллы\\.\n\n"
        "Выбери свой *класс*:",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⚔️ Воин",    callback_data="class_warrior"),
            InlineKeyboardButton("🏹 Рейнджер", callback_data="class_ranger"),
            InlineKeyboardButton("🧙 Маг",      callback_data="class_mage"),
        ]])
    )

async def profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    save_data(data)
    if not user["class"]:
        await update.message.reply_text("Сначала выбери класс → /start"); return
    cls = CLASSES[user["class"]]
    lvl = user["level"]
    xp = user["xp"]
    nx = xp_next(lvl)
    today = user["today"]
    steps_bar = bar(today["steps"], 9000, 10)
    xp_bar = bar(xp, nx, 12)

    boss_line = ""
    bosses = [b for b in BOSSES if b["min_level"] <= lvl]
    if bosses:
        idx = min(user.get("boss_index",0), len(bosses)-1)
        boss = bosses[idx]
        hp = user["boss_hp"] if user["boss_hp"] is not None else boss["hp"]
        boss_line = f"\n\n🐉 *Босс:* {boss['name']}\n{bar(hp, boss['hp'], 10)} {hp}/{boss['hp']}"

    skills_owned = [SKILLS[s]["name"] for s in user["skills"] if user["skills"][s]]
    skills_line = f"\n⚡ {', '.join(skills_owned)}" if skills_owned else ""

    await update.message.reply_text(
        f"{cls['name']} *{user['name']}* — {get_title(lvl)}\n\n"
        f"🏅 Уровень: *{lvl}*\n"
        f"✨ XP: {xp}/{nx}  {xp_bar}\n"
        f"💎 SP: {user['sp']}\n"
        f"🔥 Streak: {user['streak']} дней"
        f"{skills_line}"
        f"{boss_line}\n\n"
        f"*Сегодня:*\n"
        f"👟 Шаги: {today['steps']}/9000  {steps_bar}\n"
        f"🏋️ Тренировок: {len(today['workouts'])}\n"
        f"🍗 Белок: {today['protein']}г / 145г",
        parse_mode="Markdown"
    )

async def steps_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    args = ctx.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Напиши: `/steps 8500`", parse_mode="Markdown")
        save_data(data); return
    steps = int(args[0])
    user["today"]["steps"] = steps
    xp_msg = add_xp(user, steps // 100, "steps")
    boss_msg = boss_hit(user, steps // 500)
    update_streak(user)
    save_data(data)
    pct = min(100, int(steps/9000*100))
    await update.message.reply_text(
        f"👟 *Шаги: {steps:,}*\n{bar(steps,9000,12)} {pct}%\n\n{xp_msg}{boss_msg}",
        parse_mode="Markdown"
    )

async def workout_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data(); save_data(data)
    await update.message.reply_text(
        "🏋️ *Что сделал?* Выбирай:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🍑 Ягодичный мост", callback_data="ex_bridge"),
             InlineKeyboardButton("🦵 Подъём ног",     callback_data="ex_leg_raise")],
            [InlineKeyboardButton("🧗 Планка",         callback_data="ex_plank"),
             InlineKeyboardButton("💪 Отжимания",      callback_data="ex_pushup")],
            [InlineKeyboardButton("🌀 Скручивания",    callback_data="ex_crunch"),
             InlineKeyboardButton("🤸 Разведение рук", callback_data="ex_lateral")],
            [InlineKeyboardButton("✅ Готово!",         callback_data="ex_done")],
        ])
    )

async def food_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data(); save_data(data)
    await update.message.reply_text(
        "🍽️ *Что ел?* Отмечай:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🍳 Завтрак",       callback_data="food_breakfast"),
             InlineKeyboardButton("🍗 Обед",          callback_data="food_lunch")],
            [InlineKeyboardButton("🍚 Ужин",          callback_data="food_dinner"),
             InlineKeyboardButton("🥛 Перекус",       callback_data="food_snack")],
            [InlineKeyboardButton("🥤 Кола Zero ✅",  callback_data="food_cola_zero"),
             InlineKeyboardButton("🥤 Обычная кола ❌",callback_data="food_cola_regular")],
            [InlineKeyboardButton("🌯 Донер (читмил)", callback_data="food_cheat"),
             InlineKeyboardButton("✅ Сохранить",      callback_data="food_done")],
        ])
    )

async def skills_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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
        f"⚡ *Скиллы*\nТвои SP: 💎 {user['sp']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def boss_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    bosses = [b for b in BOSSES if b["min_level"] <= user["level"]]
    if not bosses:
        await update.message.reply_text("Качайся до 1 уровня сначала!")
        save_data(data); return
    idx = min(user.get("boss_index",0), len(bosses)-1)
    boss = bosses[idx]
    hp = user["boss_hp"] if user["boss_hp"] is not None else boss["hp"]
    save_data(data)
    await update.message.reply_text(
        f"🐉 *БОСС: {boss['name']}*\n\n"
        f"HP: {bar(hp, boss['hp'], 14)}\n{hp}/{boss['hp']}\n\n"
        f"Атакуй шагами и тренировками\\!\n"
        f"500 шагов = \\-1 HP\n"
        f"Упражнение = \\-15 HP\n\n"
        f"Награда: 🏆 {boss['reward_xp']} XP \\+ {boss['reward_sp']} SP",
        parse_mode="MarkdownV2"
    )

async def summary_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    user = get_user(uid, data)
    save_data(data)
    t = user["today"]
    await update.message.reply_text(
        f"📊 *Итог дня — {t['date']}*\n\n"
        f"{'✅' if t['steps']>=9000 else '❌'} Шаги: {t['steps']:,}/9000\n"
        f"{'✅' if t['workouts'] else '❌'} Тренировок: {len(t['workouts'])}\n"
        f"  {', '.join(t['workouts']) if t['workouts'] else 'нет'}\n"
        f"{'✅' if t['protein']>=120 else '⚠️'} Белок: {t['protein']}г/145г\n"
        f"🔥 Калории: {t['calories']} ккал\n\n"
        f"🔥 Streak: {user['streak']} дней подряд\n"
        f"✨ XP: {user['xp']}  💎 SP: {user['sp']}",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚔️ *FITNESS RPG — Команды*\n\n"
        "/profile — персонаж и статы\n"
        "/steps 8000 — записать шаги\n"
        "/workout — отметить тренировку\n"
        "/food — записать еду\n"
        "/skills — купить скиллы\n"
        "/boss — текущий босс\n"
        "/summary — итог дня",
        parse_mode="Markdown"
    )

# ── КНОПКИ ───────────────────────────────

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
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
                f"{cls['name']} *Класс выбран\\!*\n\n{cls['desc']}\n\n"
                "/profile — посмотреть персонажа\n"
                "/steps 5000 — записать шаги\n"
                "/workout — тренировка\n"
                "/help — все команды",
                parse_mode="MarkdownV2"
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
            else:
                await q.answer("Уже записано!", show_alert=True)
        return

    if cb == "ex_done":
        w = user["today"]["workouts"]
        save_data(data)
        await q.edit_message_text(
            f"🏋️ *Записано {len(w)} упражнений*\n\n" +
            ("\n".join(w) if w else "Ничего не выбрано") +
            "\n\n/profile — посмотреть прогресс",
            parse_mode="Markdown"
        )
        return

    if cb.startswith("food_") and cb != "food_done":
        fid = cb[5:]
        if fid in FOOD_DATA:
            name, kcal, prot = FOOD_DATA[fid]
            user["today"]["calories"] += kcal
            user["today"]["protein"]  += prot
            xp_val = max(0, kcal // 20) if fid != "cola_regular" else -10
            xp_msg = add_xp(user, xp_val, "food") if xp_val > 0 else "−10 XP 😅"
            save_data(data)
            await q.answer(f"{name}: {xp_msg}", show_alert=True)
        return

    if cb == "food_done":
        t = user["today"]
        save_data(data)
        await q.edit_message_text(
            f"🍽️ *Питание сохранено*\n\n"
            f"🔥 Калории: {t['calories']} ккал\n"
            f"🥩 Белок: {t['protein']}г\n\n"
            f"{'✅ Белка достаточно!' if t['protein']>=120 else '⚠️ Добавь белка, цель 145г'}",
            parse_mode="Markdown"
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
                await q.answer(f"✅ Куплено: {sk['name']}! −{sk['cost']} SP", show_alert=True)
            else:
                await q.answer(f"Нужно {sk['cost']} SP, у тебя {user['sp']}", show_alert=True)
        return

    save_data(data)

# ── ЗАПУСК ───────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("steps",   steps_cmd))
    app.add_handler(CommandHandler("workout", workout_cmd))
    app.add_handler(CommandHandler("food",    food_cmd))
    app.add_handler(CommandHandler("skills",  skills_cmd))
    app.add_handler(CommandHandler("boss",    boss_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("help",    help_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("⚔️ Fitness RPG Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
