import json
from channels.generic.websocket import AsyncWebsocketConsumer
from Web.models import ChatThread, ChatMessage
from channels.db import database_sync_to_async

class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.thread_id = self.scope['url_route']['kwargs']['thread_id']
        self.room_group_name = f"chat_{self.thread_id}"

        # ✅ FIX: set user here
        self.user = self.scope["user"]

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get('message')

        user = self.scope["user"]
        sender_type = "admin" if user.is_superuser else "user"

        thread_id = self.thread_id

        # 🔥 HANDLE EMPTY / INVALID THREAD
        if (not thread_id or str(thread_id) in ["", "0", "null"]) and sender_type=="user":
            self.product_id = self.scope["url_route"]["kwargs"]["product_id"]  # ✅ FIX

            # create new thread
            thread = await database_sync_to_async(ChatThread.objects.create)(
                user=user,
                product_id=self.product_id  # make sure frontend sends this
            )

            # update thread_id for this connection
            self.thread_id = thread.id
            self.room_group_name = f"chat_{thread.id}"

            # join new group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )

            # 🔁 SEND THREAD ID BACK TO FRONTEND
            await self.send(text_data=json.dumps({
                "type": "thread_created",
                "thread_id": thread.id
            }))

        else:
            # existing thread
            thread = await database_sync_to_async(ChatThread.objects.get)(
                id=thread_id
            )

        # 💬 SAVE MESSAGE
        await database_sync_to_async(ChatMessage.objects.create)(
            thread=thread,
            sender_type=sender_type,
            message=message
        )

        # 📡 SEND MESSAGE TO GROUP
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message,
                "sender": sender_type
            }
        )
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"],
            "sender": event["sender"]
        }))