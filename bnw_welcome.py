import os
import time
import argparse
from datetime import datetime
from functools import partial

import requests


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--token', required=True)
    parser.add_argument('--users-file', required=True)
    parser.add_argument('--sleep', type=int, default=10)
    parser.add_argument('--added-max-timedelta', type=int, default=86400)
    parser.add_argument('--first-run', action='store_true')
    parser.add_argument('--no-post', action='store_true')
    args = parser.parse_args()

    users_file = os.path.abspath(args.users_file)
    if not os.path.exists(users_file):
        print(f"file {users_file} does not exist, forcing --first-run mode")
        first_run = True
    else:
        first_run = args.first_run

    api = BNWAPI()

    users_from_api = DictSet()
    page = 0
    while True:
        users = api.userlist(page=page)['users']
        if not users:
            break
        users_from_api.update((u['name'], u['regdate']) for u in users)
        page += 1
    print("API users:", len(users_from_api))

    if first_run:
        save_to_file(users_file, users_from_api)
        return

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
    print("file users:", len(users_from_file))

    api_diff = users_from_api - users_from_file
    file_diff = users_from_file - users_from_api

    if not api_diff and not file_diff:
        print("no changes")
        return

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
            if timedelta > args.added_max_timedelta:
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
            posts.append(messages['renamed'].format(
                username_old=old, username_new=new))
    if not args.no_post:
        for post in posts:
            print(api.post(text=post, login=args.token, return_json=False))
            time.sleep(args.sleep)


if __name__ == '__main__':
    main()
