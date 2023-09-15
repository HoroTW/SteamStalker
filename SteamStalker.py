#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Small script to check if steam friends are playing a game and send a
notification using a telegram bot.

Use a sqlite database to store the state of the friends (e.g. if they are playing a game).
"""

# load the dot env file
from dotenv import load_dotenv
import json
import os
import requests
import backoff
import telegram
import asyncio
from datetime import datetime, timedelta
import time

load_dotenv()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STEAM_KEY = os.getenv("STEAM_KEY")
STEAM_ID = os.getenv("STEAM_ID")
DBFILE = os.getenv("STORE", "steamFriendStateDB.json")
FRIEND_UPDATE_INTERVAL_IN_MIN=os.getenv("NEW_FRIEND_UPDATE_INTERVAL_IN_MIN", 120)
UPDATE_INTERVAL_IN_SEC=os.getenv("FRIEND_STATE_UPDATE_INTERVAL_IN_SEC", 60)


async def get_chats_where_bot_is_member():
    async with telegram.Bot(os.getenv("TELEGRAM_TOKEN")) as bot:
        updates = await bot.get_updates()
        for update in updates:
            joined_new_chat = update.my_chat_member
            if not joined_new_chat:
                continue

            print(f"TITLE: joined_new_chat.chat.title")
            print(f"ID: {joined_new_chat.chat.id}\n")


@backoff.on_exception(backoff.expo, requests.exceptions.RequestException, max_time=60)
async def send_message(message="Hello there!"):
    bot = telegram.Bot(os.getenv("TELEGRAM_TOKEN"))
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)


@backoff.on_exception(backoff.expo, requests.exceptions.RequestException, max_time=60)
def get_steam_friends(steamID, key):
    url = f"https://api.steampowered.com/ISteamUser/GetFriendList/v1/?key={key}&steamid={steamID}"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Error: {response.status_code} on {url}")
    return response.json()["friendslist"]["friends"]


@backoff.on_exception(backoff.expo, requests.exceptions.RequestException, max_time=60)
def update(friends, STEAM_KEY):
    url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_KEY}&steamids="
    for friend in friends:
        url += str(friend["steamid"]) + ","
    url = url[:-1]  # remove last comma
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Error: {response.status_code} on {url}")

    players = response.json()["response"]["players"]

    # open db file
    with open(DBFILE, "r") as f:
        db = json.load(f)

        for player in players:
            game = "NOTHING"
            if "gameid" in player:
                game = player["gameid"]            
                extra = player["gameextrainfo"]

            # check if entry needs update
            if player["steamid"] in db and db[player["steamid"]] == game:
                continue  # no update needed

            # update entry for player
            db[player["steamid"]] = game

            # send message
            if game == "NOTHING":
                message = f"{player['personaname']} is not playing anymore..."
            else:
                message = f"{player['personaname']}: {extra}"
            print(message)
            asyncio.run(send_message(message))

        # write db file
        with open(DBFILE, "w") as f:
            json.dump(db, f, indent=4)

    return response.json()["response"]["players"]


if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "FIND_BY_FIRST_RUN":
    print("TELEGRAM_CHAT_ID not set. List of chats (groups) where the bot is a member:")
    asyncio.run(get_chats_where_bot_is_member())
    exit(1)

# ensure db file exists
if not os.path.isfile(DBFILE):
    with open(DBFILE, "w") as f:
        json.dump({}, f)

friends = get_steam_friends(STEAM_ID, STEAM_KEY)
updateFriendsTime = datetime.now() + timedelta(minutes=FRIEND_UPDATE_INTERVAL_IN_MIN)

while True:
    if datetime.now() > updateFriendsTime:
        updateFriendsTime = datetime.now() + timedelta(minutes=FRIEND_UPDATE_INTERVAL_IN_MIN)
        friends = get_steam_friends(STEAM_ID, STEAM_KEY)

    update(friends, STEAM_KEY)
    time.sleep(UPDATE_INTERVAL_IN_SEC)
