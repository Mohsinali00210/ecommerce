import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from Web.models import ChatThread, ChatMessage


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]

        # Reject anonymous connections outright
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.thread_id = self.scope["url_route"]["kwargs"]["thread_id"]
        self.product_id = self.scope["url_route"]["kwargs"].get("product_id")
        # "0" from the widget means "general support thread"
        if str(self.product_id) == "0":
            self.product_id = None

        # Only the thread's owner or staff may join (was: anyone could listen to any thread).
        if str(self.thread_id) not in ("", "0"):
            allowed = await self._can_access(self.thread_id)
            if not allowed:
                await self.close()
                return
            self.room_group_name = f"chat_{self.thread_id}"
        else:
            # New-thread placeholder: a private group until the thread is created.
            self.room_group_name = f"chat_new_{self.user.pk}"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    @database_sync_to_async
    def _can_access(self, thread_id):
        if self.user.is_staff or self.user.is_superuser:
            return ChatThread.objects.filter(id=thread_id).exists()
        return ChatThread.objects.filter(id=thread_id, user=self.user).exists()

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get("message")
        if not message:
            return

        user = self.scope["user"]
        sender_type = "admin" if user.is_superuser else "user"

        thread_id = self.thread_id

        if (not thread_id or str(thread_id) in ["", "0", "null"]) and sender_type == "user":
            thread = await database_sync_to_async(ChatThread.objects.create)(
                user=user,
                product_id=self.product_id
            )

            old_group_name = self.room_group_name

            self.thread_id = thread.id
            self.room_group_name = f"chat_{thread.id}"

            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            # Leave the placeholder "chat_0" group now that we have a real thread
            await self.channel_layer.group_discard(old_group_name, self.channel_name)

            await self.send(text_data=json.dumps({
                "type": "thread_created",
                "thread_id": thread.id
            }))
        else:
            if not await self._can_access(thread_id):
                await self.close()
                return
            thread = await database_sync_to_async(ChatThread.objects.get)(id=thread_id)

        await database_sync_to_async(ChatMessage.objects.create)(
            thread=thread,
            sender_type=sender_type,
            message=message
        )

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message,
                "sender": sender_type
            }
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"],
            "sender": event["sender"]
        }))