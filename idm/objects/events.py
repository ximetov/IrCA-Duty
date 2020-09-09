import json
import re
from datetime import datetime
from typing import List

from flask import Request

from microvk import VkApi
from wtflog import warden

from idm.api_utils import get_msg
from idm.utils import Message
from . import DB

logger = warden.get_boy('События callback')


class ExceptToJson(Exception):
    response: str

    def __init__(self, message='', code: int = 0, iris: bool = False):
        if iris:
            self.response = json.dumps({'response': 'error',
            'error_code': code, 'error_message': message}, ensure_ascii = False)
        else:
            self.response = 'Error_o4ka:\n' + str(message)


class Chat:
    id: int
    peer_id: int
    iris_id: str
    name: str

    def __init__(self, data: dict, iris_id: str):
        self.peer_id = data.get('peer_id', 0)
        self.id = self.peer_id - 2000000000
        self.name = data.get('name', '')
        self.iris_id = iris_id
        self.installed = data.get('installed', False)


class Event:
    db: DB
    method: str

    api: VkApi

    msg: dict

    time: float
    vk_response_time: float
    obj: dict
    secret: str
    chat: Chat
    attachments: List[str]
    reply_message: dict
    responses: dict

    def set_msg(self, msg: dict = None):
        if msg is None:
            ct = datetime.now().timestamp()
            self.msg = get_msg(self.api, self.chat.peer_id,
                               self.msg['conversation_message_id'])
            self.vk_response_time = datetime.now().timestamp() - ct
        else:
            self.msg = msg
        self.parse()
        self.reply_message = self.msg.get("reply_message", None)

    def set_chat(self):
        if 'chat' not in self.obj.keys():
            return
        if self.obj['chat'] in self.db.chats.keys():
            self.chat = Chat(
                self.db.chats[self.obj['chat']], self.obj['chat'])
            return

        if self.msg:
            cmid_key = 'conversation_message_id'
            if self.msg[cmid_key] is None:
                raise ExceptToJson(code=10, iris=True)
            ct = datetime.now().timestamp()
            chats = self.api("messages.getConversations", count=100)['items']
            self.vk_response_time = datetime.now().timestamp() - ct
            for chat in chats:
                diff = chat['last_message'][cmid_key] - self.msg[cmid_key]
                if diff < 0 or diff > 50:
                    continue
                conv = chat['conversation']
                if conv['peer']['type'] == "chat":
                    message = self.api('messages.getByConversationMessageId',
                                       peer_id=conv['peer']['id'],
                                       conversation_message_ids=self.msg[cmid_key])['items']
                    if not message:
                        continue
                    if (message[0]['from_id'] == self.msg['from_id'] and message[0]['date'] == self.msg['date']):
                        chat_dict = { "peer_id": conv['peer']['id'],
                                    "name": conv['chat_settings']['title'],
                                    "installed": False }
                        self.db.chats.update({self.obj['chat']: chat_dict})
                        self.db.save()
                        self.chat = Chat(chat_dict, self.obj['chat'])
                        self.set_msg(message[0])
                        break
            return
        self.chat = None

    def __init__(self, request: Request):
        if request != None and request.data == b'':
            self.user_id = None
            self.msg = None
            self.obj = None
            self.secret = None
            self.method = 'ping'
        else:
            _data = json.loads(request.data)
            self.secret = _data.get('secret')
            self.obj = _data.get('object', {})
            self.msg = _data.get('message', {})

            try:
                self.db = DB(_data.get('user_id'))
            except:
                raise ExceptToJson('Неверный ID дежурного')

            self.time = datetime.now().timestamp()
            self.api = VkApi(self.db.access_token, raise_excepts=True)
            self.method = _data.get('method', 'ping')
            self.attachments = []
            self.responses = self.db.responses

            if self.method in {'sendSignal', 'sendMySignal', 'subscribeSignals', 'toGroup'}:
                self.set_chat()
            elif self.method in {'ping', 'groupbots.invited', 'bindChat'}:
                pass
            else:
                self.chat = Chat(self.db.chats[self.obj['chat']], self.obj['chat'])

        logger.info(self.__str__())

    def parse(self):
        msg = Message(self.msg)
        self.attachments = msg.attachments
        self.command = msg.command
        self.payload = msg.payload
        self.args = msg.args

    def __str__(self) -> str:
        return f"""Новое событие от Iris callback API
            Метод: {self.method}
            Пользователь: {self.db.duty_id}
            Данные: {json.dumps(self.obj, ensure_ascii=False, indent=4)}
            Сообщение: {json.dumps(self.msg, ensure_ascii=False, indent=4)}
            """.replace("    ", "")


class SignalEvent(Event):
    msg: dict
    chat: Chat

    time: float
    vk_response_time: float
    command: str
    args: list
    payload: str

    reply_message: dict

    def __str__(self) -> str:
        return f"""Новое событие от Iris callback API
            Метод: {self.method}
            Команда: {self.command}
            Аргументы: {self.args}
            Пользователь: {self.db.duty_id}
            Данные: {json.dumps(self.obj, ensure_ascii=False, indent=4)}
            Сообщение: {json.dumps(self.msg, ensure_ascii=False, indent=4)}
            """.replace("    ", "")

    def __init__(self, event: Event):
        self.event = event
        self.time = event.time
        self.api = event.api
        self.db = event.db
        self.method = event.method
        self.obj = event.obj
        self.msg = event.msg
        self.secret = event.secret
        self.chat = event.chat
        self.responses = event.responses

        logger.debug(self.__str__())

    def send(self, text = '', **kwargs):
        self.api.msg_op(1, self.chat.peer_id, text, **kwargs)


class MySignalEvent(Event):

    msg: dict
    chat: Chat

    time: float
    vk_response_time: float
    command: str
    args: list
    payload: str

    reply_message: dict

    def __init__(self, event: Event):
        self.event = event
        self.api = event.api
        self.time = event.time
        self.db = event.db
        self.method = event.method
        self.obj = event.obj
        self.msg = event.msg
        self.secret = event.secret
        self.chat = event.chat
        self.responses = event.responses

        logger.debug(self.__str__())

    def msg_op(self, mode, text = '', **kwargs):
        '1 - новое сообщение, 2 - редактирование, 3 - удаление для всех'
        msg_id = self.msg['id'] if mode in {2, 3, 4} else 0
        self.api.msg_op(mode, self.chat.peer_id, text, msg_id, **kwargs)
