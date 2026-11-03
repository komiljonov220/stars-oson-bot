from __future__ import annotations



import asyncio

import json

import logging

import os

import random

import re

import sqlite3

import uuid

from datetime import datetime, timedelta, timezone
from pathlib import Path



import aiohttp

from aiogram import Bot, Dispatcher, F, Router

from aiogram.client.default import DefaultBotProperties

from aiogram.enums import ChatMemberStatus, ParseMode

from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command

from aiogram.fsm.context import FSMContext

from aiogram.fsm.state import State, StatesGroup

from aiogram.fsm.storage.memory import MemoryStorage

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from aiosqlite import connect

from dotenv import load_dotenv



try:

    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

except ImportError:

    TelegramClient = None
    StringSession = None

    events = None



load_dotenv()



# ========================= ASOSIY SOZLAMALAR =========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

FRAGMENT_API_KEY = os.getenv("FRAGMENT_API_KEY", "").strip()

ADMIN_IDS = {

    int(x.strip())

    for x in os.getenv("ADMIN_IDS", "").split(",")

    if x.strip().isdigit()

}

CARD_NUMBER = os.getenv("CARD_NUMBER", "KARTA_RAQAMINI_KIRITING").strip()

SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@Starsoson_bot").strip()

REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "").strip()
FORCE_SUB_ENABLED_DEFAULT = os.getenv("FORCE_SUB_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}

LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID", "0") or 0)

