# ============================================================
# FF AutoLike Bot - Complete Single File
# Host this on Railway / Render / VPS / any Python host
# ============================================================

import os
import logging
import asyncio
from datetime import datetime, timedelta
from io import BytesIO

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputFile, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import qrcode

# ===================== CONFIG =====================
BOT_TOKEN = os.getenv("8887514582:AAGhVYsyqui7M21tqDFF-bMa70icKR-MwME", "8887514582:AAGhVYsyqui7M21tqDFF-bMa70icKR-MwME")  # <-- yahan token daalna ya ENV mein set karna
ADMIN_ID = 7088682169
UPI_ID = "1krishnam@fam"
RESULTS_GROUP_ID = -1004317507663
AUTO_LIKE_BOT = "@FreeLikeLeloBot"
MIN_RECHARGE = 10
QR_EXPIRE_MINUTES = 5

# Default settings (admin baad mein change kar sakta hai)
DEFAULT_BOT_NAME = "FF AutoLike Bot"
DEFAULT_DEV_NAME = "Admin"
DEFAULT_COMMAND = "/like"          # jo command FreeLikeLeloBot ko bhejna hai
DEFAULT_PACKAGE = {
    "name": "70 Likes Daily × 7 Days",
    "likes": 70,
    "days": 7,
    "price": 50
}

# Conversation states
WAITING_AMOUNT, WAITING_UTR, WAITING_SCREENSHOT = range(3)
ADMIN_SET_CMD, ADMIN_SET_BOTNAME, ADMIN_SET_DEVNAME, ADMIN_ADD_PKG = range(3, 7)

# In-memory storage (production mein database use karo)
users_data = {}          # user_id -> {balance, plan, days_left, uid, ...}
pending_payments = {}    # order_id -> payment info
bot_settings = {
    "bot_name": DEFAULT_BOT_NAME,
    "dev_name": DEFAULT_DEV_NAME,
    "command": DEFAULT_COMMAND,
    "packages": [DEFAULT_PACKAGE]
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ===================== HELPERS =====================
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def get_user(user_id: int) -> dict:
    if user_id not in users_data:
        users_data[user_id] = {
            "balance": 0,
            "plan": None,
            "days_left": 0,
            "uid": None,
            "active": False
        }
    return users_data[user_id]


def generate_upi_qr(amount: float) -> BytesIO:
    upi_link = f"upi://pay?pa={UPI_ID}&am={amount:.2f}&cu=INR&tn=FFAutoLike"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio


def make_order_id() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S") + str(os.urandom(2).hex())


# ===================== KEYBOARDS =====================
def user_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Recharge", callback_data="user_recharge")],
        [InlineKeyboardButton("🛒 Buy AutoLike", callback_data="user_buy")],
        [
            InlineKeyboardButton("📦 My Plan", callback_data="user_myplan"),
            InlineKeyboardButton("💰 Balance", callback_data="user_balance")
        ],
        [InlineKeyboardButton("ℹ️ Help", callback_data="user_help")]
    ])


def admin_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Pending Payments", callback_data="admin_pending")],
        [
            InlineKeyboardButton("⚙️ Set Command", callback_data="admin_setcmd"),
            InlineKeyboardButton("📅 Set Days", callback_data="admin_setdays")
        ],
        [
            InlineKeyboardButton("🏷 Set Bot Name", callback_data="admin_setbotname"),
            InlineKeyboardButton("👨‍💻 Set Dev Name", callback_data="admin_setdevname")
        ],
        [
            InlineKeyboardButton("📦 Add Package", callback_data="admin_addpkg"),
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats")
        ],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")]
    ])


# ===================== /start =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    data = get_user(uid)

    bot_name = bot_settings["bot_name"]
    dev_name = bot_settings["dev_name"]

    if is_admin(uid):
        text = (
            f"👑 <b>Admin Panel</b>\n\n"
            f"Bot: <b>{bot_name}</b>\n"
            f"Developer: <b>{dev_name}</b>\n\n"
            f"Kya karna hai?"
        )
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=admin_main_keyboard())
    else:
        plan_text = ""
        if data["plan"]:
            plan_text = f"\n📦 Active Plan: <b>{data['plan']}</b>\n⏳ Days Left: <b>{data['days_left']}</b>"
        else:
            plan_text = "\n📦 Koi active plan nahi hai"

        text = (
            f"🔥 <b>Welcome to {bot_name}</b>\n\n"
            f"💰 Balance: <b>₹{data['balance']}</b>{plan_text}\n\n"
            f"Neeche se option choose karo:"
        )
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=user_main_keyboard())


# ===================== USER: RECHARGE =====================
async def recharge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"💳 <b>Recharge</b>\n\n"
        f"Minimum amount: ₹{MIN_RECHARGE}\n\n"
        f"Kitna amount recharge karna hai? (sirf number likho)",
        parse_mode="HTML"
    )
    return WAITING_AMOUNT


async def recharge_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        if amount < MIN_RECHARGE:
            await update.message.reply_text(f"❌ Minimum ₹{MIN_RECHARGE} daalo.")
            return WAITING_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Sirf number likho (example: 50)")
        return WAITING_AMOUNT

    order_id = make_order_id()
    context.user_data["recharge_amount"] = amount
    context.user_data["order_id"] = order_id

    # Save pending
    pending_payments[order_id] = {
        "user_id": update.effective_user.id,
        "username": update.effective_user.username or "",
        "full_name": update.effective_user.full_name,
        "amount": amount,
        "status": "waiting_payment",
        "created_at": datetime.now(),
        "expire_at": datetime.now() + timedelta(minutes=QR_EXPIRE_MINUTES),
        "utr": None,
        "screenshot_id": None
    }

    qr_img = generate_upi_qr(amount)
    caption = (
        f"💳 <b>Payment QR</b>\n\n"
        f"Amount: <b>₹{amount:.2f}</b>\n"
        f"UPI: <code>{UPI_ID}</code>\n"
        f"Order ID: <code>{order_id}</code>\n\n"
        f"⏰ Ye QR <b>{QR_EXPIRE_MINUTES} minute</b> ke liye valid hai.\n\n"
        f"Payment karne ke baad <b>UTR number</b> bhejo."
    )
    await update.message.reply_photo(
        photo=InputFile(qr_img, filename="qr.png"),
        caption=caption,
        parse_mode="HTML"
    )
    return WAITING_UTR


async def recharge_utr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    utr = update.message.text.strip()
    if len(utr) < 8:
        await update.message.reply_text("❌ UTR galat lag raha hai. Sahi UTR bhejo.")
        return WAITING_UTR

    order_id = context.user_data.get("order_id")
    if not order_id or order_id not in pending_payments:
        await update.message.reply_text("❌ Order expire ho gaya. Phir se /start karke recharge karo.")
        return ConversationHandler.END

    pending_payments[order_id]["utr"] = utr
    pending_payments[order_id]["status"] = "waiting_screenshot"

    await update.message.reply_text(
        "✅ UTR mil gaya.\n\nAb payment ka <b>Screenshot</b> bhejo.",
        parse_mode="HTML"
    )
    return WAITING_SCREENSHOT


async def recharge_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Screenshot (photo) bhejo.")
        return WAITING_SCREENSHOT

    order_id = context.user_data.get("order_id")
    if not order_id or order_id not in pending_payments:
        await update.message.reply_text("❌ Order expire ho gaya.")
        return ConversationHandler.END

    photo = update.message.photo[-1]
    pending_payments[order_id]["screenshot_id"] = photo.file_id
    pending_payments[order_id]["status"] = "pending_admin"

    # Notify Admin
    p = pending_payments[order_id]
    admin_text = (
        f"🔔 <b>New Payment Request</b>\n\n"
        f"User: <a href='tg://user?id={p['user_id']}'>{p['full_name']}</a>\n"
        f"Username: @{p['username']}\n"
        f"User ID: <code>{p['user_id']}</code>\n"
        f"Amount: <b>₹{p['amount']}</b>\n"
        f"UTR: <code>{p['utr']}</code>\n"
        f"Order: <code>{order_id}</code>"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{order_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{order_id}")
        ]
    ])
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=admin_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await update.message.reply_text(
        "✅ Screenshot mil gaya!\n\n"
        "Admin check karega. Approve hone pe balance add ho jayega.\n"
        "Thoda wait karo."
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ===================== ADMIN APPROVE / REJECT =====================
async def admin_approve_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("approve_"):
        order_id = data.replace("approve_", "")
        if order_id not in pending_payments:
            await query.edit_message_caption(caption="❌ Order nahi mila.")
            return

        p = pending_payments[order_id]
        if p["status"] != "pending_admin":
            await query.edit_message_caption(caption="⚠️ Ye order already process ho chuka hai.")
            return

        user_id = p["user_id"]
        amount = p["amount"]
        u = get_user(user_id)
        u["balance"] += amount
        p["status"] = "approved"

        await query.edit_message_caption(
            caption=query.message.caption + "\n\n✅ <b>APPROVED</b> by Admin",
            parse_mode="HTML"
        )
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Payment Approved!\n\n₹{amount} balance mein add ho gaya.\nNaya Balance: ₹{u['balance']}"
            )
        except Exception:
            pass

    elif data.startswith("reject_"):
        order_id = data.replace("reject_", "")
        if order_id not in pending_payments:
            await query.edit_message_caption(caption="❌ Order nahi mila.")
            return

        p = pending_payments[order_id]
        p["status"] = "rejected"
        await query.edit_message_caption(
            caption=query.message.caption + "\n\n❌ <b>REJECTED</b> by Admin",
            parse_mode="HTML"
        )
        try:
            await context.bot.send_message(
                chat_id=p["user_id"],
                text="❌ Payment Rejected by Admin.\nAgar dikkat hai to admin se contact karo."
            )
        except Exception:
            pass


# ===================== USER BUY PACKAGE =====================
async def user_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    packages = bot_settings["packages"]
    buttons = []
    for i, pkg in enumerate(packages):
        buttons.append([InlineKeyboardButton(
            f"{pkg['name']} — ₹{pkg['price']}",
            callback_data=f"buypkg_{i}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])

    await query.edit_message_text(
        "🛒 <b>Buy AutoLike Package</b>\n\nSelect karo:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def buy_package_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.replace("buypkg_", ""))
    packages = bot_settings["packages"]
    if idx >= len(packages):
        await query.edit_message_text("❌ Package nahi mila.")
        return

    pkg = packages[idx]
    user_id = query.from_user.id
    u = get_user(user_id)

    if u["balance"] < pkg["price"]:
        await query.edit_message_text(
            f"❌ Balance kam hai.\n\n"
            f"Package: ₹{pkg['price']}\n"
            f"Aapka Balance: ₹{u['balance']}\n\n"
            f"Pehle Recharge karo.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Recharge", callback_data="user_recharge")]])
        )
        return

    # Deduct & activate
    u["balance"] -= pkg["price"]
    u["plan"] = pkg["name"]
    u["days_left"] = pkg["days"]
    u["active"] = True
    u["likes"] = pkg.get("likes", 70)

    await query.edit_message_text(
        f"✅ <b>Package Activated!</b>\n\n"
        f"📦 {pkg['name']}\n"
        f"⏳ Days: {pkg['days']}\n"
        f"💰 Remaining Balance: ₹{u['balance']}\n\n"
        f"Ab har din subah 5 baje AutoLike chalega.",
        parse_mode="HTML",
        reply_markup=user_main_keyboard()
    )


# ===================== USER OTHER =====================
async def user_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    u = get_user(query.from_user.id)
    await query.edit_message_text(
        f"💰 <b>Aapka Balance</b>\n\n₹{u['balance']}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
    )


async def user_myplan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    u = get_user(query.from_user.id)
    if not u["plan"]:
        text = "📦 Koi active plan nahi hai."
    else:
        text = (
            f"📦 <b>Active Plan</b>\n\n"
            f"Plan: <b>{u['plan']}</b>\n"
            f"Days Left: <b>{u['days_left']}</b>\n"
            f"Status: {'🟢 Active' if u['active'] else '🔴 Inactive'}"
        )
    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
    )


async def user_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "ℹ️ <b>Help</b>\n\n"
        "1. Pehle <b>Recharge</b> karo\n"
        "2. Phir <b>Buy AutoLike</b> se package lo\n"
        "3. Har din subah 5 baje auto likes milenge\n\n"
        "Koi problem ho to admin se contact karo."
    )
    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
    )


async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = get_user(user.id)
    bot_name = bot_settings["bot_name"]

    if is_admin(user.id):
        text = f"👑 <b>Admin Panel</b>\n\nBot: <b>{bot_name}</b>"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_main_keyboard())
    else:
        plan_text = f"\n📦 Plan: {data['plan']} | Days: {data['days_left']}" if data["plan"] else "\n📦 No active plan"
        text = f"🔥 <b>{bot_name}</b>\n\n💰 Balance: ₹{data['balance']}{plan_text}"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=user_main_keyboard())


# ===================== ADMIN FUNCTIONS =====================
async def admin_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pending = [oid for oid, p in pending_payments.items() if p["status"] == "pending_admin"]
    if not pending:
        await query.edit_message_text("✅ Koi pending payment nahi hai.", reply_markup=admin_main_keyboard())
        return
    text = f"💰 <b>Pending Payments:</b> {len(pending)}\n\n"
    for oid in pending[:10]:
        p = pending_payments[oid]
        text += f"• ₹{p['amount']} | {p['full_name']} | <code>{oid}</code>\n"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_main_keyboard())


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    total_users = len(users_data)
    active_plans = sum(1 for u in users_data.values() if u.get("active"))
    total_balance = sum(u.get("balance", 0) for u in users_data.values())
    text = (
        f"📊 <b>Stats</b>\n\n"
        f"Total Users: <b>{total_users}</b>\n"
        f"Active Plans: <b>{active_plans}</b>\n"
        f"Total Balance in system: <b>₹{total_balance}</b>"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_main_keyboard())


async def admin_setcmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"⚙️ Current Command: <code>{bot_settings['command']}</code>\n\n"
        f"Naya command bhejo (example: /like ya /getlike):",
        parse_mode="HTML"
    )
    return ADMIN_SET_CMD


async def admin_setcmd_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.strip()
    bot_settings["command"] = cmd
    await update.message.reply_text(f"✅ Command set ho gaya: <code>{cmd}</code>", parse_mode="HTML")
    return ConversationHandler.END


async def admin_setbotname_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🏷 Naya Bot Name bhejo:")
    return ADMIN_SET_BOTNAME


async def admin_setbotname_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_settings["bot_name"] = update.message.text.strip()
    await update.message.reply_text(f"✅ Bot Name: <b>{bot_settings['bot_name']}</b>", parse_mode="HTML")
    return ConversationHandler.END


async def admin_setdevname_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("👨‍💻 Naya Developer Name bhejo:")
    return ADMIN_SET_DEVNAME


async def admin_setdevname_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_settings["dev_name"] = update.message.text.strip()
    await update.message.reply_text(f"✅ Developer Name: <b>{bot_settings['dev_name']}</b>", parse_mode="HTML")
    return ConversationHandler.END


# ===================== DAILY AUTO LIKE JOB =====================
async def daily_autolike_job(context: ContextTypes.DEFAULT_TYPE):
    """Har din subah 5 baje chalta hai"""
    bot = context.bot
    command = bot_settings["command"]
    bot_name = bot_settings["bot_name"]
    dev_name = bot_settings["dev_name"]

    active_users = []
    for uid, data in users_data.items():
        if data.get("active") and data.get("days_left", 0) > 0:
            active_users.append((uid, data))

    if not active_users:
        logger.info("No active users for auto like today.")
        return

    # Send command to AutoLike bot
    try:
        await bot.send_message(chat_id=AUTO_LIKE_BOT, text=command)
    except Exception as e:
        logger.error(f"Failed to send to {AUTO_LIKE_BOT}: {e}")

    # Process each active user
    for uid, data in active_users:
        data["days_left"] -= 1
        if data["days_left"] <= 0:
            data["active"] = False
            data["plan"] = None
            try:
                await bot.send_message(uid, "⏰ Aapka AutoLike plan khatam ho gaya.")
            except Exception:
                pass

        # Post result to Results Group
        result_text = (
            f"✅ <b>AutoLike Sent</b>\n\n"
            f"👤 User ID: <code>{uid}</code>\n"
            f"📦 Plan: {data.get('plan', 'N/A')}\n"
            f"⏳ Days Left: {data['days_left']}\n"
            f"🤖 Bot: {bot_name}\n"
            f"👨‍💻 Developer: {dev_name}\n"
            f"🕐 Time: {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        )
        try:
            await bot.send_message(
                chat_id=RESULTS_GROUP_ID,
                text=result_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send to results group: {e}")


# ===================== CALLBACK ROUTER =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "user_recharge":
        return await recharge_start(update, context)
    elif data == "user_buy":
        return await user_buy(update, context)
    elif data == "user_balance":
        return await user_balance(update, context)
    elif data == "user_myplan":
        return await user_myplan(update, context)
    elif data == "user_help":
        return await user_help(update, context)
    elif data == "back_main":
        return await back_main(update, context)
    elif data.startswith("buypkg_"):
        return await buy_package_confirm(update, context)
    elif data.startswith("approve_") or data.startswith("reject_"):
        return await admin_approve_reject(update, context)
    elif data == "admin_pending":
        return await admin_pending(update, context)
    elif data == "admin_stats":
        return await admin_stats(update, context)
    elif data == "admin_setcmd":
        return await admin_setcmd_start(update, context)
    elif data == "admin_setbotname":
        return await admin_setbotname_start(update, context)
    elif data == "admin_setdevname":
        return await admin_setdevname_start(update, context)
    else:
        await query.answer("Coming soon...")


# ===================== MAIN =====================
def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Error: BOT_TOKEN set nahi hai!")
        print("Ya to code mein token daalo ya ENV variable BOT_TOKEN set karo.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation for Recharge
    recharge_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(recharge_start, pattern="^user_recharge$")],
        states={
            WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, recharge_amount)],
            WAITING_UTR: [MessageHandler(filters.TEXT & ~filters.COMMAND, recharge_utr)],
            WAITING_SCREENSHOT: [MessageHandler(filters.PHOTO, recharge_screenshot)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # Admin set conversations
    setcmd_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_setcmd_start, pattern="^admin_setcmd$")],
        states={ADMIN_SET_CMD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_setcmd_save)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    setbotname_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_setbotname_start, pattern="^admin_setbotname$")],
        states={ADMIN_SET_BOTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_setbotname_save)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    setdevname_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_setdevname_start, pattern="^admin_setdevname$")],
        states={ADMIN_SET_DEVNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_setdevname_save)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(recharge_conv)
    app.add_handler(setcmd_conv)
    app.add_handler(setbotname_conv)
    app.add_handler(setdevname_conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    # Scheduler - har din subah 5:00 AM IST
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        daily_autolike_job,
        CronTrigger(hour=5, minute=0),
        args=[app],
        id="daily_autolike"
    )
    scheduler.start()

    print("✅ Bot started...")
    print("📅 Daily AutoLike scheduled at 05:00 AM IST")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
