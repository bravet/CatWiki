# Copyright 2026 CatWiki Authors
#
# Licensed under the CatWiki Open Source License (Modified Apache 2.0);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://github.com/CatWiki/CatWiki/blob/main/LICENSE
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
chat 子包 - 聊天相关服务

提供以下服务:
- ChatSessionService: 会话 CRUD 和统计
- ChatHistoryService: 消息持久化
- ChatService: 聊天核心逻辑
"""

from app.services.chat.chat_service import ChatService, get_chat_service  # noqa: F401
from app.services.chat.history_service import (  # noqa: F401
    ChatHistoryService,
    get_chat_history_service,
)
from app.services.chat.session_service import (  # noqa: F401
    ChatSessionService,
    get_chat_session_service,
)

__all__ = [
    "ChatSessionService",
    "get_chat_session_service",
    "ChatHistoryService",
    "get_chat_history_service",
    "ChatService",
    "get_chat_service",
]
