from microvk import VkApi, VkApiResponseException
from typing import Union, List
import random
import re


def att_parse(attachments):
    atts = []
    if attachments:
        for i in attachments:
            att_t = i['type']
            if att_t in {'link', 'article'}: continue
            atts.append(att_t + str(i[att_t]['owner_id']) +
            '_' + str(i[att_t]['id']))
            if i[att_t].get('access_key'):
                atts[-1] += '_' + i[att_t]['access_key']
    return atts


class Message:
    text: str
    args: List[str]
    payload: str
    command: str
    attachments: List[str]
    reply: dict
    fwd: List[dict]

    def __init__(self, msg: dict):
        matches = re.findall(r'(\S+)|\n(.*)', msg['text'])
        del matches[0]
        self.command = matches.pop(0)[0].lower()
        self.reply = msg.get('reply_message', {})
        self.fwd = msg.get('fwd_messages', [])
        self.text = msg['text']
        self.payload = ''
        self.args = []
        for i, match in enumerate(matches, 1):
            if match[0]:
                self.args.append(match[0])
            else:
                self.payload += match[1] + ('\n' if i < len(matches) else '')
        self.attachments = att_parse(msg['attachments'])


def gen_secret(chars = 'abcdefghijklmnopqrstuvwxyz0123456789', length: int = None):
    secret = ''
    length = length or random.randint(64, 80)
    while len(secret) < length:
        secret += chars[random.randint(0, len(chars)-1)]
    return secret


def find_user_mention(text: str) -> Union[int, None]:
    uid = re.findall(r'\[(id|public|club)(\d*)\|', text)
    if uid:
        if uid[0][0] != 'id':
            uid = 0 - int(uid[0][1])
        else:
            uid = int(uid[0][1])
    return uid


def find_user_by_link(text: str, vk: VkApi) -> Union[int, None]:
    user = re.findall(r"vk.com\/(id\d*|[^ \n]*\b)", text)
    if user:
        try:
            return vk('users.get', user_ids = user)[0]['id']
        except (VkApiResponseException, IndexError):
            return None


def find_mention_by_event(event: "MySignalEvent") -> Union[int, None]:
    'Возвращает ID пользователя, если он есть в сообщении, иначе None'
    user_id = None
    if event.args:
        user_id = find_user_mention(event.args[0])
    if event.reply_message and not user_id:
        user_id = event.reply_message['from_id']
    if not user_id:
        user_id = find_user_by_link(event.msg['text'], event.api)
    if event.msg['fwd_messages'] and not user_id:
        user_id = event.msg['fwd_messages'][0]['from_id']
    return user_id


def ment_user(user: dict) -> str:
    return f"[id{user['id']}|{user['first_name']} {user['last_name']}]"
