#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import time
from datetime import datetime
from functools import partial
import requests
import settings


messages = {
    'added': 'Поприветствуем нового бнвачера — @{username}',
    'removed': 'Нас покинул @{username}',
    'renamed': '@{username_old} сменил юзернейм на @{username_new}'
}


class BNWAPI:

    def __init__(self, api_url='https://bnw.im/api/'):
        if not api_url.endswith('/'):
            api_url += '/'
        self.api_url = api_url

    def __getattr__(self, attr):
        return partial(self._request, command=attr)

    def _request(self, command, return_json=True, **kwargs):
        resp = requests.post(self.api_url+command, data=kwargs)
        return resp.json() if return_json else resp.text


class DictSet(dict):

    def __add__(self, other):
        result = self.__class__(self)
        result.update(other)
        return result

    def __sub__(self, other):
        keys = set(self) - set(other)
        return self.__class__((k, self[k]) for k in keys)

    def key_by_value(self, value):
        for k, v in self.items():
            if v == value:
                return k
        raise KeyError("Value '{}' not found".format(value))


def save_to_file(path, users):
    with open(path, 'w') as f:
        for user in sorted(users):
            f.write("{} {}\n".format(user, users[user]))


firstrun = '--firstrun' in sys.argv
nopost = '--nopost' in sys.argv
users_file = os.path.abspath(settings.users_file)
api = BNWAPI()

print(datetime.now().strftime("%d-%m-%Y %H:%M:%S"))

users_from_api = DictSet()
page = 0
while True:
    users = api.userlist(page=page)['users']
    if not users:
        break
    users_from_api.update((u['name'], u['regdate']) for u in users)
    page += 1
print("[API] users:", len(users_from_api))

if firstrun:
    save_to_file(users_file, users_from_api)
    sys.exit()

users_from_file = DictSet()
with open(users_file, 'r') as f:
    for line in f:
        line = line.strip()
        if line:
            user, regdate = line.split(' ', 1)
            try:
                regdate = int(regdate)
            except ValueError:
                regdate = float(regdate)
            users_from_file[user] = regdate
print("[file] users:", len(users_from_file))

api_diff = users_from_api - users_from_file
file_diff = users_from_file - users_from_api

if not api_diff and not file_diff:
    print("no changes")
    sys.exit()

save_to_file(users_file, users_from_api)

renamed = []
removed = []
for user, regdate in file_diff.items():
    try:
        user_new = api_diff.key_by_value(regdate)
    except KeyError:
        removed.append(user)
    else:
        renamed.append((user, user_new))
        del api_diff[user_new]

posts = []
if api_diff:
    print("added:", *api_diff)
    now = int(datetime.now().timestamp())
    for user in sorted(api_diff):
        timedelta = int(now-api_diff[user])
        if settings.added_max_timedelta and timedelta > settings.added_max_timedelta:
            print("skip {}: added {} seconds ago".format(user, timedelta))
        else:
            posts.append(messages['added'].format(username=user))
if removed:
    print("removed:", *removed)
    for user in sorted(removed):
        posts.append(messages['removed'].format(username=user))
if renamed:
    print("renamed:", *("{}>{}".format(*e) for e in renamed))
    for old, new in sorted(renamed):
        posts.append(messages['renamed'].format(username_old=old, username_new=new))
if not nopost:
    for post in posts:
        print(api.post(text=post, login=settings.token, return_json=False))
        time.sleep(settings.sleep)

print("-"*40)
