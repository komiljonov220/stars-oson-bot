        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[b("❌ Bekor qilish", "admin:broadcast:cancel", "danger")]]
        ),
    )
    await c.answer()


@router.message(Flow.broadcast)
async def admin_broadcast_receive(m: Message, state: FSMContext, bot: Bot):
    if m.from_user.id not in ADMIN_IDS:
        return
    await state.update_data(
        broadcast_chat_id=m.chat.id,
        broadcast_message_id=m.message_id,
    )
    await bot.copy_message(m.chat.id, m.chat.id, m.message_id)
    await m.answer(
        "👆 <b>Preview</b>\n\nShu xabarni barcha foydalanuvchilarga yuboraymi?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [b("✅ Hammaga yuborish", "admin:broadcast:confirm", "success")],
                [b("❌ Bekor qilish", "admin:broadcast:cancel", "danger")],
            ]
        ),
    )


@router.callback_query(F.data == "admin:broadcast:cancel")
async def admin_broadcast_cancel(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)
    await state.clear()
    await c.message.edit_text("❌ Ommaviy xabar bekor qilindi.", reply_markup=admin_back_kb())
    await c.answer()


@router.callback_query(F.data == "admin:broadcast:confirm")
async def admin_broadcast_confirm(c: CallbackQuery, state: FSMContext, bot: Bot):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)
    data = await state.get_data()
    from_chat_id = data.get("broadcast_chat_id")
    message_id = data.get("broadcast_message_id")
    if not from_chat_id or not message_id:
        await state.clear()
        return await c.answer("Xabar topilmadi. Qaytadan urinib ko‘ring.", show_alert=True)

    await c.answer("Yuborish boshlandi.")
    await c.message.edit_text("📤 <b>Ommaviy xabar yuborilmoqda...</b>")
    ok, fail = await broadcast_copy(bot, int(from_chat_id), int(message_id))
    await state.clear()
    await c.message.edit_text(
        f"✅ <b>Ommaviy xabar yakunlandi</b>\n\n"
        f"✅ Yuborildi: <b>{ok} ta</b>\n"
        f"❌ Yetmadi: <b>{fail} ta</b>",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data.in_({"admin:broadcast:open", "admin:broadcast:closed"}))
async def admin_broadcast_status_preview(c: CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)
    is_open = c.data.endswith(":open")
    text = (
        "🟢 <b>StarsOson bot yana ishga tushdi!</b>\n\n"
        "⭐ Stars va 💎 Premium xaridlarini bot orqali 24/7 amalga oshirishingiz mumkin.\n\n"
        "👇 Xarid qilish uchun /start"
        if is_open
        else
        "🔴 <b>StarsOson bot vaqtincha yopildi.</b>\n\n"
        "🛠 Texnik ishlar olib borilmoqda. Bot qayta ishga tushganda xabar beramiz."
    )
    action = "open" if is_open else "closed"
    await c.message.edit_text(
        f"{text}\n\n<b>Bu xabar barcha foydalanuvchilarga yuboriladi.</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [b("✅ Tasdiqlash", f"admin:broadcast:status:{action}", "success")],
                [b("❌ Bekor qilish", "admin:broadcast", "danger")],
            ]
        ),
    )
    await c.answer()


@router.callback_query(F.data.startswith("admin:broadcast:status:"))
async def admin_broadcast_status_send(c: CallbackQuery, bot: Bot):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)

    action = c.data.rsplit(":", 1)[1]
    is_open = action == "open"
    text = (
        "🟢 <b>StarsOson bot yana ishga tushdi!</b>\n\n"
        "⭐ Stars va 💎 Premium xaridlarini bot orqali 24/7 amalga oshirishingiz mumkin.\n\n"
        "👇 Xarid qilish uchun /start"
        if is_open
        else
        "🔴 <b>StarsOson bot vaqtincha yopildi.</b>\n\n"
        "🛠 Texnik ishlar olib borilmoqda. Bot qayta ishga tushganda xabar beramiz."
    )

    await set_setting("bot_enabled", "1" if is_open else "0")
    await c.answer("Yuborish boshlandi.")
    await c.message.edit_text("📤 <b>Status xabari yuborilmoqda...</b>")
    ok, fail = await broadcast_text(bot, text)
    await c.message.edit_text(
        f"{'🟢 Bot yoqildi.' if is_open else '🔴 Bot o‘chirildi.'}\n\n"
        f"✅ Yuborildi: <b>{ok} ta</b>\n"
        f"❌ Yetmadi: <b>{fail} ta</b>",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data == "admin:channel")
async def admin_channel(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)

    await state.clear()
    enabled, channel = await required_channel_settings()
    await c.message.edit_text(
        "📢 <b>Majburiy kanal obunasi</b>\n\n"
        f"Holat: <b>{'✅ YOQILGAN' if enabled else '❌ O‘CHIRILGAN'}</b>\n"
        f"Kanal: <b>{channel or 'kiritilmagan'}</b>\n\n"
        "⚠️ Obunani aniq tekshirish uchun bot kanalda administrator bo‘lishi kerak.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [b("✏️ Kanalni o‘zgartirish", "admin:channel:set", "primary")],
                [b("✅ Yoqish", "admin:channel:on", "success"), b("⛔ O‘chirish", "admin:channel:off", "danger")],
                [b("↩️ Admin", "admin:panel", "danger")],
            ]
        ),
    )
    await c.answer()


@router.callback_query(F.data == "admin:channel:set")
async def admin_channel_set(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)
    await state.set_state(Flow.admin_channel)
    await c.message.edit_text(
        "📢 Kanal username'ini yuboring.\n\n"
        "Masalan: <code>@starsoson</code>\n"
        "Kanal public bo‘lishi kerak.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[b("❌ Bekor qilish", "admin:channel", "danger")]]
        ),
    )
    await c.answer()


@router.message(Flow.admin_channel)
async def admin_channel_value(m: Message, state: FSMContext, bot: Bot):
    if m.from_user.id not in ADMIN_IDS:
        return

    value = (m.text or "").strip()
